"""`simulation/variants.py` 단위시험 — 대안 변형 페이로드.

⚠️ 이 코드는 분리 전까지 **시험이 하나도 없었다.** 그런데 여기서 `None` 이 나오면
그 추천은 **재시뮬레이션을 건너뛰고 "에너지 변화 0"으로 화면에 나간다.** 조건
하나만 틀려도 조용히 그렇게 되므로, 대상 판정을 값으로 고정한다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.simulation.variants import (  # noqa: E402
    GLAZING_HIGH_LOWE_AR,
    GLAZING_STANDARD_DOUBLE,
    INSULATION_HIGH_ID,
    INSULATION_HIGH_K,
    INSULATION_STANDARD_ID,
    INSULATION_STANDARD_K,
    build_variant_payload,
    net_effect,
    payback_years,
)


def _payload(surfaces=None, constructions=None, overrides=None, project=None):
    return {
        "surfaces": surfaces or [],
        "materials": {"constructions": constructions or []},
        "constructionOverrides": overrides or {},
        "projectData": project or {},
    }


def _construction(cid, conductivity, thickness=120):
    return {"id": cid, "layers": [
        {"name": "콘크리트", "conductivity": 1.6, "thickness": 200},
        {"name": "단열", "conductivity": conductivity, "thickness": thickness,
         "isInsulation": True},
    ]}


# ── 창호 ────────────────────────────────────────────────

@pytest.mark.parametrize("surface", [
    {"id": "W1", "type": "Window"},
    {"id": "W1", "type": "Skylight"},
    {"id": "W1", "type": "ExteriorWall", "glazingId": 154},
    {"id": "W1", "type": "ExteriorWall", "wwr": 0.4},
])
def test_glass_surfaces_are_recognised(surface):
    """⚠️ `type` 만 보면 WWR 로만 표현된 창을 놓친다 — 파서가 두 방식을 다 쓴다."""
    v = build_variant_payload(_payload([surface]), "window")
    assert v is not None, f"유리 면을 못 알아봤다: {surface}"
    assert v["surfaces"][0]["glazingId"] == GLAZING_STANDARD_DOUBLE


def test_wwr_zero_wall_is_not_a_window():
    assert build_variant_payload(
        _payload([{"id": "W1", "type": "ExteriorWall", "wwr": 0}]), "window") is None


def test_window_downgrade_is_noop_when_already_standard():
    """이미 일반 복층이면 바꿀 게 없다 → None."""
    assert build_variant_payload(
        _payload([{"id": "W1", "type": "Window", "glazingId": GLAZING_STANDARD_DOUBLE}]),
        "window") is None


def test_window_upgrade_targets_high_performance_glazing():
    v = build_variant_payload(
        _payload([{"id": "W1", "type": "Window", "glazingId": GLAZING_STANDARD_DOUBLE}]),
        "window_upgrade")
    assert v["surfaces"][0]["glazingId"] == GLAZING_HIGH_LOWE_AR


def test_original_payload_is_not_mutated():
    """⚠️ 원본을 건드리면 **본 시뮬레이션 결과가 대안 값으로 오염**된다."""
    payload = _payload([{"id": "W1", "type": "Window", "glazingId": 999}])
    build_variant_payload(payload, "window")
    assert payload["surfaces"][0]["glazingId"] == 999


# ── 단열 ────────────────────────────────────────────────

def test_insulation_downgrade_uses_product_conductivity_not_tier_default():
    """⚠️ tier 대표값(0.055)이 아니라 **실제 제품 물성**(0.036)을 써야
    프런트가 적용하는 값과 일치한다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       overrides={"S1": {"tier": "premium", "thickness": 150}})
    v = build_variant_payload(payload, "insulation")
    assert v["constructionOverrides"]["S1"] == {
        "insulationId": INSULATION_STANDARD_ID, "tier": "standard", "thickness": 150}
    assert v["insulationOverrides"]["C1"]["conductivity"] == INSULATION_STANDARD_K


def test_insulation_downgrade_preserves_thickness():
    """등급만 낮추고 두께는 그대로 — 두께까지 바꾸면 어느 쪽 효과인지 알 수 없다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       overrides={"S1": {"tier": "high", "thickness": 220}})
    v = build_variant_payload(payload, "insulation")
    assert v["insulationOverrides"]["C1"]["thickness"] == 220


def test_insulation_downgrade_detects_good_insulation_without_override():
    """사용자 지정이 없어도 원 구성의 단열층이 좋으면(λ≤0.045) 하향 대상이다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.034)])
    v = build_variant_payload(payload, "insulation")
    assert v["constructionOverrides"]["S1"]["tier"] == "standard"
    assert v["insulationOverrides"]["C1"]["thickness"] == 120


