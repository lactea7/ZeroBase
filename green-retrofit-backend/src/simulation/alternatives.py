"""추천 대안 평가 루프 — 시뮬레이터를 **인자로 받는다.**

`ep_simulator._evaluate_alternatives` 에 있던 것을 옮겼다. 실행기를 주입하는 게
이 함수의 정확한 경계다("여러 변형을 시뮬레이터로 실행하는 오케스트레이터").
가짜 시뮬레이터를 끼울 수 있어야 조립 오류를 잡는다 — 순수 함수 시험만으로는
못 잡는 결함이 실제로 있었다(0% 할인율이 5% 로 바뀌던 것).

⚠️ `recommendations` 리스트를 **제자리에서 변형**한다. 응답의 `financial` 과
`result.financial` 이 같은 객체라 여기서의 변형이 양쪽에 반영된다.
"""
import os
from typing import Any, Callable, Dict, List, Optional

from src.simulation.variants import build_variant_payload, net_effect, payback_years

DEFAULT_DISCOUNT_PCT = 5.0
DEFAULT_UTILITY_INFLATION_PCT = 4.0
DEFAULT_LIFECYCLE_YEARS = 20


def _percent(value, default: float) -> float:
    """백분율(%) → 소수. **0 은 유효한 값이다** — `or` 로 폴백하면 안 된다.

    ⚠️ 할인율 0% 는 "미래 비용을 그대로 더한다"는 정당한 입력이다. `or` 를 쓰면
    사용자가 명시한 0 이 조용히 기본값(5%)으로 바뀐다.
    """
    return (default if value is None else float(value)) / 100.0


def evaluate_alternatives(payload: Dict[str, Any], result_data: Dict[str, Any],
                          temp_dir: str, stage_fn: Callable[[str], Any],
                          simulate_fn: Callable[[Dict[str, Any], str], Dict[str, Any]],
                          log: Callable[[str], Any] = print) -> None:
    """추천 대안별 정량 영향(kWh/㎡·운영비·LCC 순효과)을 각 추천에 붙인다.

    열모델이 바뀌는 대안(창호·단열 하향/상향, 지열 해제)은 `simulate_fn` 으로
    실제 재실행하고, 비용만 바뀌는 대안은 에너지 delta 0 으로 표기한다.
    """
    fin = result_data.get("financial", {})
    recs: List[Dict[str, Any]] = fin.get("recommendations") or []
    if not recs:
        return

    base_summary = result_data.get("summary", {})
    base_bill = fin.get("total_energy_bill") or 0
    base_capital = fin.get("capital_cost") or 0
    lccp = fin.get("lcc_parameters", {}) or {}
    discount_rate = _percent(lccp.get("discount_rate"), DEFAULT_DISCOUNT_PCT)
    utility_inflation = _percent(lccp.get("utility_inflation"),
                                 DEFAULT_UTILITY_INFLATION_PCT)
    years = int(lccp.get("lifecycle_years") or DEFAULT_LIFECYCLE_YEARS)

    for rec in recs:
        rec_type = rec.get("type", "")
        variant = build_variant_payload(payload, rec_type)

        if variant is None:
            # 열모델 불변 — 시뮬레이션상 에너지 변화가 없다.
            # (LED 조명 효과 등 미모델 항목은 performance_note 로 따로 고지한다)
            rec["impact"] = _unsimulated_impact(rec, years)
            continue

        variant["_variantOf"] = rec_type
        variant.pop("baselineModel", None)   # 대안 평가의 기준은 현재 개선안이다
        stage_fn(f"alt:{rec_type}")
        log(f"🔀 [대안 평가] '{rec.get('title')}' 적용 모델 재시뮬레이션 시작...")

        try:
            vres = simulate_fn(variant, os.path.join(temp_dir, f"alt_{rec_type}"))
        except Exception as e:
            # 대안 평가 실패가 본 결과를 막으면 안 된다 — 정성 주석은 유지한다.
            # ⚠️ impact 를 안 붙이면 소비자가 "평가 전"과 "평가 실패"를 구별 못 한다.
            log(f"⚠️ [대안 평가] '{rec_type}' 재시뮬레이션 실패 → 정량 영향 생략: {e}")
            rec["impact"] = {**_unsimulated_impact(rec, years),
                             "status": "failed", "error": str(e)}
            continue

        rec["impact"] = _simulated_impact(
            rec, vres, base_summary=base_summary, base_bill=base_bill,
            base_capital=base_capital, years=years,
            discount_rate=discount_rate, utility_inflation=utility_inflation)
        # 순효과가 음수면 '비권장' — 시스템이 손해로 판명한 대안을 그대로 제안하면
        # 사용자가 적용 → 반대 대안 제안 → 재적용의 핑퐁에 빠진다.
        rec["advisable"] = rec["impact"]["net_effect"] >= 0

        imp = rec["impact"]
        log(f"✅ [대안 평가] '{rec.get('title')}': ΔkWh/㎡ {imp['delta_kwh_m2']:+.1f}, "
            f"운영비 {imp['annual_bill_delta']:+,}원/년, "
            f"{years}년 순효과 {imp['net_effect']:+,}원"
            f"{'' if rec['advisable'] else ' → 비권장(장기 손해)'}")


def _unsimulated_impact(rec: Dict[str, Any], years: int) -> Dict[str, Any]:
    return {
        "simulated": False,
        "status": "not_applicable",
        "delta_kwh_m2": 0.0,
        "annual_bill_delta": 0,
        "net_effect": int(rec.get("saved_cost", 0)),
        "lifecycle_years": years,
    }


def _simulated_impact(rec: Dict[str, Any], vres: Dict[str, Any], *,
                      base_summary: Dict[str, Any], base_bill: float,
                      base_capital: float, years: int,
                      discount_rate: float, utility_inflation: float) -> Dict[str, Any]:
    v_sum = vres.get("summary", {})
    v_fin = vres.get("financial", {})
    bill_delta = int((v_fin.get("total_energy_bill") or 0) - base_bill)
    capital_delta = int((v_fin.get("capital_cost") or 0) - base_capital)
    return {
        "simulated": True,
        "status": "ok",
        "payback_years": payback_years(capital_delta, bill_delta),
        "consume_per_m2": v_sum.get("consume_per_m2"),
        "delta_kwh_m2": round((v_sum.get("consume_per_m2") or 0)
                              - (base_summary.get("consume_per_m2") or 0), 1),
        "co2_delta": round((v_sum.get("co2_per_m2") or 0)
                           - (base_summary.get("co2_per_m2") or 0), 2),
        "annual_bill_delta": bill_delta,
        "capital_delta": capital_delta,
        # 순효과는 자재 단가 차액(saved_cost)이 아니라 **실제 총공사비 변화** 기준이다.
        # 예: 창호 하향 → 열손실 증가 → 피크부하·설비 용량 증가 → 설비비 상승까지
        # 재시뮬레이션이 잡아내므로, saved_cost 보다 -capital_delta 가 정직한 절감액이다.
        "net_effect": net_effect(-capital_delta, bill_delta,
                                 discount_rate=discount_rate,
                                 utility_inflation=utility_inflation, years=years),
        "lifecycle_years": years,
    }
