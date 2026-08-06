"""`economics/cashflow.py` 단위시험 — **실제 함수**를 부른다.

⚠️ 예전 시험은 IRR 알고리즘을 시험 파일에 **복제**해 검사했다. 그러면 실제 구현이
다시 깨져도 복제본은 통과한다 — 시험이 아니라 별개 구현을 검증하는 셈이다.
codex 가 지적해서 순수 함수로 꺼내고 그것을 직접 부른다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.economics.cashflow import (  # noqa: E402
    cumulative_present_value,
    irr,
    npv,
    simple_payback_years,
)


# ── NPV ─────────────────────────────────────────────────

def test_npv_does_not_discount_year_zero():
    """`cash_flows[0]` 은 초기 투자다 — 할인하면 안 된다."""
    assert npv([-100.0], 0.1) == pytest.approx(-100.0)


def test_npv_discounts_later_years():
    assert npv([0.0, 110.0], 0.1) == pytest.approx(100.0)


def test_zero_discount_rate_is_plain_sum():
    assert npv([-100.0, 50.0, 60.0], 0.0) == pytest.approx(10.0)


# ── IRR ─────────────────────────────────────────────────

def test_irr_is_none_when_never_recovered():
    """전부 음수 — 회수가 불가능하다. 탐색 하한 -99% 를 IRR 로 내보내면 안 된다."""
    assert irr([-100.0, -10.0, -10.0, -10.0]) is None


def test_irr_is_none_without_investment():
    """전부 양수 — 투자가 없다. 탐색 상한 500% 를 IRR 로 내보내면 안 된다."""
    assert irr([100.0, 10.0, 10.0, 10.0]) is None


def test_irr_solves_normal_cashflow():
    assert irr([-100.0, 60.0, 60.0]) == pytest.approx(0.1306623, abs=1e-4)


def test_irr_makes_npv_zero():
    """IRR 의 정의: 그 할인율에서 NPV 가 0 이다."""
    flows = [-1000.0, 300.0, 400.0, 500.0]
    rate = irr(flows)
    assert rate is not None
    assert npv(flows, rate) == pytest.approx(0.0, abs=1e-3)


def test_irr_handles_immediate_full_recovery():
    assert irr([-100.0, 200.0]) == pytest.approx(1.0, abs=1e-4)


def test_irr_of_empty_is_none():
    assert irr([]) is None


# ── 단순 회수기간 ────────────────────────────────────────

def test_payback_interpolates_within_the_year():
    """100 투자, 매년 40 회수 → 2.5년."""
    assert simple_payback_years([-100.0, 40.0, 40.0, 40.0]) == pytest.approx(2.5)


def test_payback_is_none_when_never_recovered():
    assert simple_payback_years([-100.0, 10.0, 10.0]) is None


def test_payback_is_zero_when_no_investment():
    assert simple_payback_years([0.0, 10.0]) == 0.0


def test_payback_lands_exactly_on_a_year():
    assert simple_payback_years([-100.0, 50.0, 50.0]) == pytest.approx(2.0)


def test_payback_of_empty_is_none():
    assert simple_payback_years([]) is None


# ── 누적 현재가치 ────────────────────────────────────────

def test_cumulative_starts_with_capital_plus_first_year():
    series = cumulative_present_value(1000.0, [100.0, 100.0], discount_rate=0.0)
    assert series[0] == pytest.approx(1100.0)
    assert series[1] == pytest.approx(1200.0)


def test_cumulative_index_is_one_less_than_year():
    """⚠️ `series[i]` 는 **(i+1)년차** 누적이다. 헷갈리면 엉뚱한 해를 읽는다."""
    series = cumulative_present_value(0.0, [10.0, 20.0, 30.0], discount_rate=0.0)
    assert len(series) == 3
    assert series[0] == 10.0        # 1년차
    assert series[2] == 60.0        # 3년차 누적


def test_cumulative_discounts_later_years():
    series = cumulative_present_value(0.0, [110.0, 121.0], discount_rate=0.1)
    assert series[0] == pytest.approx(100.0)
    assert series[1] == pytest.approx(200.0)


def test_cumulative_is_monotonic_for_positive_costs():
    series = cumulative_present_value(500.0, [100.0] * 10, discount_rate=0.03)
    assert all(b >= a for a, b in zip(series, series[1:]))
