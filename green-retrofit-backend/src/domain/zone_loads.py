"""존 내부발열 — 사용자 입력 · 아키타입 기본값 · 콘센트를 하나로 정리한다.

⚠️ **domain 이지 simulation 이 아니다.** IDF 객체가 아니라 물리량(W/㎡, m³/s)을
내고, 냉난방 부하의 출발점이 된다. 용호동에서 조명+기기가 44.5 kWh/㎡·년으로
난방(19.0)보다 크다 — 여기가 틀리면 결과가 통째로 틀어진다.

`generate_idf_and_simulate` 의 존 루프 안에 있던 것을 옮겼다. 순수 이동이며
산식을 바꾸지 않았다.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional

#: 콘센트 부하를 기기부하에 **더할지(sum) 큰 쪽만 쓸지(max)**.
#
# ⚠️ 기본은 `max` 다. 두 값은 **같은 물리량의 서로 다른 추정치**이기 때문이다.
#   · `equipmentPower` — 아키타입 기본값(사무실 12 W/㎡)은 ASHRAE/DOE 통상값이고,
#     그 정의가 **콘센트(plug/receptacle) 부하**다. 별도 설비가 아니라 꽂아 쓰는 것 전체다.
#   · `calc_outlet_power_density()` — 콘센트 개수로 **같은 양**을 추정한다.
# 더하면 정의상 이중계산이다. 예전 기본값 `sum` 에서는 사무실이
# 12 + 최대 25 = **37 W/㎡** 까지 갔다.
#
# `sum` 은 `equipmentPower` 가 콘센트를 **제외한** 공정·특수기기 부하임을 사용자가
# 명시적으로 고른 경우에만 쓴다.
DEFAULT_OUTLET_LOAD_TYPE = "max"

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
    # ⚠️ `sum` 은 **사용자가 명시적으로 고른 경우에만** 이다. 기본은 `max` —
    # 두 값이 같은 물리량의 다른 추정치라 더하면 이중계산이다.
    load_type = zone.get("outletLoadType") or DEFAULT_OUTLET_LOAD_TYPE
    # ⚠️ `float()` 로 고정한다. `max(12, 0.0)` 은 int 12 를 돌려주는데, 그러면
    # 부하 방식에 따라 IDF 에 `12` 와 `12.0` 이 갈려 적힌다(값은 같지만 골든이 반응).
    equipment = float(base_equipment + outlet_w_m2 if load_type == "sum"
                      else max(base_equipment, outlet_w_m2))

    return ZoneLoads(
        people_density=_or_default(zone, "peopleDensity", archetype_loads["people"]),
        lighting_w_m2=_or_default(zone, "lightingPower", archetype_loads["lighting"]),
        equipment_w_m2=equipment,
        outlet_w_m2=outlet_w_m2,
        outlet_load_type=load_type,
        dhw_litres_per_person_day=archetype_loads.get("dhw_lpd", 0.0),
    )
