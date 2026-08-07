"""`simulation/hvac_plan.py` 단위시험 — 열원 → 설비 계획.

⚠️ 여기서 고른 모드가 **소비량 산출 방식 자체를 바꾼다**(`energyplus/outputs`):
  · pthp/fuel — EnergyPlus 미터 실측을 그대로 쓴다
  · ideal     — 존별 요구량을 COP·효율로 나눈다
모드를 잘못 고르면 요구량과 소비량이 뒤섞인다. 그런데 이 분기는 존 루프 직전에
얽혀 있어 시험이 없었다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.simulation.hvac_plan import (  # noqa: E402
    ELECTRIC_HEAT_SOURCE,
    FUEL_SYSTEMS,
    GEOTHERMAL_COPS,
    resolve,
)

EQUIP = {"cool_cop": 3.3, "heat_factor": 0.9, "pthp_cops": (4.2, 3.5),
         "is_user_input": False, "cooling_grade": "3등급", "heating_age": "10년"}


def _resolve(project, equip=None, **kw):
    return resolve(project, equip or dict(EQUIP), **kw)


# ── 모드 선택 ────────────────────────────────────────────

@pytest.mark.parametrize("heat_source", sorted(FUEL_SYSTEMS))
def test_fuel_heat_sources_use_real_equipment(heat_source):
    """연료 열원은 미터 실측 경로다 — COP 나눗셈 근사를 쓰지 않는다."""
    plan = _resolve({"heatSource": heat_source})
    assert plan.mode == "fuel"
    assert plan.fuel_type == FUEL_SYSTEMS[heat_source][0]


def test_electric_heat_source_uses_heat_pump():
    assert _resolve({"heatSource": ELECTRIC_HEAT_SOURCE}).mode == "pthp"


def test_geothermal_forces_heat_pump_regardless_of_heat_source():
    """지열은 열원 설정과 무관하게 히트펌프다."""
    plan = _resolve({"heatSource": 1, "geothermalApplied": True})
    assert plan.mode == "pthp"
    assert plan.is_geothermal is True


@pytest.mark.parametrize("unknown", [3, 5, 99])
def test_unmapped_heat_source_falls_back_to_ideal(unknown):
    assert _resolve({"heatSource": unknown}).mode == "ideal"


def test_default_heat_source_is_district_heating():
    """미지정이면 지역난방 — 조용히 이상부하로 빠지면 안 된다."""
    plan = _resolve({})
    assert plan.mode == "fuel"
    assert plan.fuel_type == "OtherFuel1"


def test_heat_source_accepts_string_input():
    """프런트가 문자열로 보내도 매핑돼야 한다."""
    assert _resolve({"heatSource": "1"}).fuel_type == "NaturalGas"


# ── COP·효율 ─────────────────────────────────────────────

def test_boiler_efficiency_is_degraded_by_age():
    """⚠️ 성능은 세우는 순간이 아니라 **지금**이 기준이다."""
    plan = _resolve({"heatSource": 1})       # 가스 0.87 × 열화 0.9
    assert plan.fuel_efficiency == pytest.approx(0.783)


def test_geothermal_cops_are_fixed_not_degraded():
    """지열은 신설 전제라 등급·연식 보정을 걸지 않는다."""
    plan = _resolve({"geothermalApplied": True})
    assert (plan.pthp_cooling_cop, plan.pthp_heating_cop) == GEOTHERMAL_COPS


def test_ordinary_heat_pump_uses_graded_cops():
    plan = _resolve({"heatSource": ELECTRIC_HEAT_SOURCE})
    assert (plan.pthp_cooling_cop, plan.pthp_heating_cop) == EQUIP["pthp_cops"]


def test_window_ac_cop_comes_from_user_grade():
    assert _resolve({"heatSource": 1}).cooling_cop == 3.3


# ── ASHRAE 140 강제 이상부하 ──────────────────────────────

@pytest.mark.parametrize("project", [
    {"heatSource": 1}, {"heatSource": 2}, {"geothermalApplied": True},
])
def test_benchmark_forces_ideal_loads_over_any_heat_source(project):
    """⚠️ 140 은 **용량 무제한·효율 100%** 를 요구한다. 실기기로는 그 사양을
    표현할 수 없으므로 열원 설정과 무관하게 이상부하여야 참조값 비교가 성립한다."""
    plan = _resolve(project, force_ideal_loads=True)
    assert plan.mode == "ideal"
    assert plan.fuel_type is None
    assert plan.fuel_efficiency is None


# ── 파생 속성 ────────────────────────────────────────────

@pytest.mark.parametrize("project,sizing", [
    ({"heatSource": 1}, True),      # 보일러 autosize
    ({"heatSource": 2}, True),      # PTHP autosize
    ({"heatSource": 3}, False),     # 이상부하는 사이징이 필요 없다
])
def test_only_real_equipment_needs_sizing(project, sizing):
    assert _resolve(project).needs_sizing is sizing


def test_fuel_label_is_korean():
    assert _resolve({"heatSource": 1}).fuel_label == "가스보일러"
    assert _resolve({"heatSource": 11}).fuel_label == "지역난방"


def test_describe_names_the_mode():
    assert "PTHP" in _resolve({"heatSource": 2}).describe()
    assert "이상부하" in _resolve({"heatSource": 3}).describe()
    assert "보일러" in _resolve({"heatSource": 1}).describe()


def test_plan_is_immutable():
    """계획이 나중에 바뀌면 IDF 와 결과 해석이 어긋난다."""
    plan = _resolve({"heatSource": 1})
    with pytest.raises(Exception):
        plan.mode = "ideal"
