"""공사비 산정 — 창호·단열·LED·설비.

`LCCAnalyzer.calculate()` 안에 있던 것을 옮겼다. 순수 이동이며 계산식을 바꾸지 않았다.

여기 오면 안 되는 것: 현금흐름·NPV·권고. 이 모듈은 **"얼마를 들여 고치나"** 만 답한다.
운영비·절감액은 다루지 않는다.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from src.domain.models import CapitalCostResult

# LED 조명: 단가가 '개당(EA)' 이므로 면적은 등기구 개수로 환산해 적용한다.
LED_FIXTURE_AREA_M2 = 10.0   # 등기구 1개가 담당하는 바닥면적 (㎡/개)

# 한 공종이 이 비중을 넘으면 단가·물량 오매핑을 의심한다.
# (설비는 전면교체 시 정상적으로 클 수 있어 임계에서 제외한다)
TRADE_SHARE_WARNING_THRESHOLD = 0.6


@dataclass
class CapitalCostBreakdown:
    """공사비와 그 근거. 합계만 남기면 어떻게 나온 값인지 되짚을 수 없다."""
    result: CapitalCostResult
    mapped_window_name: str
    window_unit_price: float
    insulation_details: List[Dict[str, Any]]
    warnings: List[str]
    # 권고 생성이 산정 근거를 필요로 한다 — 다시 계산하게 두면 두 곳이 갈라진다
    hvac_unit_cost: float = 0.0
    non_habitable_share: float = 0.0
    led_saving: float = 0.0


def estimate_capital_cost(*, cost_db, surfaces, zones, materials,
                          total_area: float, total_window_area: float,
                          total_wall_area: float,
                          target_u: float, target_shgc: float,
                          led_fixture_count: int, led_reduction_active: bool,
                          is_geothermal: bool, hvac_capacity_kw: float,
                          hvac_exclude_non_habitable: bool = False,
                          hvac_upgrade_active: bool = False,
                          construction_overrides: Optional[dict] = None,
                          meter_fallback_notes: Optional[List[str]] = None,
                          target_budget: float = 0.0) -> CapitalCostBreakdown:
    """공종별 공사비를 산정한다."""
    # ⚠️ cost_analyzer 가 이 모듈을 import 하므로 상단에서 역참조하면 순환이 된다.
    from src.cost_analyzer import is_non_habitable

    construction_overrides = construction_overrides or {}
    meter_fallback_notes = meter_fallback_notes or []


    target_window_price, mapped_window_name = cost_db.match_window_price(target_u, target_shgc)

    window_cost = total_window_area * target_window_price

    # 단열 공사비 계산
    insulation_cost = 0.0
    detailed_insulation_costs = []

    for s in surfaces:
        s_id = s.get("id")
        s_area = s.get("area", 0.0)

        # 프론트엔드 캐시로 인해 area가 없을 경우 자체 계산 (긴급 패치)
        if s_area <= 0 and s.get("vertices"):
            try:
                from src.gbxml_parser import calculate_surface_area
                s_area = round(calculate_surface_area(s["vertices"]), 2)
            except Exception:
                pass

        s_type = s.get("type", s.get("surfaceType", ""))
        if s_area <= 0 or s_type in ["InteriorWall", "InteriorFloor", "Ceiling"]:
            continue

        has_insulation = False
        conductivity = None

        override = construction_overrides.get(s_id)
        if override and (override.get("isCustom") or override.get("insulationId") is not None):
            has_insulation = True
            # ⚠️ 함수 파라미터 target_u를 덮어쓰지 않도록 지역변수 사용
            surf_u = override.get("uValue", s.get("uValue", 0.4))

            if override.get("isCustom"):
                t_insul = override.get("insulThick", 100) / 1000.0
            else:
                t_insul = override.get("thickness", 100) / 1000.0

            # 단열층 열전도율 추정: λ = 두께 / 단열저항
            #   단열저항 ≈ 전체저항(1/U) − 표면열전달저항(0.17). 구조층은 보수적으로 무시.
            #   (기존 t_insul×U는 단위는 맞지만 λ를 체계적으로 과소평가 → 등급 과대평가)
            r_total = (1.0 / surf_u) if surf_u and surf_u > 0 else 0.0
            r_insul = max(r_total - 0.17, 0.1)
            conductivity = t_insul / r_insul if r_insul > 0 else 0.04
        else:
            c_id = s.get("constructionRef") or s.get("constructionId")
            if materials and "constructions" in materials:
                c = next((c for c in materials["constructions"] if c["id"] == c_id), None)
                if c:
                    for layer in c.get("layers", []):
                        if layer.get("isInsulation"):
                            has_insulation = True
                            conductivity = layer.get("conductivity", 0.04)
                            break

        override_tier = override.get("tier") if override else None

        if has_insulation and (conductivity is not None or override_tier is not None):
            price, tier_label = cost_db.match_insulation_price(conductivity, explicit_tier=override_tier)
            cost = s_area * price
            insulation_cost += cost
            detailed_insulation_costs.append({
                "surfaceId": s_id,
                "area": s_area,
                "price": price,
                "cost": int(cost),
                "tier": tier_label
            })

    if insulation_cost == 0.0 and total_wall_area > 0:
        insulation_cost = total_wall_area * cost_db.cost_db["avg_prices"]["insulation"]

    # LED 공사 면적 산출: 비거주 구역(계단실, 기계실, 창고, 엘리베이터 등)은
    # 조명 밀도가 낮으므로 해당 면적의 30%만 LED 공사 대상으로 반영
    habitable_area = 0.0
    non_habitable_area = 0.0
    for z in zones:
        # gbXML 파서는 존 용도명을 'id'에 담는다('name' 미발급) → is_non_habitable이 폴백 처리
        z_area = z.get('area', 0)
        if not z_area:
            z_area = total_area / max(len(zones), 1)
        if is_non_habitable(z):
            non_habitable_area += z_area
        else:
            habitable_area += z_area
    # LED 비용은 '등기구 개당(EA)' 단가로 통일 (면적 기준일 때도 개수로 환산)
    led_per_ea = cost_db.cost_db["avg_prices"].get("led_per_ea", 85000)
    if led_fixture_count > 0:
        # 사용자가 직접 입력한 등기구 수량 기준
        led_cost = led_fixture_count * led_per_ea
    else:
        if led_reduction_active:
            led_effective_area = habitable_area  # 공용구역 전체 제외
        else:
            led_effective_area = habitable_area + (non_habitable_area * 0.3)
        # 안전장치: 면적이 0이면 전체 면적 비율을 조정하여 기본값으로 사용
        if led_effective_area < 1.0:
            led_effective_area = total_area * (0.5 if led_reduction_active else 0.7)
        # 면적 → 등기구 개수 환산(약 LED_FIXTURE_AREA_M2 ㎡당 1개) 후 개당 단가 적용
        est_fixtures = led_effective_area / LED_FIXTURE_AREA_M2
        led_cost = est_fixtures * led_per_ea

    # 추천 카드에 표시할 LED 절감액은 '적용 시 실제 차액'으로 계산한다.
    # (기존 led_cost×0.3은 비거주 면적의 30% 몫만 빠지는 실제 효과를 ~3배 과대표시했음)
    if led_fixture_count > 0:
        led_saving = led_cost * 0.5   # 수량 50% 축소 → 비용도 정확히 50% 감소
    elif not led_reduction_active:
        reduced_area = habitable_area if habitable_area >= 1.0 else total_area * 0.5
        led_cost_if_reduced = (reduced_area / LED_FIXTURE_AREA_M2) * led_per_ea
        led_saving = max(led_cost - led_cost_if_reduced, 0.0)
    else:
        led_saving = 0.0


    main_hvac_sys = 5
    for z in zones:
        if z.get("isConditioned", True):
            main_hvac_sys = z.get('hvacSystemId', 5)
            break

    hvac_unit_cost = cost_db.cost_db["avg_prices"]["hvac_kw_system"].get(main_hvac_sys, cost_db.cost_db["avg_prices"]["hvac_kw_default"])
    # 지열(GSHP)은 천공·지중 열교환기 비용으로 일반 시스템보다 고가 → 프리미엄(×2.2) 반영
    if is_geothermal:
        hvac_unit_cost = int(hvac_unit_cost * 2.2)

    # 설비비는 항상 표시한다(건물에는 냉난방 설비가 필수). 토글 게이팅 제거 →
    # 실제 산정된 설비 용량(hvac_capacity_kw) × 시스템 단가로 일관 산출.
    hvac_cost = hvac_capacity_kw * hvac_unit_cost

    # 비거주 구역(계단실·창고·기계실 등) 설비 제외 옵션: 냉난방 용량은 공조 대상
    # 바닥면적에 대략 비례하므로, 비거주 면적 비율만큼 설비 규모(비용)를 축소한다.
    _total_zone_area = habitable_area + non_habitable_area
    non_hab_share = (non_habitable_area / _total_zone_area) if _total_zone_area > 0 else 0.0
    hvac_exclude_non_habitable = hvac_exclude_non_habitable
    if hvac_exclude_non_habitable and non_hab_share > 0:
        hvac_cost *= (1.0 - non_hab_share)

    total_capital_cost = window_cost + insulation_cost + led_cost + hvac_cost

    # 공사비 비중 새너티 점검: 단가/물량 오매핑으로 한 공종이 비정상 지배하면 경고
    # (설비는 전면교체 시 정상적으로 클 수 있어 임계 제외)
    # DB 품질 이슈(가드 발동 등) + 미터 폴백을 사용자에게 노출
    cost_warnings = list(cost_db.load_warnings) + meter_fallback_notes
    if total_capital_cost > 0:
        _shares = {"창호": window_cost, "단열": insulation_cost, "LED": led_cost}
        for _label, _val in _shares.items():
            _share = _val / total_capital_cost
            if _share > TRADE_SHARE_WARNING_THRESHOLD:
                _msg = f"{_label} 공사비가 전체의 {_share*100:.0f}%로 과도합니다 — 단가/물량 매핑 점검 필요"
                cost_warnings.append(_msg)
                print(f"  ⚠️ 비중 점검: {_msg}")

    return CapitalCostBreakdown(
        result=CapitalCostResult(
            by_item={"window": window_cost, "insulation": insulation_cost,
                     "led": led_cost, "hvac": hvac_cost},
            total_won=total_capital_cost,
            budget_won=target_budget or None,
        ),
        mapped_window_name=mapped_window_name,
        window_unit_price=target_window_price,
        insulation_details=detailed_insulation_costs,
        warnings=cost_warnings,
        hvac_unit_cost=hvac_unit_cost,
        non_habitable_share=non_hab_share,
        led_saving=led_saving,
    )
