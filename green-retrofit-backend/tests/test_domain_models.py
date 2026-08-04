"""데이터 계약 단위시험 — **코드를 이 위로 옮기기 전에** 계약을 고정한다.

계약이 틀린 채로 743줄을 옮기면 잘못된 키·단위·해상도 가정이 새 계층에 고착된다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.models import (  # noqa: E402
    AnnualEnergySummary,
    BaselineSource,
    CapitalCostResult,
    CategoryMetric,
    ConsumptionBasis,
    ConversionStep,
    EnergyCategory,
    EnergyConversionContext,
    EnergyMetrics,
    EnergyTimeSeries,
    TariffResult,
    TimeResolution,
)


def _series(n=3, **override):
    base = dict(
        months=[1] * n, hours=list(range(n)),
        heating_requirement_kwh=[1.0] * n, cooling_requirement_kwh=[0.0] * n,
        heating_consumption_kwh=[0.5] * n, cooling_consumption_kwh=[0.0] * n,
        heating_rate_w=[10.0] * n, cooling_rate_w=[0.0] * n,
        lighting_kwh=[0.1] * n, equipment_kwh=[0.2] * n, dhw_kwh=[0.0] * n,
        fan_kwh=[0.05] * n, ventilation_kg_s=[0.01] * n,
    )
    base.update(override)
    months, hours = base.pop("months"), base.pop("hours")
    return EnergyTimeSeries.build(TimeResolution.HOURLY, months, hours, **base)


# ── 시계열 ──────────────────────────────────────────────

def test_series_is_immutable_including_contents():
    """frozen=True 는 리스트 *내용*을 막지 못한다 → 튜플이어야 한다."""
    s = _series()
    assert isinstance(s.heating_requirement_kwh, tuple)
    with pytest.raises(TypeError):
        s.heating_requirement_kwh[0] = 99


@pytest.mark.parametrize("field", [
    "heating_rate_w", "cooling_rate_w", "fan_kwh", "ventilation_kg_s",
    "heating_consumption_kwh", "lighting_kwh",
])
def test_every_series_field_length_is_checked(field):
    """⚠️ 예전 계약은 4개 필드를 검사하지 않았다."""
    with pytest.raises(ValueError, match="길이 불일치"):
        _series(**{field: [1.0]})


def test_non_finite_values_are_rejected():
    with pytest.raises(ValueError, match="유한하지"):
        _series(heating_requirement_kwh=[1.0, float("nan"), 1.0])


def test_month_and_hour_ranges_are_checked():
    with pytest.raises(ValueError, match="month"):
        _series(months=[0, 1, 1])
    with pytest.raises(ValueError, match="hour"):
        _series(hours=[0, 1, 99])


def test_resolution_is_explicit_not_inferred_from_row_count():
    """⚠️ 예전에는 `len(df) > 365` 로 해상도를 **추정**했다.
    데이터가 무엇인지가 아니라 얼마나 많은지를 본 것이라 계약으로 틀렸다."""
    monthly = EnergyTimeSeries.build(
        TimeResolution.MONTHLY, months=list(range(1, 13)), hours=[12] * 12,
        heating_requirement_kwh=[1.0] * 12, cooling_requirement_kwh=[0.0] * 12,
        heating_consumption_kwh=[1.0] * 12, cooling_consumption_kwh=[0.0] * 12,
        heating_rate_w=[0.0] * 12, cooling_rate_w=[0.0] * 12,
        lighting_kwh=[0.0] * 12, equipment_kwh=[0.0] * 12, dhw_kwh=[0.0] * 12,
        fan_kwh=[0.0] * 12, ventilation_kg_s=[0.0] * 12)
    assert monthly.resolution is TimeResolution.MONTHLY
    assert monthly.row_count == 12


# ── 변환 근거 ────────────────────────────────────────────

def test_conversion_context_exposes_fallbacks():
    """미터가 없어 추정한 항목은 기계 판독 가능해야 한다 — 문자열 메모로는 부족하다."""
    ctx = EnergyConversionContext(
        hvac_mode="fuel",
        steps=(
            ConversionStep(EnergyCategory.HEATING, ConsumptionBasis.METERED,
                           source_name="Heating:OtherFuel1"),
            ConversionStep(EnergyCategory.COOLING, ConsumptionBasis.DERIVED_FROM_COP,
                           factor=2.8, note="Cooling:Electricity 미터 없음"),
        ))
    assert len(ctx.fallback_steps) == 1
    assert ctx.fallback_steps[0].category is EnergyCategory.COOLING
    assert ctx.fallback_steps[0].factor == 2.8


# ── 매트릭스 ────────────────────────────────────────────

def _metrics(**override):
    cats = {
        EnergyCategory.HEATING: CategoryMetric(10.0, 5.0),
        EnergyCategory.COOLING: CategoryMetric(20.0, 7.0),
        EnergyCategory.RENEWABLE: CategoryMetric(-3.0, -3.0),
    }
    kw = dict(by_category=cats, primary_energy_kwh_m2=100.0, co2_kg_m2=30.0,
              renewable_independence_pct=5.0, floor_area_m2=100.0)
    kw.update(override)
    return EnergyMetrics(**kw)


def test_renewable_is_excluded_from_totals():
    m = _metrics()
    assert m.demand_kwh_m2 == pytest.approx(30.0)     # -3 이 빠져야 한다
    assert m.consumption_kwh_m2 == pytest.approx(12.0)


def test_category_keys_must_be_enum():
    """오타를 생성 시점에 잡는 것이 계약의 목적이다."""
    with pytest.raises(TypeError, match="EnergyCategory"):
        _metrics(by_category={"heating": CategoryMetric(1.0, 1.0)})


def test_zero_floor_area_is_rejected():
    with pytest.raises(ValueError, match="바닥면적"):
        _metrics(floor_area_m2=0)


def test_response_keys_match_existing_api():
    """⚠️ 프런트가 이 문자열에 의존한다. dhw/vent 가 아니라 hotwater/ventilation."""
    assert EnergyCategory.HOT_WATER.value == "hotwater"
    assert EnergyCategory.VENTILATION.value == "ventilation"
    d = _metrics().as_response_dict()
    assert set(d) == {"heating", "cooling", "renewable"}
    assert d["heating"] == {"req": 10.0, "con": 5.0}


# ── 연간 집계 ────────────────────────────────────────────

def _annual(**override):
    kw = dict(heating_requirement_kwh=100.0, cooling_requirement_kwh=200.0,
              heating_consumption_kwh=50.0, cooling_consumption_kwh=70.0,
              dhw_requirement_kwh=10.0, dhw_consumption_kwh=10.0,
              ventilation_requirement_kwh=5.0, ventilation_consumption_kwh=8.0,
              lighting_kwh=30.0, equipment_kwh=40.0, fan_kwh=3.0)
    kw.update(override)
    return AnnualEnergySummary(**kw)


def test_fan_is_not_double_counted():
    """⚠️ 매트릭스의 ventilation.con 은 처리에너지 + 팬전력이다.
    총합에서 팬을 또 더하면 이중계산이 된다."""
    a = _annual()
    assert a.total_consumption_kwh == pytest.approx(50 + 70 + 10 + 8 + 30 + 40)


def test_ventilation_is_represented_not_just_fan():
    """예전 계약에는 fan_kwh 만 있어 매트릭스를 재현할 수 없었다."""
    a = _annual()
    assert a.ventilation_consumption_kwh == 8.0
    assert a.ventilation_requirement_kwh == 5.0


# ── 요금 ────────────────────────────────────────────────

def test_baseline_source_spelling_matches_existing_api():
    """⚠️ 실제 응답은 "estimate" 다. "estimated" 로 쓰면 기존 시험·프런트가 깨진다."""
    assert BaselineSource.ESTIMATE.value == "estimate"


def test_tariff_rejects_raw_string_source():
    with pytest.raises(TypeError, match="BaselineSource"):
        TariffResult(1000.0, 500.0, "electricity", 2000.0, "estimate")


def test_tariff_saving_is_baseline_minus_current():
    t = TariffResult(1000.0, 500.0, "electricity", 2000.0, BaselineSource.SIMULATED)
    assert t.total_won == 1500.0
    assert t.annual_saving_won == 500.0


# ── 자본비 ──────────────────────────────────────────────

def test_over_budget_is_zero_when_within():
    c = CapitalCostResult({"window": 100.0}, 100.0, budget_won=200.0)
    assert c.over_budget_won == 0.0


def test_over_budget_reports_excess():
    c = CapitalCostResult({"window": 300.0}, 300.0, budget_won=200.0)
    assert c.over_budget_won == 100.0


def test_no_budget_means_no_overrun():
    assert CapitalCostResult({"a": 1.0}, 1.0).over_budget_won == 0.0
