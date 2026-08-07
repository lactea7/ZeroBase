"""열원·등급·연식 → **HVAC 설비 계획**. 순수 함수만 둔다.

`generate_idf_and_simulate` 안에서 열원 매핑·이상부하 강제·COP 보정이 존 루프
직전에 얽혀 있던 것을 값 하나로 모았다. IDF 객체 생성은 여기 오지 않는다.

⚠️ 여기서 고른 모드가 **소비량 산출 방식 자체를 바꾼다**(`energyplus/outputs`):
  · pthp/fuel — EnergyPlus **미터 실측**을 그대로 쓴다
  · ideal     — 존별 요구량을 COP·효율로 나눈다
모드를 잘못 고르면 요구량과 소비량이 뒤섞인다.
"""
from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple

#: 열원 id → (EnergyPlus 연료명, 연소·열교환 효율).
#: 여기 없는 열원은 이상부하로 폴백한다.
FUEL_SYSTEMS: Dict[int, Tuple[str, float]] = {
    1:  ("NaturalGas", 0.87),    # 가스보일러 (콘덴싱 반영 평균 효율)
    4:  ("FuelOilNo2", 0.83),    # 등유보일러
    11: ("OtherFuel1", 0.95),    # 지역난방 (열교환 손실)
}

DEFAULT_HEAT_SOURCE = 11         # 미지정 시 지역난방
ELECTRIC_HEAT_SOURCE = 2         # 전기 열원 → 히트펌프

#: 지열은 **신설 전제**라 등급·연식 보정을 걸지 않는다. (냉방 COP, 난방 COP)
GEOTHERMAL_COPS = (5.0, 4.5)

FUEL_LABELS = {"NaturalGas": "가스보일러", "FuelOilNo2": "등유보일러",
               "OtherFuel1": "지역난방"}


@dataclass(frozen=True)
class HvacPlan:
    """어떤 설비를 어떤 성능으로 놓을지. **IDF 객체가 아니라 값이다.**"""
    mode: str                      # "pthp" | "fuel" | "ideal"
    fuel_type: Optional[str] = None
    fuel_efficiency: Optional[float] = None
    cooling_cop: float = 0.0       # WindowAC (fuel 모드)
    pthp_cooling_cop: float = 0.0
    pthp_heating_cop: float = 0.0
    is_geothermal: bool = False
    is_user_input: bool = False
    heat_source_id: int = DEFAULT_HEAT_SOURCE

    @property
    def uses_pthp(self) -> bool:
        return self.mode == "pthp"

    @property
    def uses_fuel(self) -> bool:
        return self.mode == "fuel"

    @property
    def needs_sizing(self) -> bool:
        """실기기는 autosize 를 쓰므로 사이징 계산이 필요하다."""
        return self.mode in ("pthp", "fuel")

    @property
    def fuel_label(self) -> str:
        return FUEL_LABELS.get(self.fuel_type, self.fuel_type or "")

    def describe(self) -> str:
        if self.mode == "pthp":
            return "PTHP 실기기(전기/지열)"
        if self.mode == "fuel":
            return (f"연료 보일러+개별냉방 실기기({self.fuel_type}, "
                    f"효율 {self.fuel_efficiency})")
        return "이상부하(폴백)"


def resolve(project_data: Dict[str, Any], equipment: Dict[str, Any], *,
            force_ideal_loads: bool = False) -> HvacPlan:
    """열원 설정 + 사용자 실기기 입력 → `HvacPlan`.

    `equipment` 는 `resolve_hvac_equipment(project_data)` 의 결과다
    (등급·연식 → COP·열화계수).

    ⚠️ `force_ideal_loads` 는 ASHRAE 140 전용이다. 140 은 **용량 무제한·효율
    100%** 의 이상부하를 요구하는데 실기기(PTHP/보일러)로는 그 사양을 표현할 수
    없다. 열원 설정과 무관하게 이상부하를 강제해야 참조값과 비교가 성립한다.
    """
    is_geothermal = bool(project_data.get("geothermalApplied", False))
    heat_source = int(project_data.get("heatSource", DEFAULT_HEAT_SOURCE))

    if force_ideal_loads:
        return HvacPlan(mode="ideal", is_geothermal=is_geothermal,
                        heat_source_id=heat_source,
                        is_user_input=bool(equipment.get("is_user_input")))

    use_pthp = is_geothermal or heat_source == ELECTRIC_HEAT_SOURCE
    if use_pthp:
        cool_cop, heat_cop = (GEOTHERMAL_COPS if is_geothermal
                              else equipment["pthp_cops"])
        return HvacPlan(mode="pthp",
                        pthp_cooling_cop=cool_cop, pthp_heating_cop=heat_cop,
                        cooling_cop=equipment["cool_cop"],
                        is_geothermal=is_geothermal, heat_source_id=heat_source,
                        is_user_input=bool(equipment.get("is_user_input")))

    fuel = FUEL_SYSTEMS.get(heat_source)
    if fuel is None:
        return HvacPlan(mode="ideal", cooling_cop=equipment["cool_cop"],
                        heat_source_id=heat_source,
                        is_user_input=bool(equipment.get("is_user_input")))

    fuel_type, base_eff = fuel
    # 보일러 연식 열화를 효율에 반영한다 — 성능은 세우는 순간이 아니라 지금이 기준이다.
    return HvacPlan(mode="fuel", fuel_type=fuel_type,
                    fuel_efficiency=round(base_eff * equipment["heat_factor"], 3),
                    cooling_cop=equipment["cool_cop"],
                    heat_source_id=heat_source,
                    is_user_input=bool(equipment.get("is_user_input")))
