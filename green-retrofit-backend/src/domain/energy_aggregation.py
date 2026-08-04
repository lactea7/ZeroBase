"""시계열 → 월별·연간 집계. **순수 합산만 한다.**

여기 오면 안 되는 것: 요금·요율·에너지원 배분·PV 자가소비 정책.
그것들은 "얼마를 썼나"가 아니라 "그 소비를 어떻게 값으로 바꾸나"이므로
`economics/` 의 몫이다.

엔진에도 의존하지 않는다 — `EnergyTimeSeries` 만 받으므로 나중에 실측 CSV 나
다른 엔진 결과에도 그대로 쓸 수 있다.
"""
from typing import Dict, List

from src.domain.models import AnnualEnergySummary, EnergyTimeSeries

# 급탕 배관 손실. 요구량 → 소비량 계수.
# ⚠️ 시계열의 `dhw_kwh` 에는 이미 이 값이 곱해져 있다. 요구량을 되돌릴 때 쓴다.
# (계약에 요구량/소비량을 따로 담도록 고치는 것이 더 낫다 — 별도 항목)
DHW_DISTRIBUTION_LOSS = 1.1

MONTH_LABELS = [f"{m}월" for m in range(1, 13)]


def _sum_by_month(values, months) -> List[float]:
    """월별 합계 12개. 값이 없으면 0."""
    out = [0.0] * 12
    for v, m in zip(values, months):
        if 1 <= m <= 12:
            out[m - 1] += float(v)
    return out


def monthly_breakdown(series: EnergyTimeSeries, total_area_m2: float,
                      ventilation_kwh=None) -> List[Dict[str, object]]:
    """화면용 월별 원단위(kWh/㎡).

    ⚠️ 난방은 **공간 난방만** 담는다. 급탕은 연중 발생하므로 별도 항목이다 —
    예전에는 난방에 급탕이 섞여 여름에도 난방값이 떠 보였다.
    """
    area = total_area_m2 if total_area_m2 > 0 else 1.0
    months = series.months
    heat = _sum_by_month(series.heating_consumption_kwh, months)
    cool = _sum_by_month(series.cooling_consumption_kwh, months)
    light = _sum_by_month(series.lighting_kwh, months)
    equip = _sum_by_month(series.equipment_kwh, months)
    dhw = _sum_by_month(series.dhw_kwh, months)

    return [{
        "name": MONTH_LABELS[i],
        "heating": round(heat[i] / area, 1),
        "cooling": round(cool[i] / area, 1),
        "lighting": round(light[i] / area, 1),
        "equipment": round(equip[i] / area, 1),
        "hotwater": round(dhw[i] / area, 1),
    } for i in range(12)]


def annual_summary(series: EnergyTimeSeries, ventilation_kwh) -> AnnualEnergySummary:
    """연간 절대량 집계.

    `ventilation_kwh` 는 환기 **처리 에너지 + 팬 전력**이다
    (`energyplus.outputs.ventilation_energy_kwh` 가 만든다).
    환기 요구량은 거기서 팬을 뺀 값이다 — 팬은 소비 쪽에만 붙는다.
    """
    def total(values) -> float:
        return float(sum(values))

    fan = total(series.fan_kwh)
    vent_con = float(sum(ventilation_kwh))
    dhw_con = total(series.dhw_kwh)

    return AnnualEnergySummary(
        heating_requirement_kwh=total(series.heating_requirement_kwh),
        cooling_requirement_kwh=total(series.cooling_requirement_kwh),
        heating_consumption_kwh=total(series.heating_consumption_kwh),
        cooling_consumption_kwh=total(series.cooling_consumption_kwh),
        # ⚠️ dhw_kwh 에는 배관손실이 이미 곱해져 있으므로 요구량은 되돌린다.
        dhw_requirement_kwh=dhw_con / DHW_DISTRIBUTION_LOSS,
        dhw_consumption_kwh=dhw_con,
        ventilation_requirement_kwh=vent_con - fan,
        ventilation_consumption_kwh=vent_con,
        lighting_kwh=total(series.lighting_kwh),
        equipment_kwh=total(series.equipment_kwh),
        fan_kwh=fan,
    )
