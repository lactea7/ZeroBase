"""`energyplus/outputs.py` 단위시험.

**왜 필요한가**: golden fixture(`eplusout_monthly.csv`)는 월별·이상부하라서
`pthp`/`fuel` 경로를 전혀 덮지 못한다. 즉 파싱 코드의 절반이 회귀 시험 없이
분리됐다. 여기서 그 절반을 덮는다 — 특히 **미터가 없을 때의 폴백**은
사용자 결과를 조용히 근사치로 바꾸므로 반드시 고정해야 한다.
"""
import os
import sys

import numpy as np
import pandas as pd
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.models import (  # noqa: E402
    ConsumptionBasis,
    EnergyCategory,
    TimeResolution,
)
from src.energyplus.outputs import (  # noqa: E402
    FALLBACK_DX_COOLING_COP,
    FALLBACK_PTHP_COOLING_COP,
    FALLBACK_PTHP_HEATING_COP,
    J_TO_KWH,
    MONTHLY_HOURS,
    VENT_SPECIFIC_FAN_POWER_KW_PER_M3S,
    parse_outputs,
    ventilation_energy_kwh,
)

N = 4
ZONE = {"id": "ZONE A", "isConditioned": True, "hvacSystemId": 5}


def _df(**cols):
    """EnergyPlus 시각 형식 첫 열 + 지정한 데이터 열."""
    stamps = [f" 01/0{i+1}  0{i+1}:00:00" for i in range(N)]
    return pd.DataFrame({"Date/Time": stamps, **cols})


def _kwh(values):
    return np.array(values, dtype=float) * J_TO_KWH


# ── 시간축 ──────────────────────────────────────────────

# ⚠️ 해상도를 **행 수로 추정하면 안 된다.** 365행 이하의 정상적인 시간별 부분 실행이
# 월별로 오판되면 환기에 730 배가 붙어 결과가 통째로 틀어진다.
# EnergyPlus 는 모든 열 이름 끝에 보고주기를 적으므로 그것을 1순위로 쓴다.

def test_monthly_csv_is_detected_by_column_tag():
    df = pd.DataFrame({"Date/Time": [f"January {i}" for i in range(1, 13)],
                       "X:Lights Electricity Energy [J](Monthly)": [0.0] * 12})
    s = parse_outputs(df, [], np_mod=np)
    assert s.resolution is TimeResolution.MONTHLY
    assert list(s.months) == list(range(1, 13))


def test_short_hourly_run_is_not_mistaken_for_monthly():
    """설계일·부분 기간 실행은 행이 적어도 시간별이다."""
    stamps = [f" 07/21  {h:02d}:00:00" for h in range(1, 25)]
    df = pd.DataFrame({"Date/Time": stamps,
                       "X:Lights Electricity Energy [J](Hourly)": [0.0] * 24})
    s = parse_outputs(df, [], np_mod=np)
    assert s.resolution is TimeResolution.HOURLY
    assert set(s.months) == {7}


def test_full_year_hourly_is_hourly():
    stamps = [f" {m:02d}/{d:02d}  {h:02d}:00:00"
              for m in range(1, 13) for d in (1, 2) for h in range(1, 25)]
    df = pd.DataFrame({"Date/Time": stamps,
                       "X:Lights Electricity Energy [J](Hourly)": [0.0] * len(stamps)})
    assert parse_outputs(df, [], np_mod=np).resolution is TimeResolution.HOURLY


def test_unlabelled_columns_fall_back_to_timestamps():
    """보고주기 표기가 없으면 타임스탬프 간격으로 판정한다."""
    stamps = [f" 03/01  {h:02d}:00:00" for h in range(1, 13)]
    df = pd.DataFrame({"Date/Time": stamps, "X:Lights Electricity Energy [J]": [0.0] * 12})
    assert parse_outputs(df, [], np_mod=np).resolution is TimeResolution.HOURLY


