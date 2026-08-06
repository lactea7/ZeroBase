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
    insulated_u_value,
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
                       constructions=[_construction("C1", 0.030)],
                       overrides={"S1": {"tier": "premium", "thickness": 150}})
    v = build_variant_payload(payload, "insulation")
    assert v["constructionOverrides"]["S1"]["insulationId"] == INSULATION_STANDARD_ID
    assert v["constructionOverrides"]["S1"]["tier"] == "standard"
    assert v["constructionOverrides"]["S1"]["thickness"] == 150
    # 프런트도 override 에 uValue 를 심는다 — 같은 모양이어야 한다
    assert v["constructionOverrides"]["S1"]["uValue"] == v["surfaces"][0]["uValue"]
    assert v["surfaces"][0]["uValue"] == pytest.approx(
        insulated_u_value(_construction("C1", 0.030),
                          conductivity=INSULATION_STANDARD_K, thickness_mm=150))


def test_insulation_downgrade_preserves_thickness():
    """등급만 낮추고 두께는 그대로 — 두께까지 바꾸면 어느 쪽 효과인지 알 수 없다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.030)],
                       overrides={"S1": {"tier": "high", "thickness": 220}})
    v = build_variant_payload(payload, "insulation")
    assert v["constructionOverrides"]["S1"]["thickness"] == 220


# ── 열모델이 실제로 바뀌는지 ────────────────────────────
# ⚠️ IDF 조립부의 기본 모드는 면의 `uValue` 만 본다. `constructionOverrides` 항목
# 만으로는 **U 값이 안 바뀐다** — 실제로 바꾸는 건 `insulationOverrides[c_ref]` 뿐이고
# 그건 구성이 `materials.constructions` 에 실재할 때만 동작한다.
# 이걸 확인하지 않으면 2.5분 재시뮬레이션 후 `simulated: True, delta 0.0` 이 나온다.

@pytest.mark.parametrize("c_ref", [None, "존재하지-않는-구성"])
def test_override_without_a_real_construction_is_not_simulatable(c_ref):
    """⚠️ `constructionIdRef` 가 아예 없는 gbXML 이 실제로 있다
    (회의실.xml: Surface 1,230개 전부). 그 모델에서 단열 대안은 열모델을
    못 바꾸므로 재시뮬레이션을 돌리면 안 된다."""
    payload = _payload([{"id": "S1", "constructionRef": c_ref}],
                       overrides={"S1": {"tier": "premium", "thickness": 150}})
    assert build_variant_payload(payload, "insulation") is None
    assert build_variant_payload(payload, "insulation_upgrade") is None


def test_shared_construction_keeps_each_surface_thickness():
    """⚠️ 예전에는 `insulationOverrides` 키가 면이 아니라 **구성**이라, 같은
    구성을 공유하는 면들의 두께가 다르면 마지막 값이 전부에 적용됐다. 프런트는
    면별로 계산하므로 "대안이 예고한 효과"와 "실제 적용 결과"가 갈렸다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"},
                        {"id": "S2", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.030)],
                       overrides={"S1": {"tier": "premium", "thickness": 150},
                                  "S2": {"tier": "premium", "thickness": 250}})
    v = build_variant_payload(payload, "insulation")
    by_id = {s["id"]: s for s in v["surfaces"]}
    assert v["constructionOverrides"]["S1"]["thickness"] == 150
    assert v["constructionOverrides"]["S2"]["thickness"] == 250
    # 두꺼운 쪽이 반드시 U 값이 낮아야 한다 — 같으면 구성 단위로 뭉갠 것이다
    assert by_id["S1"]["uValue"] > by_id["S2"]["uValue"]


def test_insulation_downgrade_detects_good_insulation_without_override():
    """사용자 지정이 없어도 원 구성의 단열층이 좋으면(λ≤0.045) 하향 대상이다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.034)])
    v = build_variant_payload(payload, "insulation")
    assert v["constructionOverrides"]["S1"]["tier"] == "standard"
    assert v["constructionOverrides"]["S1"]["thickness"] == 120


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
    assert v["surfaces"][0]["uValue"] == pytest.approx(
        insulated_u_value(_construction("C1", 0.060),
                          conductivity=INSULATION_HIGH_K, thickness_mm=120))


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
                       constructions=[_construction("C1", 0.030),
                                      _construction("C2", 0.030)],
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


# ── 프런트와 산식 일치 ───────────────────────────────────
# ⚠️ 여기서 예고한 U 값과 사용자가 실제로 적용한 뒤의 U 값이 다르면
# "적용 시 실제 차액" 원칙이 깨진다. 프런트는 App.jsx `calculateUpdatedUValue`.

def test_u_value_matches_the_frontend_formula():
    """U = 1 / (0.17 + Σ 비단열층 R + 새 단열층 R)"""
    c = _construction("C1", 0.030, thickness=100)
    # 콘크리트 200mm/1.6 = 0.125, 단열 150mm/0.036 = 4.1667
    expected = 1.0 / (0.17 + 0.2 / 1.6 + 0.150 / 0.036)
    assert insulated_u_value(c, conductivity=0.036, thickness_mm=150) == pytest.approx(
        round(expected, 4))


def test_thicker_insulation_lowers_u():
    c = _construction("C1", 0.030)
    thin = insulated_u_value(c, conductivity=0.036, thickness_mm=50)
    thick = insulated_u_value(c, conductivity=0.036, thickness_mm=200)
    assert thick < thin


def test_original_insulation_layer_is_replaced_not_added():
    """⚠️ 기존 단열층 R 을 남기고 새 층을 더하면 U 가 실제보다 낮게 나온다."""
    c = _construction("C1", 0.030, thickness=300)   # 원래 아주 두꺼운 단열
    u = insulated_u_value(c, conductivity=0.036, thickness_mm=50)
    bare = 1.0 / (0.17 + 0.2 / 1.6 + 0.050 / 0.036)
    assert u == pytest.approx(round(bare, 4))


def test_construction_without_layers_returns_none():
    assert insulated_u_value({"id": "C1", "layers": []}, conductivity=0.036,
                             thickness_mm=100) is None


def test_zero_conductivity_layers_are_skipped_not_infinite():
    """⚠️ 0 으로 나누면 죽는다. 물성이 빠진 층은 저항 0 으로 본다."""
    c = {"id": "C1", "layers": [{"conductivity": 0, "thickness": 100},
                                {"conductivity": 0.03, "thickness": 100,
                                 "isInsulation": True}]}
    assert insulated_u_value(c, conductivity=0.036, thickness_mm=100) is not None


def test_no_stale_construction_level_override_remains():
    """구성 단위 키를 남겨 두면 조립부가 그것으로 면별 값을 덮어쓴다."""
    payload = _payload([{"id": "S1", "constructionRef": "C1"}],
                       constructions=[_construction("C1", 0.030)],
                       overrides={"S1": {"tier": "premium", "thickness": 150}})
    v = build_variant_payload(payload, "insulation")
    assert "insulationOverrides" not in v
