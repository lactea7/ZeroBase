"""피크 전력과 냉난방 설비 용량 산정.

⚠️ **economics 가 아니라 domain 이다.** 요금표가 아니라 물리량에서 나오는 값이고,
전기 기본요금(economics)과 설비 공사비(economics) 양쪽이 이것을 **입력으로** 받는다.

`LCCAnalyzer.calculate()` 안에 있던 것을 옮겼다. 순수 이동이며 산식을 바꾸지 않았다.
"""
from typing import Sequence

# 동시사용률(Diversity Factor). 모든 부하가 같은 순간에 최대가 되지는 않는다.
DIVERSITY_FACTOR = 0.8

# 피크를 산출하지 못했을 때의 면적 기반 폴백 (kW/㎡)
FALLBACK_PEAK_KW_PER_M2 = 0.05

# 설비 용량 클램프 (kW/㎡). 현실 설계부하 범위다.
# ⚠️ 일부 gbXML 모델(폐합 갭·과대 침기)은 현열부하가 200 W/㎡까지 치솟지만
# 실제 설비는 그렇게 사이징하지 않는다. 단열 좋은 건물은 하한 미만이라 설비비가
# 싸지는데 그건 정상이다.
MIN_HVAC_KW_PER_M2 = 0.04
MAX_HVAC_KW_PER_M2 = 0.10

# 설비 용량 산정에 쓰는 백분위.
# ⚠️ 순간 최대값(.max())을 쓰면 셋백 복귀 시 용량제한 없이 치솟아(예: 228 W/㎡)
# 설비비를 크게 과대평가한다.
HVAC_SIZING_PERCENTILE = 99

# 환기 팬 전력 환산 — 질량유량(kg/s) → 전력(W)
#
# ⚠️ 여기는 **순간 유량 → 순간 전력**이다. 시간 환산(3600)을 넣으면 안 된다.
# 에너지로 바꾸는 건 `energyplus/outputs.ventilation_energy_kwh` 쪽이고,
# 같은 SFP 상수를 쓴다. 두 곳의 값이 갈라지면 피크와 사용량이 어긋난다.
_AIR_DENSITY = 1.2
_VENT_SFP_KW_PER_M3S = 0.8       # 비팬동력 [kW/(m³/s)] — kWh/m³ 가 아니다


def peak_electric_kw(*, base_demand_w: Sequence[float],
                     cooling_rate_w: Sequence[float],
                     heating_rate_w: Sequence[float],
                     ventilation_kg_s: Sequence[float],
                     floor_area_m2: float, np_mod) -> float:
    """계약전력 산정용 피크(kW). 기본요금이 여기에 곱해진다."""
    vent_w = np_mod.array(ventilation_kg_s) / _AIR_DENSITY * _VENT_SFP_KW_PER_M3S * 1000.0
    series = (np_mod.array(base_demand_w) + np_mod.array(cooling_rate_w)
              + np_mod.array(heating_rate_w) + vent_w) / 1000.0
    peak = float(series.max()) * DIVERSITY_FACTOR if len(series) else 0.0
    return peak if peak > 0 else floor_area_m2 * FALLBACK_PEAK_KW_PER_M2


def hvac_capacity_kw(*, heating_requirement_kwh: Sequence[float],
                     cooling_requirement_kwh: Sequence[float],
                     floor_area_m2: float, np_mod) -> float:
    """냉난방 설비 용량(kW) — 설비비 산정용.

    시간당 현열부하(kWh/h ≈ kW)의 99퍼센타일로 잡는다. PTHP·이상부하 양 경로가
    **같은 현열부하 시계열**을 쓰므로 시스템 선택과 무관하게 일관된다.
    """
    if len(heating_requirement_kwh):
        heat = float(np_mod.percentile(heating_requirement_kwh, HVAC_SIZING_PERCENTILE))
        cool = float(np_mod.percentile(cooling_requirement_kwh, HVAC_SIZING_PERCENTILE))
    else:
        heat = cool = 0.0
    capacity = max(heat, cool)
    return min(max(capacity, floor_area_m2 * MIN_HVAC_KW_PER_M2),
               floor_area_m2 * MAX_HVAC_KW_PER_M2)