def test_hourly_stamps_are_parsed():
    stamps = [f" {m:02d}/{d:02d}  {h:02d}:00:00"
              for m in (1, 2) for d in range(1, 11) for h in range(1, 25)]
    df = pd.DataFrame({"Date/Time": stamps,
                       "X:Lights Electricity Energy [J](Hourly)": [0.0] * len(stamps)})
    s = parse_outputs(df, [], np_mod=np)
    assert s.resolution is TimeResolution.HOURLY
    assert set(s.months) == {1, 2}
    assert set(s.hours) == set(range(1, 25))


# ── pthp 경로 ────────────────────────────────────────────

def test_pthp_uses_meters_when_present():
    df = _df(**{
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": _kwh([10] * N),
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": _kwh([20] * N),
        "Heating:Electricity [J](Hourly)": _kwh([3] * N),
        "Cooling:Electricity [J](Hourly)": _kwh([5] * N),
        "Fans:Electricity [J](Hourly)": _kwh([1] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="pthp")
    assert s.heating_requirement_kwh == pytest.approx((10,) * N)
    assert s.heating_consumption_kwh == pytest.approx((3,) * N)   # 미터 그대로
    assert s.cooling_consumption_kwh == pytest.approx((5,) * N)
    assert s.fan_kwh == pytest.approx((1,) * N)
    assert s.context.fallback_steps == (), "미터가 있는데 폴백으로 기록됐다"


def test_pthp_falls_back_to_cop_without_meters():
    """⚠️ 미터가 없으면 요구량÷대표COP 로 **근사**한다. 조용히 넘어가면 안 된다."""
    df = _df(**{
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": _kwh([7] * N),
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": _kwh([42] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="pthp")
    assert s.heating_consumption_kwh == pytest.approx((7 / FALLBACK_PTHP_HEATING_COP,) * N)
    assert s.cooling_consumption_kwh == pytest.approx((42 / FALLBACK_PTHP_COOLING_COP,) * N)

    fallbacks = {st.category: st for st in s.context.fallback_steps}
    assert EnergyCategory.HEATING in fallbacks and EnergyCategory.COOLING in fallbacks
    assert fallbacks[EnergyCategory.HEATING].factor == FALLBACK_PTHP_HEATING_COP
    assert "근사치" in fallbacks[EnergyCategory.HEATING].note


# ── fuel 경로 ────────────────────────────────────────────

def test_fuel_uses_fuel_meter_when_present():
    df = _df(**{
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": _kwh([10] * N),
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": _kwh([0] * N),
        "Heating:OtherFuel1 [J](Hourly)": _kwh([11] * N),
        "Cooling:Electricity [J](Hourly)": _kwh([2] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="fuel",
                      heating_fuel="OtherFuel1", heating_fuel_eff=0.95)
    assert s.heating_consumption_kwh == pytest.approx((11,) * N)
    steps = {st.category: st for st in s.context.steps}
    assert steps[EnergyCategory.HEATING].basis is ConsumptionBasis.METERED
    assert "OtherFuel1" in steps[EnergyCategory.HEATING].source_name


def test_fuel_falls_back_to_efficiency_without_meter():
    df = _df(**{
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": _kwh([9.5] * N),
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": _kwh([33] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="fuel",
                      heating_fuel="NaturalGas", heating_fuel_eff=0.95)
    assert s.heating_consumption_kwh == pytest.approx((9.5 / 0.95,) * N)
    # 냉방은 DX 대표 COP 로 폴백 (PTHP 와 값이 다르다)
    assert s.cooling_consumption_kwh == pytest.approx((33 / FALLBACK_DX_COOLING_COP,) * N)
    assert s.context.heating_efficiency == 0.95


# ── ideal 경로 ───────────────────────────────────────────

def test_ideal_divides_requirement_by_efficiency():
    """⚠️ 이상부하에서도 요구량 ≠ 소비량이다. hvacSystemId 5 + 지역난방(11) → 0.95."""
    df = _df(**{
        "ZONE_A_IDEAL:Zone Ideal Loads Supply Air Total Heating Energy [J](Hourly)": _kwh([9.5] * N),
        "ZONE_A_IDEAL:Zone Ideal Loads Supply Air Total Cooling Energy [J](Hourly)": _kwh([28] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="ideal", heat_source=11)
    assert s.heating_requirement_kwh == pytest.approx((9.5,) * N)
    assert s.heating_consumption_kwh == pytest.approx((9.5 / 0.95,) * N)
    assert s.cooling_consumption_kwh == pytest.approx((28 / 2.80,) * N)   # COOLING_EFF_DB[5]


def test_ideal_skips_unconditioned_zones():
    df = _df(**{
        "ZONE_A_IDEAL:Zone Ideal Loads Supply Air Total Heating Energy [J](Hourly)": _kwh([10] * N),
    })
    zones = [dict(ZONE, isConditioned=False)]
    s = parse_outputs(df, zones, np_mod=np, hvac_mode="ideal")
    assert s.heating_requirement_kwh == pytest.approx((0,) * N)


def test_zone_prefix_matching_is_exact():
    """⚠️ 부분문자열 매칭이면 'ZONE A' 가 'ZONE A2' 열도 합산해 이중집계된다."""
    df = _df(**{
        "ZONE_A_IDEAL:Zone Ideal Loads Supply Air Total Heating Energy [J](Hourly)": _kwh([10] * N),
        "ZONE_A2_IDEAL:Zone Ideal Loads Supply Air Total Heating Energy [J](Hourly)": _kwh([99] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="ideal", heat_source=11)
    assert s.heating_requirement_kwh == pytest.approx((10,) * N), "다른 존 열까지 합산했다"


def test_geothermal_uses_fixed_cops():
    df = _df(**{
        "ZONE_A_IDEAL:Zone Ideal Loads Supply Air Total Heating Energy [J](Hourly)": _kwh([9] * N),
        "ZONE_A_IDEAL:Zone Ideal Loads Supply Air Total Cooling Energy [J](Hourly)": _kwh([10] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="ideal", is_geothermal=True)
    assert s.heating_consumption_kwh == pytest.approx((9 / 4.5,) * N)
    assert s.cooling_consumption_kwh == pytest.approx((10 / 5.0,) * N)


# ── 공통 항목 ────────────────────────────────────────────

def test_dhw_columns_are_all_summed():
    """⚠️ 존마다 열이 따로 있다. 하나만 잡으면 급탕이 과소산정된다."""
    df = _df(**{
        "A:Water Use Equipment Heating Energy [J](Hourly)": _kwh([1] * N),
        "B:Water Use Equipment Heating Energy [J](Hourly)": _kwh([2] * N),
    })
    s = parse_outputs(df, [], np_mod=np)
    assert s.dhw_kwh == pytest.approx((3 * 1.1,) * N)     # 배관손실 1.1


def test_missing_columns_yield_zeros_not_errors():
    s = parse_outputs(_df(**{"X:Something Else [J](Hourly)": [0.0] * N}), [], np_mod=np)
    assert s.lighting_kwh == pytest.approx((0,) * N)
    assert s.row_count == N


def test_ventilation_energy_includes_fan_and_uses_same_factor():
    """요구량과 소비량이 **같은 계수**를 거쳐야 한다.
    예전에는 요구량에만 계수가 빠져 체적(m³)이 kWh 합계에 섞였다."""
    df = _df(**{
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": _kwh([0] * N),
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": _kwh([0] * N),
        "A:Zone Mechanical Ventilation Mass Flow Rate [kg/s](Hourly)": [1.2] * N,
        "Fans:Electricity [J](Hourly)": _kwh([0.5] * N),
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="pthp")
    # 열 이름이 (Hourly) 이므로 4행이라도 시간별이다 — 730 배가 붙으면 안 된다
    assert s.resolution is TimeResolution.HOURLY
    vent = ventilation_energy_kwh(s, np)
    # 1.2 kg/s ÷ 1.2 kg/m³ = 1 m³/s → ×0.8 kW/(m³/s) = 0.8 kW → ×1h + 팬 0.5
    assert vent == pytest.approx(np.array([1.0 * VENT_SPECIFIC_FAN_POWER_KW_PER_M3S + 0.5] * N))


def test_hourly_ventilation_has_no_monthly_multiplier():
    """⚠️ 월별 CSV 에만 730 배가 붙는다. 시간별에 붙으면 환기가 730배 과대해진다."""
    stamps = [f" 01/{d:02d}  {h:02d}:00:00" for d in range(1, 21) for h in range(1, 25)]
    n = len(stamps)
    df = pd.DataFrame({
        "Date/Time": stamps,
        "A:Zone Mechanical Ventilation Mass Flow Rate [kg/s](Hourly)": [1.2] * n,
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": [0.0] * n,
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": [0.0] * n})
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="pthp")
    assert s.resolution is TimeResolution.HOURLY
    assert ventilation_energy_kwh(s, np) == pytest.approx(np.full(n, VENT_SPECIFIC_FAN_POWER_KW_PER_M3S))


# ── 환기 계수의 단위 계약 ────────────────────────────────
# ⚠️ 상수 이름이 예전엔 `VENT_ENERGY_PER_M3`, 주석이 "kWh/m³" 였다. 그 이름대로
# 읽으면 "질량유량이 순간값이니 초 환산 3600 이 빠졌다"는 결론이 나오는데,
# 실제로 곱하면 환기 에너지가 **3,600배**가 된다. 이 시험이 그것을 막는다.

def test_ventilation_coefficient_is_specific_fan_power_not_energy_per_volume():
    """0.8 kWh/m³ 는 물리적으로 불가능하다.

    공기 1 m³(1.2 kg)를 ΔT 만큼 처리하는 데 드는 열은 1.2 × 1.005 × ΔT kJ 다.
    0.8 kWh/m³ = 2,880 kJ/m³ 이 되려면 ΔT ≈ 2,388 K 여야 한다.
    반면 0.8 kW/(m³/s) 는 비팬동력(SFP)의 정상 범위다(고효율 0.8~1.2).
    """
    kj_per_m3 = VENT_SPECIFIC_FAN_POWER_KW_PER_M3S * 3600
    implied_delta_t = kj_per_m3 / (1.2 * 1.005)
    assert implied_delta_t > 1000, (
        f"kWh/m³ 로 해석하면 ΔT={implied_delta_t:.0f}K — 불가능한 값이다")
    assert 0.5 <= VENT_SPECIFIC_FAN_POWER_KW_PER_M3S <= 3.0, "SFP 정상 범위를 벗어났다"


def test_hourly_ventilation_energy_is_not_scaled_by_seconds():
    """⚠️ 시간별 1시간 구간에 곱할 것은 **1시간**이지 3,600초가 아니다."""
    n = 4
    df = _df(**{
        "A:Zone Mechanical Ventilation Mass Flow Rate [kg/s](Hourly)": [1.2] * n,
        "A:Zone Air System Sensible Heating Energy [J](Hourly)": [0.0] * n,
        "A:Zone Air System Sensible Cooling Energy [J](Hourly)": [0.0] * n,
    })
    s = parse_outputs(df, [ZONE], np_mod=np, hvac_mode="pthp")
    vent = ventilation_energy_kwh(s, np)
    # 1 m³/s × 0.8 kW/(m³/s) × 1h = 0.8 kWh
    assert vent == pytest.approx(np.full(n, 0.8))
    assert vent[0] < 10, "3,600 을 곱하면 시간당 2,880 kWh 라는 값이 나온다"


def test_ventilation_uses_the_same_coefficient_as_peak_sizing():
    """⚠️ 피크(설비 용량·기본요금)와 사용량이 다른 SFP 를 쓰면 어긋난다."""
    from src.domain import sizing
    assert sizing._VENT_SFP_KW_PER_M3S == VENT_SPECIFIC_FAN_POWER_KW_PER_M3S
