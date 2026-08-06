"""`simulation/alternatives.py` 단위시험 — 대안 평가 루프.

가짜 시뮬레이터를 끼워 **조립**을 검사한다. 순수 함수(`net_effect`) 시험만으로는
못 잡는 결함이 실제로 있었다 — 사용자가 명시한 0% 할인율이 `or` 폴백에 걸려
5% 로 바뀌고 있었다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.simulation.alternatives import evaluate_alternatives  # noqa: E402


def _payload():
    """창호 하향·상향이 **둘 다** 열모델을 바꾸는 최소 페이로드.

    ⚠️ `glazingId` 를 42(하향 목표)나 154(상향 목표)로 두면 그쪽 대안이
    "이미 그 사양"으로 걸려 None 이 되고, 시뮬레이션을 안 돈다.
    """
    return {"surfaces": [{"id": "W1", "type": "Window"}],
            "materials": {"constructions": []}, "projectData": {}}


def _result(recs, *, bill=10_000_000, capital=100_000_000,
            consume=200.0, co2=90.0, lcc=None):
    return {
        "summary": {"consume_per_m2": consume, "co2_per_m2": co2},
        "financial": {"recommendations": recs, "total_energy_bill": bill,
                      "capital_cost": capital,
                      "lcc_parameters": lcc if lcc is not None else {}},
    }


def _sim(*, bill, capital, consume=200.0, co2=90.0):
    """호출 기록을 남기는 가짜 시뮬레이터."""
    calls = []

    def run(variant, temp_dir):
        calls.append((variant, temp_dir))
        return {"summary": {"consume_per_m2": consume, "co2_per_m2": co2},
                "financial": {"total_energy_bill": bill, "capital_cost": capital}}

    run.calls = calls
    return run


def _run(result, sim, payload=None, stages=None):
    evaluate_alternatives(payload or _payload(), result, "/tmp/x",
                          stages.append if stages is not None else (lambda s: None),
                          simulate_fn=sim, log=lambda *_a: None)


# ── 실행 여부 ────────────────────────────────────────────

def test_non_thermal_recommendation_never_runs_the_simulator():
    """⚠️ 열모델이 안 바뀌는데 돌리면 2.5분을 버린다."""
    recs = [{"type": "led", "title": "LED 교체", "saved_cost": 3_000_000}]
    sim = _sim(bill=0, capital=0)
    _run(_result(recs), sim)
    assert sim.calls == []
    assert recs[0]["impact"]["simulated"] is False
    assert recs[0]["impact"]["net_effect"] == 3_000_000


def test_thermal_recommendation_runs_the_simulator_once():
    recs = [{"type": "window", "title": "일반 복층 하향", "saved_cost": 5_000_000}]
    sim = _sim(bill=11_000_000, capital=95_000_000)
    _run(_result(recs), sim)
    assert len(sim.calls) == 1


def test_variant_is_tagged_and_baseline_is_dropped():
    """⚠️ `_variantOf` 가 없으면 대안 평가가 자기 대안을 또 평가해 무한 재귀다.
    `baselineModel` 은 대안 평가에 불필요하다 — 남기면 시뮬레이션이 두 배로 돈다."""
    payload = {**_payload(), "baselineModel": {"surfaces": []}}
    recs = [{"type": "window", "title": "창호", "saved_cost": 0}]
    sim = _sim(bill=0, capital=0)
    _run(_result(recs), sim, payload=payload)
    variant, temp_dir = sim.calls[0]
    assert variant["_variantOf"] == "window"
    assert "baselineModel" not in variant
    assert temp_dir.endswith("alt_window")
    assert "baselineModel" in payload, "원본에서 지워버렸다"


def test_stage_is_reported_per_alternative():
    recs = [{"type": "window", "title": "창호", "saved_cost": 0},
            {"type": "led", "title": "LED", "saved_cost": 0}]
    stages = []
    _run(_result(recs), _sim(bill=0, capital=0), stages=stages)
    assert stages == ["alt:window"], "시뮬레이션 안 하는 대안까지 단계로 보고했다"


def test_no_recommendations_is_a_noop():
    _run(_result([]), _sim(bill=0, capital=0))
    _run(_result(None), _sim(bill=0, capital=0))


# ── 산출값 ───────────────────────────────────────────────

def test_deltas_are_measured_against_the_base_result():
    recs = [{"type": "window", "title": "창호", "saved_cost": 5_000_000}]
    result = _result(recs, bill=10_000_000, capital=100_000_000,
                     consume=200.0, co2=90.0)
    _run(result, _sim(bill=11_500_000, capital=92_000_000, consume=215.0, co2=97.5))
    imp = recs[0]["impact"]
    assert imp["delta_kwh_m2"] == 15.0
    assert imp["co2_delta"] == 7.5
    assert imp["annual_bill_delta"] == 1_500_000
    assert imp["capital_delta"] == -8_000_000


def test_net_effect_uses_capital_delta_not_saved_cost():
    """⚠️ 창호를 낮추면 열손실이 늘어 설비 용량·설비비까지 오른다. 자재 단가
    차액(saved_cost)만 보면 절감액을 과대평가한다."""
    recs = [{"type": "window", "title": "창호", "saved_cost": 50_000_000}]
    result = _result(recs, bill=10_000_000, capital=100_000_000,
                     lcc={"discount_rate": 5.0, "utility_inflation": 5.0,
                          "lifecycle_years": 10})
    # 공사비는 300만원만 줄었는데 운영비는 매년 100만원 늘었다
    _run(result, _sim(bill=11_000_000, capital=97_000_000))
    assert recs[0]["impact"]["net_effect"] == 3_000_000 - 10_000_000
    assert recs[0]["advisable"] is False


def test_advisable_is_true_when_net_effect_is_positive():
    recs = [{"type": "window", "title": "창호", "saved_cost": 0}]
    result = _result(recs, bill=10_000_000, capital=100_000_000)
    _run(result, _sim(bill=10_000_000, capital=90_000_000))
    assert recs[0]["impact"]["net_effect"] == 10_000_000
    assert recs[0]["advisable"] is True


def test_payback_appears_for_upgrades():
    """공사비가 늘고 운영비가 줄면 회수기간이 뜬다 — 상향 대안의 핵심 지표."""
    recs = [{"type": "window_upgrade", "title": "고성능 창호", "saved_cost": 0}]
    result = _result(recs, bill=10_000_000, capital=100_000_000)
    _run(result, _sim(bill=8_000_000, capital=110_000_000))
    assert recs[0]["impact"]["payback_years"] == 5.0


# ── LCC 파라미터 조립 ─────────────────────────────────────
# ⚠️ 여기가 순수 함수 시험으로는 못 잡는 지점이다.

def test_explicit_zero_discount_rate_is_honoured():
    """⚠️ 예전엔 `or 5.0` 이라 사용자가 지정한 **0%** 가 5% 로 바뀌었다.
    할인율 0% 는 '미래 비용을 그대로 더한다'는 정당한 입력이다."""
    recs = [{"type": "window", "title": "창호", "saved_cost": 0}]
    result = _result(recs, bill=10_000_000, capital=100_000_000,
                     lcc={"discount_rate": 0.0, "utility_inflation": 0.0,
                          "lifecycle_years": 10})
    _run(result, _sim(bill=11_000_000, capital=100_000_000))
    # 할인 없음 → 10년치 증가분이 그대로: 0 − (100만 × 10)
    assert recs[0]["impact"]["net_effect"] == -10_000_000


def test_missing_lcc_parameters_fall_back_to_defaults():
    recs = [{"type": "led", "title": "LED", "saved_cost": 0}]
    _run(_result(recs, lcc={}), _sim(bill=0, capital=0))
    assert recs[0]["impact"]["lifecycle_years"] == 20


def test_explicit_lifecycle_years_is_used():
    recs = [{"type": "led", "title": "LED", "saved_cost": 0}]
    _run(_result(recs, lcc={"lifecycle_years": 30}), _sim(bill=0, capital=0))
    assert recs[0]["impact"]["lifecycle_years"] == 30


# ── 실패 처리 ────────────────────────────────────────────

def test_a_failed_alternative_does_not_block_the_others():
    """대안 평가 실패가 본 결과를 막으면 안 된다."""
    def flaky(variant, temp_dir):
        if variant["_variantOf"] == "window":
            raise RuntimeError("EnergyPlus 실패")
        return {"summary": {"consume_per_m2": 190.0, "co2_per_m2": 85.0},
                "financial": {"total_energy_bill": 9_000_000,
                              "capital_cost": 105_000_000}}

    recs = [{"type": "window", "title": "창호", "saved_cost": 0},
            {"type": "window_upgrade", "title": "고성능 창호", "saved_cost": 0}]
    _run(_result(recs), flaky)
    assert recs[1]["impact"]["simulated"] is True


def test_failure_never_produces_an_impact_block():
    """⚠️ 소비자(ResultDashboard·pdfReport)는 `impact.simulated` 만 보고 분기한다.
    실패를 `simulated: False` 인 impact 로 실으면 화면에
    **"에너지 영향 없음 — 열모델을 바꾸지 않아 공사비만 변동합니다"** 가 나간다.
    거짓이다 — 열모델은 바뀌는데 평가에 실패한 것이다."""
    def boom(variant, temp_dir):
        raise RuntimeError("EnergyPlus 실패")

    recs = [{"type": "window", "title": "창호", "saved_cost": 0}]
    _run(_result(recs), boom)
    assert "impact" not in recs[0]
    assert recs[0]["impact_status"] == "failed"
    assert "EnergyPlus 실패" in recs[0]["impact_error"]


def test_the_three_outcomes_are_distinguishable():
    def boom(variant, temp_dir):
        raise RuntimeError("실패")

    recs = [{"type": "led", "title": "LED", "saved_cost": 0},
            {"type": "window", "title": "창호", "saved_cost": 0}]
    _run(_result(recs), boom)
    assert recs[0]["impact_status"] == "not_applicable"
    assert recs[1]["impact_status"] == "failed"


def test_successful_evaluation_is_marked_ok():
    recs = [{"type": "window", "title": "창호", "saved_cost": 0}]
    _run(_result(recs), _sim(bill=9_000_000, capital=99_000_000))
    assert recs[0]["impact_status"] == "ok"


@pytest.mark.parametrize("bad", [
    {},
    {"summary": {}, "financial": {}},
    {"summary": {"consume_per_m2": 200.0}, "financial": {}},              # 요금 없음
    {"summary": {}, "financial": {"total_energy_bill": 9_000_000,
                                  "capital_cost": 99_000_000}},          # 소요량 없음
])
def test_incomplete_simulator_result_is_a_failure_not_a_saving(bad):
    """⚠️ 빈 결과를 받으면 없는 값이 0 으로 읽혀 **기준값 전체를 절감한 것처럼**
    계산된다(운영비 1천만원 → delta −1천만원). 실패로 다뤄야 한다."""
    recs = [{"type": "window", "title": "창호", "saved_cost": 0}]
    _run(_result(recs), lambda v, d: bad)
    assert "impact" not in recs[0]
    assert recs[0]["impact_status"] == "failed"
