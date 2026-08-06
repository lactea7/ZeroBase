"""추천 대안의 **변형 페이로드**와 **정량 영향** — 순수 함수만 둔다.

`ep_simulator._build_variant_payload` / `_evaluate_alternatives` 안에 있던 것을
옮겼다. 순수 이동이며 규칙을 바꾸지 않았다. 재시뮬레이션 호출(부수효과)은
`ep_simulator` 에 남는다 — 여기 두면 순환 import 가 되고 시험도 못 붙인다.

⚠️ 여기서 `None` 을 돌려주면 그 추천은 **재시뮬레이션 자체를 건너뛴다.** 즉
"효과 없음"으로 화면에 나간다. 조건 하나만 틀려도 조용히 그렇게 된다.

⚠️ 적용 규칙은 프런트(`utils/recommendationActions.js`)와 **같아야** 한다.
어긋나면 "적용 시 실제 차액" 원칙이 깨진다 — 화면에 예고한 효과와 실제 적용
결과가 달라진다.
"""
import copy
from typing import Any, Dict, Optional

# 유리 제품 ID — 하향/상향의 목표 사양
GLAZING_STANDARD_DOUBLE = 42     # 일반 복층
GLAZING_HIGH_LOWE_AR = 154       # 고성능 Low-E + Ar 복층 (U 1.32 / SHGC 0.34)

# 단열재 제품 ID 와 **실제 제품 열전도율**.
# ⚠️ tier 대표값(standard 0.055)이 아니라 실제 적용 제품 물성을 쓴다.
# 프런트가 적용하는 값과 같아야 예고 효과와 실제 결과가 일치한다.
INSULATION_STANDARD_ID = 1       # 비드법 1종 1호
INSULATION_STANDARD_K = 0.036
INSULATION_HIGH_ID = 2           # 비드법 1종 2호
INSULATION_HIGH_K = 0.031

DEFAULT_THICKNESS_MM = 100

# 하향 대상 판정 경계 (W/m·K).
# 이 값 이하면 "이미 좋은 단열" → 하향 여지가 있고, 초과면 "부실 단열" → 상향 대상.
GOOD_INSULATION_K = 0.045


def _has_glass(surface: Dict[str, Any]) -> bool:
    """유리가 있는 면인가.

    ⚠️ `type` 만 보면 창이 WWR 로만 표현된 벽을 놓친다 — gbXML 파서가 창을 별도
    면으로 만들 때도, 벽의 창면적비로 줄 때도 있다.
    """
    return bool(
        surface.get("type") in ("Window", "Skylight")
        or surface.get("glazingId") is not None
        or ((surface.get("wwr") or 0) > 0 and "wall" in (surface.get("type") or "").lower())
    )


def _swap_glazing(payload: Dict[str, Any], target_id: int) -> Optional[Dict[str, Any]]:
    """유리 있는 면을 전부 `target_id` 로 교체. 바뀐 게 없으면 None."""
    surfaces = copy.deepcopy(payload.get("surfaces", []))
    changed = 0
    for s in surfaces:
        if _has_glass(s) and s.get("glazingId") != target_id:
            s["glazingId"] = target_id   # glazingId 가 windowU 보다 우선한다
            changed += 1
    if not changed:
        return None
    variant = dict(payload)
    variant["surfaces"] = surfaces
    return variant


def _swap_insulation(payload: Dict[str, Any], *, from_tiers, to_tier: str,
                     to_id: int, to_k: float, bare_matches) -> Optional[Dict[str, Any]]:
    """단열 등급 교체.

    두 갈래로 대상을 찾는다.
      ① 사용자가 이미 등급을 지정한 면(`constructionOverrides`) → `from_tiers` 에 걸리면 교체
      ② 지정이 없는 면 → 원 구성의 단열층 열전도율을 `bare_matches` 로 판정

    `insulationOverrides` 는 시뮬 진입부에서 `constructionRef` 기준으로 U 값을
    재계산하는 데 쓴다 — 면 단위 override 만으로는 구성 자체가 안 바뀐다.
    """
    surfaces = copy.deepcopy(payload.get("surfaces", []))
    constructions = {c.get("id"): c
                     for c in (payload.get("materials", {}) or {}).get("constructions", [])}
    overrides = copy.deepcopy(payload.get("constructionOverrides", {}) or {})
    insul_overrides: Dict[Any, Dict[str, Any]] = {}
    changed = 0

    for s in surfaces:
        s_id = s.get("id")
        c_ref = s.get("constructionRef") or s.get("constructionId")
        existing = overrides.get(s_id)

        if existing and existing.get("tier") in from_tiers:
            thickness = existing.get("thickness", DEFAULT_THICKNESS_MM)
        elif not existing and c_ref in constructions:
            layer = next((l for l in constructions[c_ref].get("layers", [])
                          if l.get("isInsulation")), None)
            if not layer or not bare_matches(layer.get("conductivity")):
                continue
            thickness = layer.get("thickness") or DEFAULT_THICKNESS_MM
        else:
            continue

        overrides[s_id] = {"insulationId": to_id, "tier": to_tier, "thickness": thickness}
        if c_ref:
            insul_overrides[c_ref] = {"tier": to_tier, "thickness": thickness,
                                      "conductivity": to_k}
        changed += 1

    if not changed:
        return None
    variant = dict(payload)
    variant["surfaces"] = surfaces
    variant["constructionOverrides"] = overrides
    variant["insulationOverrides"] = insul_overrides
    return variant


