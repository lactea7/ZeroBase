"""`economics/tariffs.py` 단위시험.

golden 은 연간 요금 **총액 2개**만 고정한다. 그것으로는 TOU 구간을 잘못 배정하거나
PV 를 엉뚱한 시간에 배분해도 총액이 상쇄되면 통과한다. 여기서 규칙 자체를 못박는다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.models import EnergyTimeSeries, TimeResolution  # noqa: E402
from src.economics.tariffs import (  # noqa: E402
    ELEC_RATE_SPRING,
    ELEC_RATE_SUMMER,
    ELEC_RATE_WINTER,
    HEAT_RATE_KWH,
    PV_YIELD_KWH_PER_KW,
    TOU_RATES,
    annual_bills,
    apply_pv_self_consumption,
    electricity_rates,
    heat_source_entry,
    seasonal_rate,
    split_by_carrier,
    tou_rate,
)


def _series(months, hours, resolution=TimeResolution.HOURLY, **override):
    n = len(months)
    base = dict(
        heating_requirement_kwh=[0.0] * n, cooling_requirement_kwh=[0.0] * n,
        heating_consumption_kwh=[0.0] * n, cooling_consumption_kwh=[0.0] * n,
        heating_rate_w=[0.0] * n, cooling_rate_w=[0.0] * n,
        lighting_kwh=[0.0] * n, equipment_kwh=[0.0] * n, dhw_kwh=[0.0] * n,
        fan_kwh=[0.0] * n, ventilation_kg_s=[0.0] * n,
    )
    base.update(override)
    return EnergyTimeSeries.build(resolution, months, hours, **base)


# ── TOU 구간 ────────────────────────────────────────────

@pytest.mark.parametrize("month,hour,expected", [
    # 여름(6~8월): 13~17 피크 / 9~13·17~23 중간 / 나머지 경부하
    (7, 14, TOU_RATES["summer"]["peak"]),
    (7, 13, TOU_RATES["summer"]["peak"]),
    (7, 17, TOU_RATES["summer"]["mid"]),      # 경계: 17시는 피크가 아니다
    (7, 10, TOU_RATES["summer"]["mid"]),
    (7, 3,  TOU_RATES["summer"]["off"]),
    (7, 23, TOU_RATES["summer"]["off"]),      # 경계: 23시부터 경부하
    # 겨울(11~2월): 9~12·16~19 피크
    (12, 10, TOU_RATES["winter"]["peak"]),
    (12, 17, TOU_RATES["winter"]["peak"]),
    (1, 13,  TOU_RATES["winter"]["mid"]),
    (2, 5,   TOU_RATES["winter"]["off"]),
    # 봄·가을: 피크 구간이 없다
    (4, 14, TOU_RATES["spring"]["mid"]),
    (10, 2, TOU_RATES["spring"]["off"]),
])
def test_tou_boundaries(month, hour, expected):
    assert tou_rate(month, hour) == expected


def test_spring_has_no_peak_period():
    """봄·가을은 피크가 없다 — 있으면 요율표 해석이 틀린 것이다."""
    assert TOU_RATES["spring"]["peak"] == TOU_RATES["spring"]["mid"]


@pytest.mark.parametrize("month,expected", [
    (7, ELEC_RATE_SUMMER), (12, ELEC_RATE_WINTER), (4, ELEC_RATE_SPRING)])
def test_seasonal_flat_rate(month, expected):
    assert seasonal_rate(month) == expected


def test_hourly_uses_tou_monthly_uses_flat():
    """⚠️ 월별 출력에 TOU 를 적용하면 시각이 전부 12시로 고정돼 요금이 왜곡된다."""
    hourly = _series([7, 7], [3, 14])
    assert electricity_rates(hourly) == [TOU_RATES["summer"]["off"],
                                         TOU_RATES["summer"]["peak"]]
    monthly = _series([7, 12], [12, 12], resolution=TimeResolution.MONTHLY)
    assert electricity_rates(monthly) == [ELEC_RATE_SUMMER, ELEC_RATE_WINTER]


# ── 에너지원 배분 ────────────────────────────────────────

def test_heat_pump_moves_heating_to_electricity():
    """⚠️ 히트펌프면 난방이 전기로 간다. 열 요금엔 급탕만 남는다."""
    s = _series([1], [10], heating_consumption_kwh=[5.0], cooling_consumption_kwh=[1.0],
                lighting_kwh=[2.0], equipment_kwh=[3.0], dhw_kwh=[4.0])
    split = split_by_carrier(s, [0.5], use_pthp=True)
    assert split.electricity_kwh == pytest.approx((1 + 2 + 3 + 0.5 + 5,))
    assert split.heat_kwh == pytest.approx((4.0,))
    assert split.heating_is_electric


def test_fuel_boiler_keeps_heating_in_heat():
    s = _series([1], [10], heating_consumption_kwh=[5.0], cooling_consumption_kwh=[1.0],
                lighting_kwh=[2.0], equipment_kwh=[3.0], dhw_kwh=[4.0])
    split = split_by_carrier(s, [0.5], use_pthp=False)
    assert split.electricity_kwh == pytest.approx((1 + 2 + 3 + 0.5,))
    assert split.heat_kwh == pytest.approx((5 + 4,))
    assert not split.heating_is_electric


def test_ventilation_is_always_electric():
    s = _series([1], [10])
    for pthp in (True, False):
        assert split_by_carrier(s, [7.0], use_pthp=pthp).electricity_kwh == pytest.approx((7.0,))


# ── PV 자가소비 ──────────────────────────────────────────

def test_pv_only_offsets_daytime():
    """주간(9~17시)에만 발전을 배분한다."""
    hours = [3, 10, 14, 20]
    out = apply_pv_self_consumption([100.0] * 4, hours, pv_capacity_kw=1.0)
    assert out[0] == 100.0 and out[3] == 100.0          # 야간은 그대로
    assert out[1] < 100.0 and out[2] < 100.0


def test_pv_generation_is_spread_over_daytime_steps():
    hours = [10, 14]                                    # 주간 2스텝
    out = apply_pv_self_consumption([1000.0] * 2, hours, pv_capacity_kw=1.0)
    per_step = PV_YIELD_KWH_PER_KW / 2
    assert out == pytest.approx((1000 - per_step, 1000 - per_step))


def test_surplus_is_discarded_not_credited():
    """⚠️ 잉여 발전은 버린다 — 역송 보상 미반영(보수적). 음수가 나오면 안 된다."""
    out = apply_pv_self_consumption([1.0], [12], pv_capacity_kw=100.0)
    assert out == (0.0,)


def test_no_pv_is_a_noop():
    assert apply_pv_self_consumption([5.0, 6.0], [12, 13], 0.0) == (5.0, 6.0)


def test_all_night_data_leaves_consumption_untouched():
    """주간 스텝이 하나도 없으면 나눗셈이 터지면 안 된다."""
    assert apply_pv_self_consumption([5.0], [2], pv_capacity_kw=10.0) == (5.0,)


# ── 열원 ────────────────────────────────────────────────

def test_geothermal_is_billed_as_electricity():
    assert heat_source_entry(11, is_geothermal=True)["label"] == "전기(히트펌프)"


def test_unknown_heat_source_falls_back_to_district():
    assert heat_source_entry(999)["rate"] == pytest.approx(HEAT_RATE_KWH)


def test_district_heat_rate_conversion():
    """Mcal → kWh 환산(÷1.163)이 틀리면 난방비가 통째로 어긋난다."""
    assert HEAT_RATE_KWH == pytest.approx(112.32 / 1.163, abs=1e-6)


# ── 요금 합계 ────────────────────────────────────────────

def test_bills_use_per_row_rates():
    """행마다 요율이 다르므로 총량 × 평균요율로 계산하면 안 된다."""
    elec, heat = annual_bills([10.0, 10.0], [5.0], [100.0, 200.0], heat_rate_won_per_kwh=50.0)
    assert elec == pytest.approx(10 * 100 + 10 * 200)
    assert heat == pytest.approx(5 * 50)


# ── 실제 경로에서 계약이 만들어지는가 ─────────────────────
# ⚠️ 정의만 해두고 안 쓰면 계약이 아니다. codex 가 "TariffResult 는 정의됐지만
# calculate() 가 생성하지 않는다"고 지적했다.

def test_analyzer_produces_tariff_result(analyzer, base_kwargs):
    """`calculate()` 가 TariffResult 를 실제로 만들고 응답 값과 일치하는지."""
    import src.cost_analyzer as ca
    captured = {}
    original = ca.TariffResult

    class Spy(original):
        def __post_init__(self):
            original.__post_init__(self)
            captured["value"] = self

    ca.TariffResult = Spy
    try:
        result = analyzer.calculate(**base_kwargs)
    finally:
        ca.TariffResult = original

    t = captured.get("value")
    assert t is not None, "calculate() 가 TariffResult 를 만들지 않는다"
    fin = result["financial"]
    # 응답은 정수로 반올림해 내보내고 계약은 원값을 들고 있다 — 1원 이내면 같다
    assert t.electricity_won == pytest.approx(fin["annual_elec_bill"], abs=1.0)
    assert t.heating_won == pytest.approx(fin["annual_heat_bill"], abs=1.0)
    assert t.baseline_source.value == fin["baseline_assumptions"]["source"]


def test_rates_have_a_single_source():
    """⚠️ 요율이 두 곳에 있으면 한쪽만 갱신했을 때 결과가 조용히 갈라진다."""
    from src.cost_analyzer import LCCAnalyzer
    from src.economics import tariffs
    assert LCCAnalyzer.ELEC_BASE_CHARGE is tariffs.ELEC_BASE_CHARGE
    assert LCCAnalyzer.TOU_RATES is tariffs.TOU_RATES
    assert LCCAnalyzer.HEAT_SOURCE_DB is tariffs.HEAT_SOURCE_DB
    assert LCCAnalyzer.DEFAULT_HEAT_SOURCE is tariffs.DEFAULT_HEAT_SOURCE
