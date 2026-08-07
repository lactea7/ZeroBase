"""존 내부발열 — 사용자 입력 · 아키타입 기본값 · 콘센트를 하나로 정리한다.

⚠️ **domain 이지 simulation 이 아니다.** IDF 객체가 아니라 물리량(W/㎡, m³/s)을
내고, 냉난방 부하의 출발점이 된다. 용호동에서 조명+기기가 44.5 kWh/㎡·년으로
난방(19.0)보다 크다 — 여기가 틀리면 결과가 통째로 틀어진다.

`generate_idf_and_simulate` 의 존 루프 안에 있던 것을 옮겼다. 순수 이동이며
산식을 바꾸지 않았다.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

#: 콘센트 부하를 아키타입 기기부하에 **더할지(sum) 큰 쪽만 쓸지(max)**.
#
# ⚠️ 기본이 `sum` 인데, 아키타입 기기부하(사무실 12 W/㎡)가 이미 일반 콘센트를
# 포함한 값이라면 **이중계산**이다. `outletCount` 가 있는 파일에서는
# 12 + 최대 25 = 37 W/㎡ 까지 간다.
# 용호동은 20개 존 전부 `outletCount` 가 없어 이 경로를 타지 않았지만,
# 위험 자체는 실재한다. 아키타입 정의를 확인해 결정해야 한다.
DEFAULT_OUTLET_LOAD_TYPE = "sum"

SECONDS_PER_HOUR = 3600.0
LITRES_PER_M3 = 1000.0


@dataclass(frozen=True)
class ZoneLoads:
    """존 하나의 내부발열. 전부 면적당 값(W/㎡)이고 인원만 인/㎡ 다."""
    people_density: float = 0.0        # 인/㎡
    lighting_w_m2: float = 0.0
    equipment_w_m2: float = 0.0
    #: 기기부하에 포함된 콘센트 성분. 0 이면 콘센트 입력이 없었다는 뜻이다.
    outlet_w_m2: float = 0.0
    outlet_load_type: str = DEFAULT_OUTLET_LOAD_TYPE
    dhw_litres_per_person_day: float = 0.0

    @property
    def has_outlets(self) -> bool:
        return self.outlet_w_m2 > 0

    def dhw_peak_flow_m3_s(self, floor_area_m2: float,
                           daily_operating_hours: float) -> float:
        """급탕 최대 유량(m³/s).

        ⚠️ 이 유량은 운영 스케줄로 **변조**된다. 그래서 하루 사용량이 맞으려면
        `1인당 사용량 × 인원 ÷ (하루 운영시간 적분)` 이어야 한다.
        예전에는 `/3600` 으로 "1시간 가동"을 가정해 스케줄 적분만큼(약 10배)
        과다했다.
        """
        people = floor_area_m2 * self.people_density
        if people <= 0 or daily_operating_hours <= 0:
            return 0.0
        # ⚠️ 연산 **순서**를 원본 그대로 둔다. 수학적으로 같아도 부동소수점
        # 마지막 자리가 달라져 골든 IDF 가 반응한다(실제로 잡혔다).
        return (people * (self.dhw_litres_per_person_day / LITRES_PER_M3)
                / (daily_operating_hours * SECONDS_PER_HOUR))


def _or_default(zone: Dict[str, Any], key: str, fallback: float) -> float:
    """사용자 입력 우선. **`None` 일 때만** 기본값으로 간다.

    ⚠️ `or` 를 쓰면 사용자가 명시한 **0**(조명 없는 창고 등)이 기본값으로 바뀐다.
    """
    value = zone.get(key)
    return fallback if value is None else value


def resolve(zone: Dict[str, Any], floor_area_m2: float,
            archetype_loads: Dict[str, Any], *,
            outlet_w_m2: float = 0.0,
            suppress_auto: bool = False) -> ZoneLoads:
    """존 + 아키타입 기본값 + 콘센트 → `ZoneLoads`.

    `outlet_w_m2` 는 `calc_outlet_power_density(zone, floor_area)` 의 결과다
    (호출자가 넘긴다 — 이 모듈은 콘센트 개수 해석 규칙을 몰라도 된다).

    ⚠️ `suppress_auto` 는 ASHRAE 140 전용이다. 140 은 내부발열을 사양대로
    못박는다(케이스 600 = 순수 현열 200 W). 용도별 자동 추정(인원·조명·기기·
    급탕·콘센트)이 섞이면 그 사양을 표현할 수 없다.
    """
    if suppress_auto:
        return ZoneLoads()

    base_equipment = _or_default(zone, "equipmentPower", archetype_loads["equipment"])
    load_type = zone.get("outletLoadType", DEFAULT_OUTLET_LOAD_TYPE)
    equipment = (max(base_equipment, outlet_w_m2) if load_type == "max"
                 else base_equipment + outlet_w_m2)

    return ZoneLoads(
        people_density=_or_default(zone, "peopleDensity", archetype_loads["people"]),
        lighting_w_m2=_or_default(zone, "lightingPower", archetype_loads["lighting"]),
        equipment_w_m2=equipment,
        outlet_w_m2=outlet_w_m2,
        outlet_load_type=load_type,
        dhw_litres_per_person_day=archetype_loads.get("dhw_lpd", 0.0),
    )
