# 절감 추천 로직: 언제 어떤 대안이 나오고, 적용 후엔 반복되지 않는지 검증.
import pytest


def _rec_types(result):
    return [r["type"] for r in result["financial"]["recommendations"]]


def test_recommendations_without_budget(analyzer, base_kwargs):
    """예산 미입력이어도 절감 대안은 항상 생성돼야 한다 (설비비 지배 건물)."""
    result = analyzer.calculate(**base_kwargs)
    types = _rec_types(result)
    assert "hvac_scope" in types, "표준 설비 건물엔 비거주 구역 제외 대안이 나와야 함"
    assert "led" in types


def test_hvac_scope_saving_matches_share(analyzer, base_kwargs):
    result = analyzer.calculate(**base_kwargs)
    rec = next(r for r in result["financial"]["recommendations"] if r["type"] == "hvac_scope")
    assert rec["saved_cost"] == 44_979_274  # hvac 1.756억 × 비거주 면적 비율(~25.6%)


def test_hvac_scope_apply_reduces_cost_and_hides_rec(analyzer, base_kwargs):
    base = analyzer.calculate(**base_kwargs)
    applied = analyzer.calculate(**dict(base_kwargs), hvac_exclude_non_habitable=True)

    assert applied["financial"]["cost_details"]["hvac"] < base["financial"]["cost_details"]["hvac"]
    assert applied["financial"]["capital_cost"] == 168_112_863
    assert "hvac_scope" not in _rec_types(applied), "적용 후 같은 추천이 반복되면 안 됨"


def test_led_rec_not_repeated_after_apply(analyzer, base_kwargs):
    applied = analyzer.calculate(**dict(base_kwargs, led_reduction_active=True))
    assert "led" not in _rec_types(applied)
    # 부분 교체 적용 시 LED 비용도 실제로 줄어야 함
    base = analyzer.calculate(**base_kwargs)
    assert applied["financial"]["cost_details"]["led"] < base["financial"]["cost_details"]["led"]


def test_led_saving_promise_equals_actual_delta(analyzer, base_kwargs):
    """카드에 표시하는 절감액 = 적용 후 실제 차액이어야 한다.

    기존엔 led_cost×0.3으로 ~3배 과대표시해 '적용해도 안 줄어든다'는 혼란을 유발했다.
    """
    base = analyzer.calculate(**base_kwargs)
    applied = analyzer.calculate(**dict(base_kwargs, led_reduction_active=True))
    promised = next(r for r in base["financial"]["recommendations"] if r["type"] == "led")["saved_cost"]
    actual = base["financial"]["cost_details"]["led"] - applied["financial"]["cost_details"]["led"]
    assert promised == pytest.approx(actual, abs=2)  # int 절사 오차 허용
    assert promised == 759_250  # ARK 샘플 골든


def test_led_manual_count_gets_halving_rec(analyzer, base_kwargs):
    result = analyzer.calculate(**dict(base_kwargs, led_fixture_count=200))
    led_rec = next(r for r in result["financial"]["recommendations"] if r["type"] == "led")
    assert "50%" in led_rec["title"]
    assert led_rec["saved_cost"] == int(result["financial"]["cost_details"]["led"] * 0.5)


def test_geothermal_gets_removal_rec(analyzer, base_kwargs):
    result = analyzer.calculate(**dict(base_kwargs, is_geothermal=True))
    types = _rec_types(result)
    assert "hvac" in types, "지열 적용 시 지열 해제 대안이 나와야 함"
    # 지열 프리미엄(×2.2)으로 설비비가 비지열보다 커야 함
    base = analyzer.calculate(**base_kwargs)
    assert result["financial"]["cost_details"]["hvac"] > base["financial"]["cost_details"]["hvac"]


def test_budget_passthrough(analyzer, base_kwargs):
    result = analyzer.calculate(**dict(base_kwargs, target_budget=100_000_000.0))
    assert result["financial"]["target_budget"] == 100_000_000
