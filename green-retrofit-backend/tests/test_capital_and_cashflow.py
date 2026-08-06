"""자본비·현금흐름 characterization — **분리 전에 현재 동작을 못박는다.**

`test_cost_golden.py` 는 대표 fixture **한 경로**만 덮는다(자본비 4항목 + NPV/IRR).
분기(등기구 수 입력 여부, 비거주 제외, 지열 프리미엄, 예산, 기준선 우선순위)와
연차별 현금흐름은 전혀 안 덮여 있어, 옮기다 깨져도 골든이 통과할 수 있다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)


def _calc(analyzer, base_kwargs, **override):
    return analyzer.calculate(**dict(base_kwargs, **override))


# ── 자본비 분기 ──────────────────────────────────────────

def test_led_cost_uses_user_fixture_count_when_given(analyzer, base_kwargs):
    """등기구 수를 직접 입력하면 면적 추정 대신 그 값을 쓴다."""
    estimated = _calc(analyzer, base_kwargs, led_fixture_count=0)
    explicit = _calc(analyzer, base_kwargs, led_fixture_count=500)
    assert explicit["financial"]["cost_details"]["led"] != \
        estimated["financial"]["cost_details"]["led"]


def test_led_cost_scales_with_fixture_count(analyzer, base_kwargs):
    few = _calc(analyzer, base_kwargs, led_fixture_count=100)
    many = _calc(analyzer, base_kwargs, led_fixture_count=400)
    assert many["financial"]["cost_details"]["led"] > few["financial"]["cost_details"]["led"]


def test_geothermal_costs_more_than_conventional(analyzer, base_kwargs):
    """⚠️ 지열은 천공·열교환기 때문에 단가 프리미엄이 붙는다."""
    normal = _calc(analyzer, base_kwargs, is_geothermal=False)
    geo = _calc(analyzer, base_kwargs, is_geothermal=True)
    assert geo["financial"]["cost_details"]["hvac"] > normal["financial"]["cost_details"]["hvac"]


def test_capital_cost_is_sum_of_details(analyzer, base_kwargs):
    """합계가 항목 합과 다르면 어딘가 빠지거나 이중계상된 것이다."""
    fin = _calc(analyzer, base_kwargs)["financial"]
    d = fin["cost_details"]
    assert fin["capital_cost"] == pytest.approx(
        d["window"] + d["insulation"] + d["led"] + d["hvac"], abs=4)


def test_window_details_report_the_basis(analyzer, base_kwargs):
    """무엇을 얼마에 계상했는지 근거가 응답에 남아야 한다."""
    w = _calc(analyzer, base_kwargs)["financial"]["window_details"]
    assert w["unit_price"] > 0 and w["area_m2"] > 0
    assert 0 < w["u_value"] < 10


# ── 예산 ────────────────────────────────────────────────

def test_budget_is_echoed(analyzer, base_kwargs):
    fin = _calc(analyzer, base_kwargs, target_budget=50_000_000)["financial"]
    assert fin["target_budget"] == 50_000_000


def test_budget_overrun_produces_a_recommendation_signal(analyzer, base_kwargs):
    """예산을 크게 밑돌게 잡으면 초과 사실이 어딘가 드러나야 한다."""
    tight = _calc(analyzer, base_kwargs, target_budget=1_000)
    fin = tight["financial"]
    assert fin["capital_cost"] > fin["target_budget"]


def test_no_budget_is_allowed(analyzer, base_kwargs):
    assert _calc(analyzer, base_kwargs, target_budget=0)["financial"]["target_budget"] == 0


# ── 현금흐름 ────────────────────────────────────────────

def test_cumulative_lcc_length_matches_analysis_years(analyzer, base_kwargs):
    """⚠️ 키 이름은 `cumulative_lcc_30y` 인데 실제 길이는 분석기간을 따른다.
    이름과 내용이 어긋나면 소비자가 30개로 가정하고 인덱싱한다."""
    fin = _calc(analyzer, base_kwargs)["financial"]
    years = fin["lcc_parameters"]["lifecycle_years"]
    assert len(fin["cumulative_lcc_30y"]) == years


def test_cumulative_lcc_is_monotonic(analyzer, base_kwargs):
    """누적 LCC 는 비용 누적이므로 줄어들 수 없다."""
    series = _calc(analyzer, base_kwargs)["financial"]["cumulative_lcc_30y"]
    assert all(b >= a for a, b in zip(series, series[1:]))


def test_cumulative_lcc_starts_above_capital_cost(analyzer, base_kwargs):
    """1년차 누적은 초기 투자비 + 1년 운영비다."""
    fin = _calc(analyzer, base_kwargs)["financial"]
    assert fin["cumulative_lcc_30y"][0] > fin["capital_cost"]


def test_replacement_years_create_jumps(analyzer, base_kwargs):
    """10년차 LED 40%, 15년차 HVAC 50% 교체가 누적에 계단을 만든다.

    ⚠️ `cumulative_lcc_30y[i]` 는 **(i+1)년차 누적**이다. 증분 리스트는 2년차부터
    시작하므로 `year N` 의 증분은 `steps[N - 2]` 다. 인덱스를 하나만 어긋내도
    엉뚱한 해를 검사하게 된다.
    """
    series = _calc(analyzer, base_kwargs)["financial"]["cumulative_lcc_30y"]
    if len(series) < 16:
        pytest.skip("분석기간이 짧아 교체 연차가 없다")
    steps = [series[i] - series[i - 1] for i in range(1, len(series))]

    def step_of(year):
        return steps[year - 2]

    # 교체가 없는 해는 할인 때문에 증분이 매년 줄어든다
    assert step_of(9) < step_of(8)
    # 교체 연차는 그 추세를 깨고 직전 해보다 커진다
    assert step_of(10) > step_of(9), "10년차 LED 교체가 누적에 반영되지 않았다"
    assert step_of(15) > step_of(14), "15년차 HVAC 교체가 누적에 반영되지 않았다"


def test_lcc_parameters_are_reported(analyzer, base_kwargs):
    """할인율을 모르면 NPV 숫자를 해석할 수 없다."""
    p = _calc(analyzer, base_kwargs)["financial"]["lcc_parameters"]
    assert {"discount_rate", "inflation_rate", "utility_inflation", "lifecycle_years"} <= set(p)
    assert p["lifecycle_years"] > 0


# ── NPV 민감도 ───────────────────────────────────────────

def test_npv_sensitivity_has_discount_and_utility_rows(analyzer, base_kwargs):
    rows = _calc(analyzer, base_kwargs)["financial"]["npv_sensitivity"]
    assert {r["param"] for r in rows} == {"할인율", "요금상승률"}


def test_npv_sensitivity_base_matches_reported_npv(analyzer, base_kwargs):
    fin = _calc(analyzer, base_kwargs)["financial"]
    for row in fin["npv_sensitivity"]:
        assert row["base"] == fin["npv"]


def test_higher_discount_rate_lowers_npv(analyzer, base_kwargs):
    """할인율이 오르면 미래 절감의 현재가치가 줄어든다."""
    row = next(r for r in _calc(analyzer, base_kwargs)["financial"]["npv_sensitivity"]
               if r["param"] == "할인율")
    assert row["high"] < row["low"]


# ── 기준선 ──────────────────────────────────────────────

def test_baseline_source_is_estimate_without_actuals(analyzer, base_kwargs):
    """⚠️ 철자가 "estimate" 다. "estimated" 로 바꾸면 프런트가 깨진다."""
    fin = _calc(analyzer, base_kwargs)["financial"]
    assert fin["baseline_assumptions"]["source"] == "estimate"


def test_baseline_reports_its_multiplier_and_cost(analyzer, base_kwargs):
    b = _calc(analyzer, base_kwargs)["financial"]["baseline_assumptions"]
    assert b["base_running_cost"] > 0
    assert b["running_cost_multiplier"] > 1.0


def test_savings_pct_is_consistent_with_baseline(analyzer, base_kwargs):
    """⚠️ `savings_pct` 는 **정수화 전 원값**으로 계산된다. 응답의 정수 필드로
    되계산하면 반올림 경계에서 1%p 어긋난다(estimate 경로는 정확히 37.5%)."""
    fin = _calc(analyzer, base_kwargs)["financial"]
    b = fin["baseline_assumptions"]
    approx_from_response = round((1 - fin["total_energy_bill"] / b["base_running_cost"]) * 100)
    assert abs(b["savings_pct"] - approx_from_response) <= 1


def test_estimate_baseline_savings_is_fixed_by_the_multiplier(analyzer, base_kwargs):
    """추정 기준선(×1.6)에서는 절감률이 배수만으로 결정된다: 1 − 1/1.6 = 37.5%."""
    fin = _calc(analyzer, base_kwargs)["financial"]
    b = fin["baseline_assumptions"]
    assert b["source"] == "estimate"
    assert b["savings_pct"] == round((1 - 1 / b["running_cost_multiplier"]) * 100)


# ── IRR ─────────────────────────────────────────────────
# ⚠️ 예전 구현은 부호 변화를 확인하지 않고 **항상 숫자를 반환**했다.
# 해가 없는 현금흐름에 탐색 경계값(-99% / 500%)을 진짜 IRR 처럼 내보냈다.

def _irr(flows):
    """analyzer 내부 IRR 을 그대로 재현해 시험한다(모듈 밖으로 노출돼 있지 않다)."""
    low, high = -0.99, 5.0

    def npv_at(rate):
        return sum(cf / ((1 + rate) ** t) for t, cf in enumerate(flows))

    npv_low, npv_high = npv_at(low), npv_at(high)
    if npv_low * npv_high > 0:
        return None
    rate = (low + high) / 2
    for _ in range(200):
        rate = (low + high) / 2
        v = npv_at(rate)
        if abs(v) < 1e-5:
            return rate
        if (v > 0) == (npv_low > 0):
            low, npv_low = rate, v
        else:
            high = rate
    return rate


def test_irr_is_none_when_never_recovered():
    """전부 음수 — 회수가 불가능하다. -99% 를 IRR 로 내보내면 안 된다."""
    assert _irr([-100, -10, -10, -10]) is None


def test_irr_is_none_without_investment():
    """전부 양수 — 투자가 없다. 500% 를 IRR 로 내보내면 안 된다."""
    assert _irr([100, 10, 10, 10]) is None


def test_irr_solves_normal_cashflow():
    assert _irr([-100, 60, 60]) == pytest.approx(0.1307, abs=1e-3)


def test_reported_irr_is_numeric_for_the_fixture(analyzer, base_kwargs):
    """대표 fixture 는 해가 있으므로 숫자가 나와야 한다(회귀 방지)."""
    assert _calc(analyzer, base_kwargs)["financial"]["irr"] is not None
