"""전/후 비교의 **기준선(개선 전)** 실행 — 시뮬레이터를 인자로 받는다.

`ep_simulator.generate_idf_and_simulate` 안에 있던 것을 옮겼다. 실행기를 주입해야
"어떤 경우에 돌리고 어떤 경우에 건너뛰는지"를 실제 시뮬레이션 없이 시험할 수 있다.

⚠️ 기준선을 잘못 판단하면 **절감액이 통째로 틀린다.** 세 갈래가 있다.
  · 실측 요금·사용량이 있으면 → 돌리지 않는다(실측이 더 정확하고 2.5분이 굳는다)
  · 개선 전후 모델이 같으면 → 돌리지 않고 **절감 0** 으로 정직하게 처리한다
  · 그 외 → 개선 전 모델로 한 번 돌린다
"""
import os
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

#: 리모델링으로 **생기는** 요소들. 개선 전 건물엔 없으므로 기준선에서 지운다.
#: ⚠️ 하나라도 빠뜨리면 개선 전 건물이 개선 후 설비를 갖게 돼 절감액이 줄어든다.
RETROFIT_KEYS = (
    "pvCapacity",
    "geothermalApplied",
    "ledReductionActive",
    "hvacExcludeNonHabitable",
    "hvacUpgradeActive",
    "constructionOverrides",
)

#: 실측 기준선으로 인정하는 입력들. 하나라도 양수면 전-시뮬을 생략한다.
ACTUAL_KEYS = ("elecBill", "heatBill", "elecKwh", "heatKwh")


@dataclass(frozen=True)
class BaselineDecision:
    """기준선을 어떻게 잡았는지. `reason` 은 로그가 아니라 **값**이다."""
    should_run: bool
    reason: str          # "actuals" | "identical" | "no_model" | "run"

    @property
    def savings_are_zero(self) -> bool:
        """개선 전후가 같으면 절감은 0 이다 — 추정으로 채우면 안 된다."""
        return self.reason == "identical"


def _is_positive(value) -> bool:
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def has_actual_baseline(project_data: Dict[str, Any]) -> bool:
    """실측 요금·사용량이 입력됐는가."""
    actual = project_data.get("baselineActual") or {}
    return any(_is_positive(actual.get(k)) for k in ACTUAL_KEYS)


def decide(payload: Dict[str, Any], zones, surfaces) -> BaselineDecision:
    """전-시뮬을 돌릴지 판단한다."""
    project_data = payload.get("projectData", {}) or {}
    model = payload.get("baselineModel") or {}

    if has_actual_baseline(project_data):
        return BaselineDecision(False, "actuals")
    if not (model.get("zones") and model.get("surfaces")):
        return BaselineDecision(False, "no_model")

    # 편집이 전혀 없으면 시뮬 1회 낭비 + '×1.6 추정 절감' 착시가 생긴다.
    identical = (
        model["zones"] == zones
        and model["surfaces"] == surfaces
        and not payload.get("constructionOverrides")
        and not any(project_data.get(k) for k in RETROFIT_KEYS)
    )
    return BaselineDecision(not identical, "identical" if identical else "run")


def build_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """기준선 실행용 payload.

    ⚠️ `_variantOf` 를 반드시 남긴다 — 없으면 기준선 실행이 **자기 대안 평가를
    다시 돌려** 무한 재귀가 된다.
    """
    project_data = dict(payload.get("projectData", {}) or {})
    for key in RETROFIT_KEYS:
        project_data.pop(key, None)
    model = payload.get("baselineModel") or {}
    return {
        "projectData": project_data,
        "zones": model.get("zones", []),
        "surfaces": model.get("surfaces", []),
        "materials": payload.get("materials", {}),
        "constructionOverrides": {},
        "_variantOf": "baseline",
    }


def run(payload: Dict[str, Any], zones, surfaces, temp_dir: str, *,
        simulate_fn: Callable[[Dict[str, Any], str], Dict[str, Any]],
        stage_fn: Callable[[str], Any] = lambda _s: None,
        log: Callable[[str], Any] = print):
    """(기준선 결과 or None, 판단) 을 돌려준다."""
    decision = decide(payload, zones, surfaces)

    if decision.reason == "identical":
        log("⏮️ [전/후 비교] 개선 전후 모델 동일 → 전-시뮬 생략 (절감 0으로 처리)")
        return None, decision
    if not decision.should_run:
        return None, decision

    log("⏮️ [전/후 비교] 개선 전(업로드 원본) 건물 시뮬레이션 시작...")
    stage_fn("baseline")
    result = simulate_fn(build_payload(payload), os.path.join(temp_dir, "baseline"))
    log("⏮️ [전/후 비교] 개선 전 시뮬레이션 완료 → 기준선으로 사용")
    return result, decision