def test_insulation_downgrade_skips_already_poor_insulation():
    """부실 단열(λ>0.045)은 더 낮출 게 없다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.060)])
    assert build_variant_payload(payload, "insulation") is None


def test_insulation_upgrade_is_the_mirror_image():
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.060)])
    v = build_variant_payload(payload, "insulation_upgrade")
    assert v["constructionOverrides"]["S1"]["insulationId"] == INSULATION_HIGH_ID
    assert v["insulationOverrides"]["C1"]["conductivity"] == INSULATION_HIGH_K


def test_upgrade_and_downgrade_boundaries_do_not_overlap():
    """⚠️ 경계(0.045)에서 양쪽 다 걸리면 상향/하향 추천이 서로를 되돌리는
    핑퐁이 된다. λ=0.045 는 하향 대상이고 상향 대상이 아니다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.045)])
    assert build_variant_payload(payload, "insulation") is not None
    assert build_variant_payload(payload, "insulation_upgrade") is None


def test_surface_without_construction_is_skipped():
    payload = _payload([{"id": "S1"}], constructions=[_construction("C1", 0.030)])
    assert build_variant_payload(payload, "insulation") is None


def test_construction_without_insulation_layer_is_skipped():
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[{"id": "C1", "layers": [
                           {"name": "콘크리트", "conductivity": 1.6, "thickness": 200}]}])
    assert build_variant_payload(payload, "insulation") is None


def test_existing_overrides_of_other_surfaces_survive():
    """대상이 아닌 면의 사용자 지정을 지우면 그 면이 기본 사양으로 되돌아간다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"},
                        {"id": "S2", "constructionRef": "C2"}],
                       overrides={"S1": {"tier": "premium", "thickness": 150},
                                  "S2": {"tier": "basic", "thickness": 50}})
    v = build_variant_payload(payload, "insulation")
    assert v["constructionOverrides"]["S2"] == {"tier": "basic", "thickness": 50}


# ── 설비 ────────────────────────────────────────────────

def test_hvac_downgrade_only_applies_when_geothermal_is_on():
    """지열이 없으면 하향할 열모델 변화가 없다 — 표준 하향은 비용만 바뀐다."""
    assert build_variant_payload(_payload(project={}), "hvac") is None
    v = build_variant_payload(_payload(project={"geothermalApplied": True}), "hvac")
    assert v["projectData"]["geothermalApplied"] is False


def test_hvac_upgrade_is_noop_when_already_upgraded():
    assert build_variant_payload(
        _payload(project={"hvacUpgradeActive": True}), "hvac_upgrade") is None


def test_hvac_upgrade_does_not_mutate_project_data():
    payload = _payload(project={"buildingType": "office"})
    build_variant_payload(payload, "hvac_upgrade")
    assert "hvacUpgradeActive" not in payload["projectData"]


@pytest.mark.parametrize("rec_type", ["led", "hvac_scope", "", "알수없는타입"])
def test_non_thermal_recommendations_return_none(rec_type):
    """열모델이 안 바뀌는 대안은 재시뮬레이션이 무의미하다."""
    assert build_variant_payload(_payload(), rec_type) is None


# ── 경제성 ───────────────────────────────────────────────

def test_net_effect_discounts_future_bill_increases():
    """운영비가 늘면 절감액에서 그 현재가치를 뺀다."""
    # 할인율 = 물가상승률이면 매년 증가분의 현재가치가 그대로 누적된다
    assert net_effect(1_000_000, 10_000, discount_rate=0.05,
                      utility_inflation=0.05, years=20) == 800_000


def test_net_effect_is_negative_when_operating_loss_exceeds_saving():
    """⚠️ 음수면 '비권장' — 시스템이 손해로 판명한 대안을 그대로 제안하면
    사용자가 적용 → 반대 대안 제안 → 재적용의 핑퐁에 빠진다."""
    assert net_effect(100_000, 50_000, discount_rate=0.05,
                      utility_inflation=0.04, years=20) < 0


def test_net_effect_of_a_saving_alternative_is_the_saving_itself():
    assert net_effect(500_000, 0, discount_rate=0.05,
                      utility_inflation=0.04, years=20) == 500_000


def test_payback_only_when_cost_rises_and_bills_fall():
    assert payback_years(10_000_000, -2_000_000) == 5.0


@pytest.mark.parametrize("capital,bill", [
    (-5_000_000, -1_000_000),   # 공사비가 줄었다 — 회수할 것이 없다
    (10_000_000, 1_000_000),    # 운영비도 늘었다 — 영영 회수 못 한다
    (10_000_000, 0),            # 운영비 변화 없음 — 0으로 나눌 뻔했다
])
def test_payback_is_none_when_the_concept_does_not_apply(capital, bill):
    """⚠️ 0 이나 음수를 내보내면 화면에서 '즉시 회수'로 읽힌다."""
    assert payback_years(capital, bill) is None
