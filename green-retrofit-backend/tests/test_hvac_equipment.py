# 실기기 입력 매핑: 등급/연식 → COP·효율, 존별 냉방 설치 계획
from src.ep_simulator import (
    COOLING_COP_BY_GRADE, PTHP_COP_BY_GRADE, HEATING_EFF_FACTOR_BY_AGE,
    resolve_hvac_equipment, zone_cooling_plan, PYEONG_TO_KW,
)


def test_default_when_no_input():
    """미입력 시 기존 기본값과 동일해야 한다 (하위 호환)."""
    eq = resolve_hvac_equipment({})
    assert eq["cool_cop"] == 3.3
    assert eq["pthp_cops"] == (4.2, 3.5)
    assert eq["heat_factor"] == 1.0
    assert eq["is_user_input"] is False


def test_grade_and_age_mapping():
    eq = resolve_hvac_equipment({"hvacEquipment": {"coolingGrade": "old15", "heatingAge": "old"}})
    assert eq["cool_cop"] == 2.2
    assert eq["pthp_cops"] == (2.7, 2.2)
    assert eq["heat_factor"] == 0.85
    assert eq["is_user_input"] is True


def test_invalid_input_falls_back():
    eq = resolve_hvac_equipment({"hvacEquipment": {"coolingGrade": "정체불명", "heatingAge": "??"}})
    assert eq["cool_cop"] == 3.3 and eq["heat_factor"] == 1.0


def test_grades_monotonic():
    """등급이 나빠질수록 COP가 단조 감소해야 한다."""
    order = ["grade1", "grade3", "grade5", "old10", "old15"]
    cops = [COOLING_COP_BY_GRADE[g] for g in order]
    assert cops == sorted(cops, reverse=True)
    pthp = [PTHP_COP_BY_GRADE[g][0] for g in order]
    assert pthp == sorted(pthp, reverse=True)


def test_zone_cooling_plan_auto_excludes_non_habitable():
    assert zone_cooling_plan({"id": "1 STAIRCASE"}, 3000)["installed"] is False
    assert zone_cooling_plan({"id": "1 ROOM"}, 3000)["installed"] is True


def test_zone_cooling_plan_user_override():
    # 비거주 존이라도 사용자가 '설치' 선택하면 설치
    p = zone_cooling_plan({"id": "1 STAIRCASE", "coolingInstalled": "yes"}, 3000)
    assert p["installed"] is True and p["source"] == "user"
    # 거주 존이라도 '미설치' 선택하면 제외
    p = zone_cooling_plan({"id": "1 ROOM", "coolingInstalled": "no"}, 3000)
    assert p["installed"] is False and p["source"] == "user"


def test_zone_cooling_capacity_pyeong():
    p = zone_cooling_plan({"id": "1 ROOM", "coolingCapacityPyeong": 6}, 3000)
    assert p["capacity_w"] == 6 * PYEONG_TO_KW * 1000   # 6평형 ≈ 2.3kW
    assert p["source"] == "user"
