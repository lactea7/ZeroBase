"""계층 사이를 오가는 **데이터 계약**.

왜 dict 대신 이걸 쓰나:
`cost_analyzer.calculate()` 는 743줄 안에서 CSV 파싱 → 월별 집계 → 에너지 매트릭스
→ 요금 → 자본비 → 현금흐름 → 권고를 한꺼번에 한다. 중간값이 전부 지역변수와 dict 라
파일만 나누면 **dict 키 의존성이 새 파일들 사이로 그대로 퍼진다.** 그러면 나눈 의미가
없고 오히려 추적이 어려워진다. 경계마다 계약을 먼저 못박고 그 위에서 코드를 옮긴다.

설계 원칙:
  - **단위를 이름에 박는다.** 이 코드베이스에서 단위 혼동으로 실제 오류가 났었다
    (내부발열 44.5 를 W/㎡ 로 읽었는데 실은 kWh/㎡·년이었다).
  - EnergyPlus 에 의존하지 않는다. 나중에 실측 CSV 나 다른 엔진 결과도 같은 계약으로
    흘릴 수 있어야 한다.
  - 파생값은 저장하지 않고 계산한다(합계·원단위 등). 저장하면 갱신 누락이 생긴다.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional

# 이 코드베이스에서 반복해서 필요한 환산. 매직넘버로 흩어놓지 않는다.
J_TO_KWH = 3_600_000.0


@dataclass(frozen=True)
class HourlyEnergy:
    """시뮬레이션이 낸 **시간별 물리량**. 요금·정책이 섞이기 전 단계다.

    `requirement`(요구량)와 `consumption`(소비량)을 구분하는 것이 핵심이다.
    요구량은 존이 필요로 한 열이고, 소비량은 그걸 만들려고 실제로 쓴 에너지다.
    (이상부하 모드에서는 둘이 같고, 실기기 모드에서는 COP·연소효율만큼 다르다)
    """
    months: List[int]                     # 각 행의 월 (1~12)
    hours: List[int]                      # 각 행의 시각 (0~23)

    heating_requirement_kwh: List[float]  # 존 난방 요구량
    cooling_requirement_kwh: List[float]  # 존 냉방 요구량
    heating_consumption_kwh: List[float]  # 난방 실소비(연료 또는 전기)
    cooling_consumption_kwh: List[float]  # 냉방 실소비(전기)
    heating_rate_w: List[float]           # 피크 산출용
    cooling_rate_w: List[float]

    lighting_kwh: List[float]
    equipment_kwh: List[float]
    dhw_kwh: List[float]
    fan_kwh: List[float]
    ventilation_kg_s: List[float]

    # 실기기 미터가 없어 추정으로 대체한 항목. **조용한 추정을 막기 위해 들고 다닌다.**
    fallback_notes: List[str] = field(default_factory=list)

    def __post_init__(self):
        n = len(self.months)
        for name in ("hours", "heating_requirement_kwh", "cooling_requirement_kwh",
                     "heating_consumption_kwh", "cooling_consumption_kwh",
                     "lighting_kwh", "equipment_kwh", "dhw_kwh"):
            got = len(getattr(self, name))
            if got != n:
                raise ValueError(f"HourlyEnergy 길이 불일치: {name} 이 {got}, months 는 {n}")

    @property
    def row_count(self) -> int:
        return len(self.months)

    @property
    def is_hourly(self) -> bool:
        """월별 요약이 아니라 시간별 데이터인가."""
        return self.row_count > 365


@dataclass(frozen=True)
class AnnualEnergySummary:
    """연간 집계. **원단위가 아니라 절대량**을 담는다 — 면적으로 나누는 것은
    표현 계층의 일이고, 여기서 나눠 두면 면적 기준이 바뀔 때 추적이 어려워진다."""
    heating_requirement_kwh: float
    cooling_requirement_kwh: float
    heating_consumption_kwh: float
    cooling_consumption_kwh: float
    lighting_kwh: float
    equipment_kwh: float
    dhw_kwh: float
    fan_kwh: float

    @property
    def total_consumption_kwh(self) -> float:
        return (self.heating_consumption_kwh + self.cooling_consumption_kwh
                + self.lighting_kwh + self.equipment_kwh + self.dhw_kwh + self.fan_kwh)


@dataclass(frozen=True)
class EnergyMetrics:
    """용도별 에너지·1차에너지·CO₂·자립률.

    ⚠️ **economics 가 아니라 domain 이다.** 요금과 무관한 물리·정책 지표이므로,
    나중에 실측 CSV 나 다른 엔진 결과에도 같은 계산을 쓸 수 있어야 한다.

    `by_category` 는 난방·냉방·급탕·조명·환기·신재생 등을 키로 갖고,
    각 값은 요구량(req)·소비량(con)·1차에너지(primary)·CO₂(co2)·등급(gradePrimary)을 담는다.
    """
    by_category: Dict[str, Dict[str, float]]
    primary_energy_kwh_m2: float
    co2_kg_m2: float
    renewable_independence_pct: float
    floor_area_m2: float

    @property
    def demand_kwh_m2(self) -> float:
        return sum(v.get("req", 0.0)
                   for k, v in self.by_category.items() if k != "renewable")

    @property
    def consumption_kwh_m2(self) -> float:
        return sum(v.get("con", 0.0)
                   for k, v in self.by_category.items() if k != "renewable")


@dataclass(frozen=True)
class TariffResult:
    """에너지 요금. **소비량 → 돈** 변환만 담당한다.

    자본비·현금흐름은 여기 오지 않는다 — 요금표가 바뀌는 주기와 공사비가 바뀌는
    주기가 다르므로 같이 두면 한쪽 갱신이 다른 쪽을 흔든다.
    """
    electricity_won: float
    heating_won: float
    heating_fuel: str                      # "electricity" | "gas" | "district" ...
    baseline_total_won: float              # 개선 전 (실측 또는 시뮬)
    baseline_source: str                   # "actual_bill" | "actual_usage" | "simulated" | "estimated"

    @property
    def total_won(self) -> float:
        return self.electricity_won + self.heating_won

    @property
    def annual_saving_won(self) -> float:
        return self.baseline_total_won - self.total_won


@dataclass(frozen=True)
class CapitalCostResult:
    """공사비. 항목별 내역을 잃지 않는다 — 합계만 남기면 근거를 되짚을 수 없다."""
    by_item: Dict[str, float]              # 창호·단열·LED·HVAC·PV …
    total_won: float
    budget_won: Optional[float] = None

    @property
    def over_budget_won(self) -> float:
        if not self.budget_won:
            return 0.0
        return max(0.0, self.total_won - self.budget_won)


@dataclass(frozen=True)
class CashflowResult:
    """LCC. 가정값을 결과와 함께 들고 다닌다 —
    할인율이 얼마였는지 모르면 NPV 숫자는 해석할 수 없다."""
    npv_won: float
    irr_pct: Optional[float]
    simple_payback_years: Optional[float]
    yearly_net_won: List[float]
    analysis_years: int
    discount_rate: float
    inflation_rate: float
    utility_inflation: float
