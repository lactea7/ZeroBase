"""`economics/baseline.py` 단위시험 — 기준선 우선순위.

NPV·IRR·절감액은 전적으로 이 기준선 대비 차이다. 우선순위가 하나만 뒤집혀도
사용자가 입력한 실측값이 무시되고 추정으로 계산된다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.models import BaselineSource  # noqa: E402
from src.economics.baseline import (  # noqa: E402
    RUNNING_COST_MULTIPLIER,
    resolve_baseline,
    savings_pct,
)

RETROFIT = 10_000_000.0


def _resolve(**kw):
    return resolve_baseline(retrofit_running_cost=RETROFIT,
                            avg_elec_rate=100.0, heat_rate=90.0, **kw)


# ── 우선순위 ────────────────────────────────────────────

def test_actual_bill_beats_everything():
    b = _resolve(actual_elec_bill=8_000_000, actual_heat_bill=4_000_000,
                 actual_elec_kwh=999_999, sim_base_elec_bill=1, sim_base_same=True)
    assert b.source is BaselineSource.ACTUAL_BILL
    assert b.running_cost_won == 12_000_000


def test_actual_usage_beats_simulated():
    b = _resolve(actual_elec_kwh=100_000, sim_base_elec_bill=99_000_000)
    assert b.source is BaselineSource.ACTUAL_USAGE
    assert b.running_cost_won == pytest.approx(100_000 * 100.0)


def test_usage_converts_heat_with_heat_rate():
    """전기와 열은 단가가 다르다 — 같은 요율로 환산하면 난방비가 어긋난다."""
    b = _resolve(actual_heat_kwh=1_000)
    assert b.running_cost_won == pytest.approx(1_000 * 90.0)


def test_simulated_beats_same_model():
    b = _resolve(sim_base_elec_bill=15_000_000, sim_base_same=True)
    assert b.source is BaselineSource.SIMULATED
    assert b.running_cost_won == 15_000_000


def test_identical_model_means_zero_saving():
    """⚠️ 편집이 없으면 절감 0 이 정직한 답이다.
    ×1.6 추정을 쓰면 아무것도 안 고쳤는데 37% 절감이 표시된다."""
    b = _resolve(sim_base_same=True)
    assert b.running_cost_won == RETROFIT
    assert savings_pct(b.running_cost_won, RETROFIT) == 0
    assert any("동일" in w for w in b.warnings)


def test_estimate_is_last_resort():
    b = _resolve()
    assert b.source is BaselineSource.ESTIMATE
    assert b.running_cost_won == pytest.approx(RETROFIT * RUNNING_COST_MULTIPLIER)


def test_zero_actuals_do_not_count_as_input():
    """0 은 '입력 없음'과 같다 — 0원 요금을 기준선으로 삼으면 안 된다."""
    assert _resolve(actual_elec_bill=0, actual_heat_bill=0).source is BaselineSource.ESTIMATE


# ── 경고 ────────────────────────────────────────────────

def test_warns_when_baseline_is_cheaper_than_retrofit():
    """실측 기준선이 개선 후보다 싸면 절감이 음수가 된다."""
    b = _resolve(actual_elec_bill=1_000_000)
    assert any("낮거나 같습니다" in w for w in b.warnings)


def test_estimate_never_warns_about_negative_saving():
    """추정 경로는 정의상 항상 비싸다 — 경고가 뜨면 논리 오류다."""
    b = _resolve()
    assert not any("낮거나 같습니다" in w for w in b.warnings)


# ── 절감률 ──────────────────────────────────────────────

def test_estimate_saving_is_fixed_by_multiplier():
    """1 − 1/1.6 = 37.5% → 반올림 38%."""
    assert savings_pct(RETROFIT * RUNNING_COST_MULTIPLIER, RETROFIT) == 38


def test_saving_is_zero_without_baseline():
    assert savings_pct(0, RETROFIT) == 0


def test_saving_can_be_negative():
    """기준선이 더 싸면 음수여야 한다 — 0 으로 깎으면 문제를 숨긴다."""
    assert savings_pct(5_000_000, RETROFIT) < 0