def build_variant_payload(payload: Dict[str, Any], rec_type: str) -> Optional[Dict[str, Any]]:
    """추천 1건을 적용한 시뮬레이션 페이로드. 열모델이 안 바뀌면 None.

    None 을 돌려주는 경우는 두 가지이고 뜻이 다르다.
      · 애초에 열모델을 안 건드리는 대안(hvac 표준 하향·hvac_scope·led) — 재시뮬레이션이 무의미
      · 바꿀 대상이 하나도 없는 경우 — 이미 그 사양이거나 해당 면이 없다
    둘 다 "에너지 변화 0" 으로 표기된다.
    """
    project_data = payload.get("projectData", {}) or {}

    # ── 하향(비용 절감) 변형 ──
    if rec_type == "window":
        return _swap_glazing(payload, GLAZING_STANDARD_DOUBLE)

    if rec_type == "insulation":
        return _swap_insulation(
            payload, from_tiers=("premium", "high"), to_tier="standard",
            to_id=INSULATION_STANDARD_ID, to_k=INSULATION_STANDARD_K,
            bare_matches=lambda k: (k or 1.0) <= GOOD_INSULATION_K)

    if rec_type == "hvac" and project_data.get("geothermalApplied"):
        variant = dict(payload)
        variant["projectData"] = {**project_data, "geothermalApplied": False}
        return variant

    # ── 상향(성능 개선) 변형 — 전부 열모델이 바뀌므로 재시뮬레이션 필수 ──
    if rec_type == "hvac_upgrade":
        if project_data.get("hvacUpgradeActive"):
            return None
        variant = dict(payload)
        # resolve_hvac_equipment 가 1등급 신형 COP 로 전환한다
        variant["projectData"] = {**project_data, "hvacUpgradeActive": True}
        return variant

    if rec_type == "window_upgrade":
        return _swap_glazing(payload, GLAZING_HIGH_LOWE_AR)

    if rec_type == "insulation_upgrade":
        return _swap_insulation(
            payload, from_tiers=("standard", "basic"), to_tier="high",
            to_id=INSULATION_HIGH_ID, to_k=INSULATION_HIGH_K,
            bare_matches=lambda k: (k or 0) > GOOD_INSULATION_K)

    return None


def net_effect(saved_cost: float, annual_bill_delta: float, *,
               discount_rate: float, utility_inflation: float, years: int) -> int:
    """대안 적용의 분석기간 순효과(원).

    공사비 절감 − 운영비 증가분의 현재가치 합. 양수면 하향해도 경제적으로 이득,
    음수면 절감액보다 운영비 손실이 크다.
    """
    pv_extra = sum(annual_bill_delta * ((1 + utility_inflation) ** y) / ((1 + discount_rate) ** y)
                   for y in range(1, years + 1))
    return int(saved_cost - pv_extra)


def payback_years(capital_delta: float, annual_bill_delta: float) -> Optional[float]:
    """단순 회수기간(년).

    ⚠️ 공사비가 **늘고** 운영비가 **줄** 때만 뜻이 있다(상향 대안의 핵심 지표).
    반대 방향이면 회수 개념이 성립하지 않으므로 None — 0 이나 음수를 내보내면
    화면에서 "즉시 회수"로 읽힌다.
    """
    if annual_bill_delta < 0 and capital_delta > 0:
        return round(capital_delta / (-annual_bill_delta), 1)
    return None
