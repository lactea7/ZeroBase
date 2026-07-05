# 비용 DB 품질 회귀: 오염(바닥재→창호, 두께당 단가)과 등급 역전이 재발하면 잡는다
def test_window_tiers_from_window_sets_only(analyzer):
    """창호 등급 단가는 '창세트' 완제품 기준 — 바닥재(복층 비닐 타일) 오염 시 붕괴됐었다."""
    tiers = analyzer.cost_db["window_tiers"]
    # 실데이터 등급은 현실적 창세트 단가 범위(10만~40만/㎡)여야 함
    for key in ("premium", "high", "standard"):
        t = tiers[key]
        assert t["count"] > 0, f"{key} 등급 데이터 없음"
        assert 100_000 <= t["avg"] <= 400_000, f"{key} 단가 비정상: {t['avg']:,}"


def test_window_tiers_monotonic(analyzer):
    tiers = analyzer.cost_db["window_tiers"]
    order = ["basic", "standard", "high", "premium"]
    avgs = [tiers[k]["avg"] for k in order]
    assert avgs == sorted(avgs), f"창호 등급 단가 역전: {avgs}"


def test_insulation_tiers_monotonic_and_realistic(analyzer):
    tiers = analyzer.cost_db["insulation_tiers"]
    order = ["basic", "standard", "high", "premium"]
    avgs = [tiers[k]["avg"] for k in order]
    assert avgs == sorted(avgs), f"단열 등급 단가 역전: {avgs}"
    # T=1㎜(두께당) 단가 환산 검증: standard(EPS)가 ₩125 수준으로 붕괴하면 실패
    assert tiers["standard"]["avg"] >= 3_000


def test_no_price_guard_fired_on_load(analyzer):
    """정제 후엔 DB 로드에서 단가 가드가 발동하지 않아야 한다(발동=추출 오염 신호)."""
    guard_events = [w for w in analyzer.load_warnings if "단가 가드" in w]
    assert guard_events == [], f"가드 발동: {guard_events}"
