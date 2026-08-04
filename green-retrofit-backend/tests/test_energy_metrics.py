"""`domain/energy_metrics.py` 단위시험.

golden 은 실제 fixture 로 합계를 고정한다. 여기서는 **계수 적용 규칙**을 못박는다 —
어느 용도에 열원 계수가 붙고 어디가 ZEB 분모에서 빠지는지는 합계만 보면
서로 상쇄돼 잡히지 않는다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.energy_metrics import (  # noqa: E402
    CO2_FACTOR_ELEC,
    PRIMARY_FACTOR_ELEC,
    build_metrics,
)
from src.domain.models import AnnualEnergySummary, EnergyCategory  # noqa: E402

AREA = 100.0
DISTRICT_PRIMARY = 0.728       # 지역난방
DISTRICT_CO2 = 0.200


def _annual(**override):
    kw = dict(heating_requirement_kwh=1000.0, cooling_requirement_kwh=2000.0,
              heating_consumption_kwh=1000.0, cooling_consumption_kwh=500.0,
              dhw_requirement_kwh=300.0, dhw_consumption_kwh=330.0,
              ventilation_requirement_kwh=200.0, ventilation_consumption_kwh=250.0,
              lighting_kwh=400.0, equipment_kwh=600.0, fan_kwh=50.0)
    kw.update(override)
    return AnnualEnergySummary(**kw)


def _metrics(pv=0.0, **override):
    return build_metrics(_annual(**override), floor_area_m2=AREA,
                         pv_generation_kwh_m2=pv,
                         heat_primary_factor=DISTRICT_PRIMARY,
                         heat_co2_factor=DISTRICT_CO2)


# ── 원단위 ──────────────────────────────────────────────

def test_values_are_divided_by_floor_area():
    m = _metrics()
    assert m.by_category[EnergyCategory.HEATING].consumption_kwh_m2 == pytest.approx(10.0)
    assert m.by_category[EnergyCategory.COOLING].consumption_kwh_m2 == pytest.approx(5.0)


def test_lighting_and_equipment_have_equal_requirement_and_consumption():
    """조명·기기는 전력이 곧 요구량이다."""
    m = _metrics()
    for cat in (EnergyCategory.LIGHTING, EnergyCategory.EQUIPMENT):
        c = m.by_category[cat]
        assert c.requirement_kwh_m2 == c.consumption_kwh_m2


def test_zero_area_does_not_divide_by_zero():
    with pytest.raises(ValueError, match="바닥면적"):
        build_metrics(_annual(), floor_area_m2=0.0, pv_generation_kwh_m2=0.0,
                      heat_primary_factor=1.0, heat_co2_factor=1.0)


# ── 계수 적용 ────────────────────────────────────────────

def test_heat_categories_use_heat_source_factors():
    """⚠️ 난방·급탕에 전기계수를 쓰면 지역난방에서 1차에너지가 3.8배 과대해진다.
    예전엔 프런트가 모든 항목에 전기계수를 곱해 상세표와 요약이 어긋났다."""
    m = _metrics()
    heat = m.by_category[EnergyCategory.HEATING]
    assert heat.primary_energy_kwh_m2 == round(10.0 * DISTRICT_PRIMARY, 1)
    assert heat.co2_kg_m2 == round(10.0 * DISTRICT_CO2, 2)


def test_electric_categories_use_electric_factors():
    m = _metrics()
    cool = m.by_category[EnergyCategory.COOLING]
    # 소수 1자리 반올림은 계약의 일부다(응답 크기를 줄이고 화면 표시와 맞춘다)
    assert cool.primary_energy_kwh_m2 == round(5.0 * PRIMARY_FACTOR_ELEC, 1)
    assert cool.co2_kg_m2 == round(5.0 * CO2_FACTOR_ELEC, 2)


def test_renewable_has_no_emissions():
    m = _metrics(pv=7.0)
    assert m.by_category[EnergyCategory.RENEWABLE].co2_kg_m2 == 0.0


def test_renewable_is_negative_in_matrix():
    """상계 항목이므로 음수로 들어가 수요·소비 합계에서 빠진다."""
    m = _metrics(pv=7.0)
    assert m.by_category[EnergyCategory.RENEWABLE].consumption_kwh_m2 == pytest.approx(-7.0)


# ── ZEB 등급·자립률 ──────────────────────────────────────

def test_grade_primary_excludes_equipment_and_renewable():
    """⚠️ 기기는 건축 성능이 아니라 사용자 기기다. 등급 산정에서 빠진다."""
    m = _metrics(pv=5.0)
    assert m.by_category[EnergyCategory.EQUIPMENT].grade_primary_energy_kwh_m2 == 0.0
    assert m.by_category[EnergyCategory.RENEWABLE].grade_primary_energy_kwh_m2 == 0.0
    assert m.by_category[EnergyCategory.LIGHTING].grade_primary_energy_kwh_m2 > 0


def test_grade_primary_sum_matches_summary():
    """상세 표의 gradePrimary 합계가 요약의 1차에너지와 같아야 한다."""
    m = _metrics()
    total = sum(c.grade_primary_energy_kwh_m2 for c in m.by_category.values())
    assert total == pytest.approx(m.primary_energy_kwh_m2, abs=0.15)


def test_co2_includes_equipment():
    """CO₂ 는 실제 배출이므로 기기를 **포함**한다 — 등급용 1차에너지와 다르다."""
    without = _metrics(equipment_kwh=0.0).co2_kg_m2
    with_equip = _metrics(equipment_kwh=600.0).co2_kg_m2
    assert with_equip > without


def test_independence_denominator_excludes_equipment():
    """⚠️ 분모는 5대 에너지다. 기기를 넣으면 자립률이 낮게 나온다."""
    m = _metrics(pv=3.0)
    five = sum(c.consumption_kwh_m2 for k, c in m.by_category.items()
               if k not in (EnergyCategory.EQUIPMENT, EnergyCategory.RENEWABLE))
    assert m.renewable_independence_pct == pytest.approx(3.0 / five * 100, abs=0.1)


def test_independence_is_capped_at_100():
    assert _metrics(pv=9999.0).renewable_independence_pct == 100.0


def test_independence_is_zero_without_pv():
    assert _metrics(pv=0.0).renewable_independence_pct == 0.0


# ── 합계 ────────────────────────────────────────────────

def test_totals_exclude_renewable():
    m = _metrics(pv=7.0)
    assert m.consumption_kwh_m2 == pytest.approx(10 + 5 + 3.3 + 4 + 2.5 + 6, abs=0.1)


def test_response_dict_carries_all_fields():
    d = _metrics(pv=1.0).as_response_dict()
    assert set(d["heating"]) == {"req", "con", "primary", "co2", "gradePrimary"}
    assert d["renewable"]["con"] == pytest.approx(-1.0)
