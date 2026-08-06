"""개선 대안 권고 생성.

`LCCAnalyzer._build_recommendations()` 에서 옮겼다. 순수 이동이며 규칙을 바꾸지 않았다.

⚠️ 여기서는 **대안을 제시**만 한다. 정량 효과(에너지·실공사비·회수기간)는
`ep_simulator` 가 대안을 재시뮬레이션해 채운다 — 이 모듈은 그것을 모른다.
"""


def build_recommendations(*, cost_db, mapped_window_name, window_cost,
                          total_window_area, detailed_insulation_costs,
                          is_geothermal, hvac_cost, hvac_capacity_kw,
                          hvac_unit_cost, hvac_exclude_non_habitable,
                          non_hab_share, led_cost, led_saving, led_fixture_count,
                          led_reduction_active, cooling_grade="grade3",
                          heating_age="new", hvac_upgraded=False):
    """개선 대안 추천 목록 생성 — 양방향. 예산 입력 여부와 무관하게 항상 생성한다.

    · 하향(direction 없음): 공사비 절감 — 예산 초과 대응. saved_cost = 적용 시 실제 차액.
    · 상향(direction="upgrade"): kWh/운영비 절감 — 노후 설비 교체·단열/창호 상향.
      정량 효과(에너지·실공사비·회수기간)는 ep_simulator의 대안 재시뮬레이션(impact)이 산출.
    예산 초과 여부에 따른 강조는 프론트가 target_budget/capital_cost로 판단한다.
    각 대안은 이미 적용된 상태면 반복 제시하지 않는다.
    """
    recommendations = []

    if '고성능' in mapped_window_name or 'premium' in mapped_window_name.lower():
        std_price = cost_db.get("window_tiers", {}).get("standard", {}).get("avg", 180000)
        saved_cost = window_cost - (total_window_area * std_price)
        if saved_cost > 0:
            recommendations.append({
                "type": "window",
                "title": "창호 등급 하향 (Premium → Standard)",
                "description": "최상급 창호 대신 일반 복층 유리로 변경하면 공사비를 크게 절감할 수 있습니다.",
                "saved_cost": int(saved_cost),
                "performance_note": "창호 U값 상승으로 냉난방 부하·운영비가 증가합니다 — 적용 전 재시뮬레이션 권장"
            })
    elif '중성능' in mapped_window_name or 'high' in mapped_window_name.lower():
        std_price = cost_db.get("window_tiers", {}).get("standard", {}).get("avg", 180000)
        saved_cost = window_cost - (total_window_area * std_price)
        if saved_cost > 0:
            recommendations.append({
                "type": "window",
                "title": "창호 등급 하향 (High → Standard)",
                "description": "로이 복층유리 대신 일반 복층 유리로 변경하여 예산을 아낄 수 있습니다.",
                "saved_cost": int(saved_cost),
                "performance_note": "창호 U값 상승으로 냉난방 부하·운영비가 증가합니다 — 적용 전 재시뮬레이션 권장"
            })

    high_tier_insul_cost = 0
    std_insul_price = cost_db.get("insulation_tiers", {}).get("standard", {}).get("avg", 15000)
    std_insul_cost_sum = 0
    for d in detailed_insulation_costs or []:
        if '고성능' in d["tier"] or 'premium' in d["tier"].lower() or '중성능' in d["tier"] or 'high' in d["tier"].lower():
            high_tier_insul_cost += d["cost"]
            std_insul_cost_sum += d["area"] * std_insul_price

    if high_tier_insul_cost > std_insul_cost_sum:
        recommendations.append({
            "type": "insulation",
            "title": "단열재 사양 하향 (일반 등급 EPS)",
            "description": "고성능 단열재 대신 일반 등급 EPS(비드법 1종 1호, λ0.036)로 변경해 초기 비용을 줄입니다.",
            "saved_cost": int(high_tier_insul_cost - std_insul_cost_sum),
            "performance_note": "외피 열관류율 상승으로 난방 요구량·CO₂가 증가합니다 — 적용 전 재시뮬레이션 권장"
        })

    if is_geothermal:
        # 지열 해제 시 절감액 = 지열 프리미엄(×2.2)분. 일반 시스템(×1.0)으로 환원되므로
        # saved = hvac_cost × (1.2/2.2). 설비비는 그대로 남고 프리미엄만 빠진다.
        recommendations.append({
            "type": "hvac",
            "title": "지열 난방 시스템 해제",
            "description": "초기 설치비가 높은 지열(GSHP) 시스템을 일반 시스템으로 변경하여 천공·지중 열교환기 비용을 절감합니다.",
            "saved_cost": int(hvac_cost * (1.2 / 2.2)),
            "performance_note": "열원 COP 하락(5.0→일반)으로 난방 운영비가 증가합니다 — 적용 전 재시뮬레이션 권장"
        })
    else:
        # 비지열: 고효율 설비(EHP·FCU·AHU)를 표준 개별 냉난방기(Generic, id 5)로 하향.
        # 설비비가 capital의 대부분을 차지하는 경우가 많아, 이 추천이 없으면 다른 항목을
        # 모두 적용해도 총액이 거의 안 줄던 문제를 해소한다. (이미 표준이면 절감 0 → 미표시)
        std_hvac_unit = cost_db["avg_prices"]["hvac_kw_system"].get(5, 1500000)
        if hvac_capacity_kw > 0 and hvac_unit_cost > std_hvac_unit:
            saved_hvac = hvac_capacity_kw * (hvac_unit_cost - std_hvac_unit)
            if saved_hvac > 0:
                recommendations.append({
                    "type": "hvac",
                    "title": "고효율 냉난방 설비 → 표준 설비로 변경",
                    "description": "고가의 개별 히트펌프(EHP)·팬코일(FCU) 대신 표준 개별 냉난방기로 변경하여 설비 공사비를 절감합니다.",
                    "saved_cost": int(saved_hvac),
                    "performance_note": "설비 효율(COP) 하락으로 냉난방 운영비가 증가할 수 있습니다"
                })

    # 이미 표준 설비여도 쓸 수 있는 대안: 비거주 구역(계단실·창고·기계실 등)을
    # 설비 범위에서 제외해 용량을 줄인다. 비거주 면적이 유의미할 때(3% 이상)만 제시.
    if (not is_geothermal and not hvac_exclude_non_habitable
            and non_hab_share >= 0.03 and hvac_cost > 0):
        recommendations.append({
            "type": "hvac_scope",
            "title": "비거주 구역 냉난방 설비 제외",
            "description": f"계단실·창고·기계실 등 비거주 구역(전체 면적의 약 {non_hab_share*100:.0f}%)을 설비 설치 범위에서 제외해 설비 용량과 공사비를 줄입니다.",
            "saved_cost": int(hvac_cost * non_hab_share),
            "performance_note": "해당 구역의 냉난방이 제공되지 않아 동파 방지 등 최소 온도 유지가 필요하면 부적합합니다"
        })

    # 절감액은 '적용 시 실제 차액'(led_saving)만 제시. 이미 적용됐거나 효과가 0이면 미표시.
    if led_cost > 0 and led_saving > 0:
        if led_fixture_count > 0:
            recommendations.append({
                "type": "led",
                "title": "LED 조명 교체 수량 축소 (50%)",
                "description": "직접 입력한 LED 교체 수량을 50% 축소하여 필수 구역만 우선 교체합니다.",
                "saved_cost": int(led_saving),
                "performance_note": "미교체 구역의 조명 전력 절감 효과가 사라져 운영비 절감액이 줄어듭니다"
            })
        elif not led_reduction_active:
            recommendations.append({
                "type": "led",
                "title": "LED 조명 부분 교체 (공용구역 제외)",
                "description": "계단실, 복도, 창고 등 공용 구역을 제외하고 주요 거주 구역 위주로 부분 교체합니다.",
                "saved_cost": int(led_saving),
                "performance_note": "공용 구역의 조명 전력 절감 효과는 제외되어 운영비 절감액이 줄어듭니다"
            })

    # ── 상향(성능 개선) 대안: kWh·운영비를 낮추는 방향 ──────────────────
    # 냉난방 설비 1등급 교체 (COP 향상). 이미 1등급 신형이 아니면 3등급(기본)도 제안 —
    # 3등급→1등급만으로 냉방 COP 3.3→4.0 (~20% 절감). 효과·회수기간은 재시뮬로 산출.
    is_old = cooling_grade in ("grade5", "old10", "old15") or heating_age in ("mid", "old")
    if (not hvac_upgraded) and (cooling_grade != "grade1" or heating_age != "new"):
        recommendations.append({
            "type": "hvac_upgrade",
            "direction": "upgrade",
            "title": ("노후 냉난방 설비 → 1등급 신형 교체" if is_old
                      else "냉난방 설비 1등급 고효율 교체"),
            "description": "현재 설비보다 효율(COP)이 높은 1등급 신형으로 교체해 냉난방 에너지를 줄입니다. "
                           "설비 교체비는 공사비에 이미 계상되어 있어(단가는 등급 무관 평균), "
                           "운영비 절감이 그대로 순이득이 됩니다.",
            "saved_cost": 0,
        })

    # 창호 상향: 일반/단층 → 고성능 Low-E 복층 (U≈1.3)
    if ('일반' in mapped_window_name or '단층' in mapped_window_name) and total_window_area > 0:
        prem_price = cost_db.get("window_tiers", {}).get("premium", {}).get("avg", 172610)
        added = int(total_window_area * prem_price - window_cost)
        recommendations.append({
            "type": "window_upgrade",
            "direction": "upgrade",
            "title": "창호 상향 (일반 → 고성능 Low-E 복층)",
            "description": "일반 복층유리를 고성능 Low-E+아르곤 복층(U≈1.3)으로 상향해 냉난방 손실을 줄입니다.",
            "saved_cost": 0,
            "added_cost": max(added, 0),   # 자재 단가 차액 추정 — 실공사비 변화는 impact가 대체
        })

    # 단열 상향: 일반/저성능 단열 부위 → 중성능(high, λ0.035)
    up_targets = [d for d in (detailed_insulation_costs or [])
                  if ('일반' in d["tier"] or '저성능' in d["tier"]
                      or 'standard' in d["tier"].lower() or 'basic' in d["tier"].lower())]
    if up_targets:
        high_price = cost_db.get("insulation_tiers", {}).get("high", {}).get("avg", 27000)
        added = sum(d["area"] * max(high_price - d["price"], 0) for d in up_targets)
        recommendations.append({
            "type": "insulation_upgrade",
            "direction": "upgrade",
            "title": "단열재 상향 (일반 → 중성능 등급)",
            "description": f"일반 등급 단열 부위 {len(up_targets)}곳을 중성능 단열재(λ 0.035)로 상향해 난방 손실을 줄입니다.",
            "saved_cost": 0,
            "added_cost": int(added),
        })

    return recommendations


