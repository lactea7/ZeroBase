"""용도별 에너지 매트릭스·1차에너지·CO₂·ZEB 자립률.

⚠️ **economics 가 아니라 domain 이다.** 요금과 무관한 물리·정책 지표이므로
나중에 실측 CSV 나 다른 엔진 결과에도 같은 계산을 쓸 수 있어야 한다.
여기에는 요율·자본비·현금흐름이 오지 않는다.

에너지원 계수(1차·CO₂)는 인자로 받는다 — 열원별 값은 요금표와 함께 관리되므로
`economics/tariffs.HEAT_SOURCE_DB` 에 있고, 이 모듈은 그것을 알 필요가 없다.
"""
from typing import Dict, Mapping

from src.domain.models import (
    AnnualEnergySummary,
    CategoryMetric,
    EnergyCategory,
    EnergyMetrics,
)

# 전기 1차에너지·CO₂ 계수
PRIMARY_FACTOR_ELEC = 2.75
CO2_FACTOR_ELEC = 0.466

# 열원 계수를 쓰는 용도. 나머지는 전기 계수를 쓴다.
HEAT_CATEGORIES = (EnergyCategory.HEATING, EnergyCategory.HOT_WATER)

# ZEB 등급 산정에서 빼는 용도.
#   equipment — 기기부하는 건축적 성능이 아니라 사용자 기기다
#   renewable — 상계 항목이라 분모에 들어가면 안 된다
ZEB_EXCLUDED = (EnergyCategory.EQUIPMENT, EnergyCategory.RENEWABLE)


def _per_area(value: float, area: float) -> float:
    return value / area if area > 0 else 0.0


def build_metrics(annual: AnnualEnergySummary, *, floor_area_m2: float,
                  pv_generation_kwh_m2: float,
                  heat_primary_factor: float,
                  heat_co2_factor: float) -> EnergyMetrics:
    """연간 집계 → 용도별 지표.

    `pv_generation_kwh_m2` 는 **이미 ㎡당으로 나뉜 값**이며 매트릭스에는 음수로 들어간다
    (상계 항목이라 수요·소비 합계에서 빠진다).
    """
    a = floor_area_m2

    # req/con 이 같은 용도가 있다 — 조명·기기는 전력이 곧 요구량이다.
    raw: Dict[EnergyCategory, tuple] = {
        EnergyCategory.HEATING: (annual.heating_requirement_kwh, annual.heating_consumption_kwh),
        EnergyCategory.COOLING: (annual.cooling_requirement_kwh, annual.cooling_consumption_kwh),
        EnergyCategory.HOT_WATER: (annual.dhw_requirement_kwh, annual.dhw_consumption_kwh),
        EnergyCategory.LIGHTING: (annual.lighting_kwh, annual.lighting_kwh),
        EnergyCategory.VENTILATION: (annual.ventilation_requirement_kwh,
                                     annual.ventilation_consumption_kwh),
        EnergyCategory.EQUIPMENT: (annual.equipment_kwh, annual.equipment_kwh),
    }

    by_category: Dict[EnergyCategory, CategoryMetric] = {}
    for cat, (req, con) in raw.items():
        by_category[cat] = CategoryMetric(
            requirement_kwh_m2=round(_per_area(req, a), 1),
            consumption_kwh_m2=round(_per_area(con, a), 1),
        )
    pv = round(pv_generation_kwh_m2, 1)
    by_category[EnergyCategory.RENEWABLE] = CategoryMetric(
        requirement_kwh_m2=-pv, consumption_kwh_m2=-pv)

    # ── 1차에너지·CO₂ ──
    # ⚠️ 예전에는 프런트가 **모든 항목에 전기계수**를 곱해, 지역난방·가스를 고르면
    # 상세 표 합계와 요약 카드가 서로 달랐다. 계수 적용은 여기서만 하고 프런트는
    # 받은 값을 그대로 표시한다.
    enriched: Dict[EnergyCategory, CategoryMetric] = {}
    for cat, m in by_category.items():
        pf, cf = ((heat_primary_factor, heat_co2_factor) if cat in HEAT_CATEGORIES
                  else (PRIMARY_FACTOR_ELEC, CO2_FACTOR_ELEC))
        enriched[cat] = CategoryMetric(
            requirement_kwh_m2=m.requirement_kwh_m2,
            consumption_kwh_m2=m.consumption_kwh_m2,
            primary_energy_kwh_m2=round(m.consumption_kwh_m2 * pf, 1),
            # 신재생은 배출이 없다
            co2_kg_m2=0.0 if cat is EnergyCategory.RENEWABLE
            else round(m.consumption_kwh_m2 * cf, 2),
            # 등급 산정용 — 기기·신재생 제외. 합계가 primary_energy_kwh_m2 와 맞아야 한다
            grade_primary_energy_kwh_m2=(0.0 if cat in ZEB_EXCLUDED
                                         else round(m.consumption_kwh_m2 * pf, 1)),
        )

    return EnergyMetrics(
        by_category=enriched,
        primary_energy_kwh_m2=round(_grade_primary(enriched, heat_primary_factor), 1),
        co2_kg_m2=round(_total_co2(enriched, heat_co2_factor), 2),
        renewable_independence_pct=_independence(enriched),
        floor_area_m2=a,
    )


def _grade_primary(cats: Mapping[EnergyCategory, CategoryMetric],
                   heat_primary_factor: float) -> float:
    """등급 산정용 1차에너지 — 기기·신재생 제외."""
    elec = sum(m.consumption_kwh_m2 for c, m in cats.items()
               if c not in ZEB_EXCLUDED and c not in HEAT_CATEGORIES)
    heat = sum(m.consumption_kwh_m2 for c, m in cats.items() if c in HEAT_CATEGORIES)
    return elec * PRIMARY_FACTOR_ELEC + heat * heat_primary_factor


def _total_co2(cats: Mapping[EnergyCategory, CategoryMetric], heat_co2_factor: float) -> float:
    """CO₂ — **기기를 포함**한다(실제 배출이므로). 신재생만 제외."""
    elec = sum(m.consumption_kwh_m2 for c, m in cats.items()
               if c is not EnergyCategory.RENEWABLE and c not in HEAT_CATEGORIES)
    heat = sum(m.consumption_kwh_m2 for c, m in cats.items() if c in HEAT_CATEGORIES)
    return elec * CO2_FACTOR_ELEC + heat * heat_co2_factor


def _independence(cats: Mapping[EnergyCategory, CategoryMetric]) -> float:
    """ZEB 에너지자립률(%). 분모는 **5대 에너지**(기기·신재생 제외)다."""
    denominator = sum(m.consumption_kwh_m2 for c, m in cats.items() if c not in ZEB_EXCLUDED)
    if denominator <= 0:
        return 0.0
    renewable = abs(cats[EnergyCategory.RENEWABLE].consumption_kwh_m2)
    return min(100.0, renewable / denominator * 100.0)
