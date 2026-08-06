"""개선 전(기존 건물) 운영비 기준선 산정.

NPV·IRR·절감액은 **전적으로 이 기준선 대비 차이**다. 그래서 어떤 근거로 잡았는지를
결과에 반드시 실어 보낸다(`BaselineSource`) — 사용자가 추정값을 실측으로 오해하면
투자 판단이 통째로 어긋난다.

`LCCAnalyzer.calculate()` 안에 있던 것을 옮겼다. 순수 이동이며 규칙을 바꾸지 않았다.
"""
from dataclasses import dataclass, field
from typing import List, Optional

from src.domain.models import BaselineSource

# 실측이 전혀 없을 때 쓰는 마지막 수단.
# ⚠️ 검증된 값이 아니라 **단일·투명한 가정**이다. 1.6 → 기존이 60% 비쌈 ≈ 절감률 37.5%.
RUNNING_COST_MULTIPLIER = 1.6


@dataclass
class Baseline:
    """기준선과 그 근거."""
    running_cost_won: float
    source: BaselineSource
    warnings: List[str] = field(default_factory=list)

    @property
    def multiplier(self) -> float:
        return RUNNING_COST_MULTIPLIER


def resolve_baseline(*, retrofit_running_cost: float,
                     actual_elec_bill: Optional[float] = None,
                     actual_heat_bill: Optional[float] = None,
                     actual_elec_kwh: Optional[float] = None,
                     actual_heat_kwh: Optional[float] = None,
                     sim_base_elec_bill: Optional[float] = None,
                     sim_base_heat_bill: Optional[float] = None,
                     sim_base_same: bool = False,
                     avg_elec_rate: float = 0.0,
                     heat_rate: float = 0.0) -> Baseline:
    """기준 건물 연간 운영비를 정한다.

    **우선순위** — 앞이 있으면 뒤는 보지 않는다:
      ① 실측 요금  ② 실측 사용량(공식 단가 환산)
      ③ 개선 전 건물 물리 시뮬레이션  ④ 전후 동일(절감 0)  ⑤ 1.6배 추정

    ⚠️ 순서가 바뀌면 사용자가 입력한 실측값이 무시되고 추정으로 계산된다.
    """
    warnings: List[str] = []

    if actual_elec_bill or actual_heat_bill:
        cost = (actual_elec_bill or 0.0) + (actual_heat_bill or 0.0)
        source = BaselineSource.ACTUAL_BILL
    elif actual_elec_kwh or actual_heat_kwh:
        cost = (actual_elec_kwh or 0.0) * avg_elec_rate + (actual_heat_kwh or 0.0) * heat_rate
        source = BaselineSource.ACTUAL_USAGE
    elif (sim_base_elec_bill or 0) > 0 or (sim_base_heat_bill or 0) > 0:
        cost = (sim_base_elec_bill or 0.0) + (sim_base_heat_bill or 0.0)
        source = BaselineSource.SIMULATED
    elif sim_base_same:
        # ⚠️ 편집이 없으면 **절감 0 이 정직한 답**이다.
        # ×1.6 추정을 쓰면 아무것도 안 고쳤는데 37% 절감이 표시된다.
        cost = retrofit_running_cost
        source = BaselineSource.SIMULATED
        warnings.append(
            "개선 전후 모델이 동일합니다 — 창호·단열·설비 등을 편집하지 않아 "
            "절감액이 0으로 계산됩니다")
    else:
        cost = retrofit_running_cost * RUNNING_COST_MULTIPLIER
        source = BaselineSource.ESTIMATE

    # 실측·시뮬 기준선이 개선 후보다 싸면 절감이 음수가 된다 — 입력 점검을 알린다.
    # (추정 경로는 정의상 항상 비싸므로 제외)
    if source is not BaselineSource.ESTIMATE and cost <= retrofit_running_cost:
        warnings.append(
            "기존 건물 운영비(실측 또는 개선 전 시뮬레이션)가 리모델링 후 운영비보다 "
            "낮거나 같습니다 — 절감액이 음수가 될 수 있으니 입력값 또는 개선 항목을 "
            "확인하세요")

    return Baseline(running_cost_won=cost, source=source, warnings=warnings)


def savings_pct(baseline_cost: float, retrofit_cost: float) -> int:
    """절감률(%).

    ⚠️ **정수화 전 원값**으로 계산해야 한다. 응답의 정수 필드로 되계산하면
    반올림 경계에서 1%p 어긋난다(추정 경로는 정확히 37.5%).
    """
    if baseline_cost <= 0:
        return 0
    return round((1 - retrofit_cost / baseline_cost) * 100)
