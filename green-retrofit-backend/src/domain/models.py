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
  - 시계열은 **튜플**로 받는다. `frozen=True` 는 리스트 *내용*을 막지 못한다.
  - **추정·폴백은 구조화해서 들고 다닌다.** 문자열 메모만으로는 기계 판독이 안 된다.
"""
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Mapping, Optional, Tuple

# 이 코드베이스에서 반복해서 필요한 환산. 매직넘버로 흩어놓지 않는다.
J_TO_KWH = 3_600_000.0


class EnergyCategory(str, Enum):
    """에너지 용도. **값은 기존 API 응답의 키와 정확히 같아야 한다** —
    프런트가 이 문자열에 의존하므로 마음대로 바꾸면 화면이 깨진다."""
    HEATING = "heating"
    COOLING = "cooling"
    HOT_WATER = "hotwater"        # ⚠️ "dhw" 가 아니다
    LIGHTING = "lighting"
    VENTILATION = "ventilation"   # ⚠️ "vent" 가 아니다
    EQUIPMENT = "equipment"
    RENEWABLE = "renewable"


class BaselineSource(str, Enum):
    """개선 전 기준선을 무엇으로 잡았나.

    ⚠️ `ESTIMATE` 의 값은 `"estimate"` 다 — `"estimated"` 가 아니다.
    기존 응답과 시험(`test_recommendations.py`)이 이 철자에 의존한다.
    """
    ACTUAL_BILL = "actual_bill"
    ACTUAL_USAGE = "actual_usage"
    SIMULATED = "simulated"
    ESTIMATE = "estimate"


class TimeResolution(str, Enum):
    """시계열 해상도.

    ⚠️ 행 수로 추정하면 안 된다. 예전 코드는 `len(df) > 365` 로 판단했는데,
    그것은 데이터가 무엇인지가 아니라 얼마나 많은지를 본 것이다.
    """
    HOURLY = "hourly"
    MONTHLY = "monthly"


class ConsumptionBasis(str, Enum):
    """소비량이 **어떻게 만들어졌나**. 결과 해석에 반드시 필요하다."""
    METERED = "metered"           # EnergyPlus 미터 실측값
    DERIVED_FROM_COP = "cop"      # 요구량 ÷ COP·효율로 계산
    UNAVAILABLE = "unavailable"   # 산출 불가 (0 으로 둠)


@dataclass(frozen=True)
class ConversionStep:
    """요구량 → 소비량 변환 하나의 근거. 문자열 메모 대신 구조로 남긴다."""
    category: EnergyCategory
    basis: ConsumptionBasis
    factor: Optional[float] = None       # 적용된 COP 또는 효율
    source_name: str = ""                # 미터 이름 또는 계산 방식
    note: str = ""                       # 사용자에게 보일 설명


@dataclass(frozen=True)
class EnergyConversionContext:
    """소비량이 만들어진 조건 전체.

    ⚠️ **"이상부하에서는 요구량과 소비량이 같다"는 것은 사실이 아니다.**
    이상부하 경로도 요구량을 COP·효율로 나눠 소비량을 만든다
    (`cost_analyzer.py` 의 `total_h_con_kwh += zh_kwh / h_cop`).
    그래서 어떤 계수가 어디에 적용됐는지를 계약으로 들고 다녀야 한다.
    """
    hvac_mode: str                       # "pthp" | "fuel" | "ideal"
    heat_source_id: Optional[int] = None
    heating_fuel: Optional[str] = None   # "NaturalGas" | "OtherFuel1" | None(전기)
    heating_efficiency: Optional[float] = None
    steps: Tuple[ConversionStep, ...] = ()

    @property
    def fallback_steps(self) -> Tuple[ConversionStep, ...]:
        """미터가 없어 추정으로 대체한 것들. **조용한 추정을 막기 위해 노출한다.**"""
        return tuple(s for s in self.steps if s.basis is not ConsumptionBasis.METERED)


def _as_tuple(values) -> Tuple[float, ...]:
    return tuple(float(v) for v in values)


@dataclass(frozen=True)
class EnergyTimeSeries:
    """시뮬레이션이 낸 **시간별(또는 월별) 물리량**. 요금·정책이 섞이기 전 단계다.

    `requirement`(요구량)와 `consumption`(소비량)을 구분하는 것이 핵심이다.
    요구량은 존이 필요로 한 열이고, 소비량은 그걸 만들려고 실제로 쓴 에너지다.
    **둘의 관계는 `context` 가 설명한다** — 계수 없이 숫자만 보면 해석할 수 없다.

    시계열을 없애면 안 된다: TOU 요금·피크·PV 자가소비·월별 집계가 전부 여기 의존한다.
    """
    resolution: TimeResolution
    months: Tuple[int, ...]
    hours: Tuple[int, ...]

    heating_requirement_kwh: Tuple[float, ...]
    cooling_requirement_kwh: Tuple[float, ...]
    heating_consumption_kwh: Tuple[float, ...]
    cooling_consumption_kwh: Tuple[float, ...]
    heating_rate_w: Tuple[float, ...]
    cooling_rate_w: Tuple[float, ...]

    lighting_kwh: Tuple[float, ...]
    equipment_kwh: Tuple[float, ...]
    dhw_kwh: Tuple[float, ...]
    fan_kwh: Tuple[float, ...]
    ventilation_kg_s: Tuple[float, ...]

    context: EnergyConversionContext = field(
        default_factory=lambda: EnergyConversionContext(hvac_mode="ideal"))

    # 길이를 맞춰야 하는 필드 — **하나도 빠뜨리면 안 된다.**
    _SERIES_FIELDS = (
        "hours", "heating_requirement_kwh", "cooling_requirement_kwh",
        "heating_consumption_kwh", "cooling_consumption_kwh",
        "heating_rate_w", "cooling_rate_w",
        "lighting_kwh", "equipment_kwh", "dhw_kwh", "fan_kwh", "ventilation_kg_s",
    )

    def __post_init__(self):
        n = len(self.months)
        for name in self._SERIES_FIELDS:
            got = len(getattr(self, name))
            if got != n:
                raise ValueError(f"시계열 길이 불일치: {name} 이 {got}, months 는 {n}")
        for name in ("months",) + self._SERIES_FIELDS:
            for v in getattr(self, name):
                if isinstance(v, float) and not math.isfinite(v):
                    raise ValueError(f"{name} 에 유한하지 않은 값이 있다: {v}")
        for m in self.months:
            if not 1 <= m <= 12:
                raise ValueError(f"month 범위를 벗어났다: {m}")
        for h in self.hours:
            if not 0 <= h <= 24:
                raise ValueError(f"hour 범위를 벗어났다: {h}")

    @classmethod
    def build(cls, resolution, months, hours, context=None, **series) -> "EnergyTimeSeries":
        """numpy 배열·리스트를 튜플로 정규화해 만든다."""
        return cls(
            resolution=resolution,
            months=tuple(int(m) for m in months),
            hours=tuple(int(h) for h in hours),
            context=context or EnergyConversionContext(hvac_mode="ideal"),
            **{k: _as_tuple(v) for k, v in series.items()},
        )

    @property
    def row_count(self) -> int:
        return len(self.months)


@dataclass(frozen=True)
class AnnualEnergySummary:
    """연간 집계. **원단위가 아니라 절대량**을 담는다 — 면적으로 나누는 것은
    표현 계층의 일이고, 여기서 나눠 두면 면적 기준이 바뀔 때 추적이 어려워진다.

    ⚠️ 환기는 **처리 에너지(`ventilation_*`)와 팬 전력(`fan_kwh`)이 별개**다.
    매트릭스의 `ventilation.con` 은 둘의 합이다. 팬만 담으면 재현할 수 없다.
    """
    heating_requirement_kwh: float
    cooling_requirement_kwh: float
    heating_consumption_kwh: float
    cooling_consumption_kwh: float
    dhw_requirement_kwh: float
    dhw_consumption_kwh: float
    ventilation_requirement_kwh: float
    ventilation_consumption_kwh: float
    lighting_kwh: float
    equipment_kwh: float
    fan_kwh: float

    @property
    def total_consumption_kwh(self) -> float:
        """총 소비. 팬은 `ventilation_consumption_kwh` 에 이미 포함돼 있으므로
        **여기서 다시 더하지 않는다** — 이중계산 방지."""
        return (self.heating_consumption_kwh + self.cooling_consumption_kwh
                + self.dhw_consumption_kwh + self.ventilation_consumption_kwh
                + self.lighting_kwh + self.equipment_kwh)


@dataclass(frozen=True)
class CategoryMetric:
    """용도 하나의 지표. **전부 원단위(㎡당)** 다 — 이름에 박아둔다."""
    requirement_kwh_m2: float
    consumption_kwh_m2: float
    primary_energy_kwh_m2: Optional[float] = None
    co2_kg_m2: Optional[float] = None
    grade_primary_energy_kwh_m2: Optional[float] = None


@dataclass(frozen=True)
class EnergyMetrics:
    """용도별 에너지·1차에너지·CO₂·자립률.

    ⚠️ **economics 가 아니라 domain 이다.** 요금과 무관한 물리·정책 지표이므로,
    나중에 실측 CSV 나 다른 엔진 결과에도 같은 계산을 쓸 수 있어야 한다.
    `by_category` 값은 **이미 ㎡당으로 나뉜 값**이다(절대량이 아니다).
    """
    by_category: Mapping[EnergyCategory, CategoryMetric]
    primary_energy_kwh_m2: float
    co2_kg_m2: float
    renewable_independence_pct: float
    floor_area_m2: float

    def __post_init__(self):
        if self.floor_area_m2 <= 0:
            raise ValueError(f"바닥면적이 0 이하다: {self.floor_area_m2}")
        for key in self.by_category:
            if not isinstance(key, EnergyCategory):
                raise TypeError(f"by_category 키는 EnergyCategory 여야 한다: {key!r}")

    @property
    def demand_kwh_m2(self) -> float:
        """신재생은 상계 항목이라 수요 합계에서 제외한다."""
        return sum(m.requirement_kwh_m2 for k, m in self.by_category.items()
                   if k is not EnergyCategory.RENEWABLE)

    @property
    def consumption_kwh_m2(self) -> float:
        return sum(m.consumption_kwh_m2 for k, m in self.by_category.items()
                   if k is not EnergyCategory.RENEWABLE)

    def as_response_dict(self) -> Dict[str, Dict[str, float]]:
        """기존 API 응답 형태(`matrix`)로 변환. 프런트 호환용."""
        out: Dict[str, Dict[str, float]] = {}
        for key, m in self.by_category.items():
            entry = {"req": m.requirement_kwh_m2, "con": m.consumption_kwh_m2}
            if m.primary_energy_kwh_m2 is not None:
                entry["primary"] = m.primary_energy_kwh_m2
            if m.co2_kg_m2 is not None:
                entry["co2"] = m.co2_kg_m2
            if m.grade_primary_energy_kwh_m2 is not None:
                entry["gradePrimary"] = m.grade_primary_energy_kwh_m2
            out[key.value] = entry
        return out


@dataclass(frozen=True)
class TariffResult:
    """에너지 요금. **소비량 → 돈** 변환만 담당한다.

    자본비·현금흐름은 여기 오지 않는다 — 요금표가 바뀌는 주기와 공사비가 바뀌는
    주기가 다르므로 같이 두면 한쪽 갱신이 다른 쪽을 흔든다.
    """
    electricity_won: float
    heating_won: float
    heating_fuel: str
    baseline_total_won: float
    baseline_source: BaselineSource

    def __post_init__(self):
        if not isinstance(self.baseline_source, BaselineSource):
            raise TypeError(
                f"baseline_source 는 BaselineSource 여야 한다: {self.baseline_source!r}")

    @property
    def total_won(self) -> float:
        return self.electricity_won + self.heating_won

    @property
    def annual_saving_won(self) -> float:
        return self.baseline_total_won - self.total_won


@dataclass(frozen=True)
class CapitalCostResult:
    """공사비. 항목별 내역을 잃지 않는다 — 합계만 남기면 근거를 되짚을 수 없다."""
    by_item: Mapping[str, float]
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
    yearly_net_won: Tuple[float, ...]
    analysis_years: int
    discount_rate: float
    inflation_rate: float
    utility_inflation: float
