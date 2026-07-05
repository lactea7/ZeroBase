# 골든(회귀) 테스트: ARK 샘플 건물 + 월별 EnergyPlus 출력 기준의 기대값을 고정한다.
# 산식을 의도적으로 바꿨다면 아래 golden 값을 함께 갱신할 것 — 그 외의 값 변화는 회귀다.
import pytest


@pytest.fixture(scope="module")
def result(analyzer, base_kwargs):
    return analyzer.calculate(**base_kwargs)


def test_summary_golden(result):
    s = result["summary"]
    assert s["consume_per_m2"] == pytest.approx(104.5, abs=0.1)
    assert s["demand_per_m2"] == pytest.approx(102.6, abs=0.1)
    assert s["primary_per_m2"] == pytest.approx(100.9, abs=0.1)
    assert s["co2_per_m2"] == pytest.approx(38.67, abs=0.01)


def test_matrix_golden(result):
    m = result["matrix"]
    assert m["heating"]["con"] == pytest.approx(37.7, abs=0.1)
    assert m["lighting"]["con"] == pytest.approx(26.7, abs=0.1)
    assert m["equipment"]["con"] == pytest.approx(40.1, abs=0.1)
    # 월별 CSV엔 냉방 부하가 없어야 함 (난방 지배 기후 샘플)
    assert m["cooling"]["con"] == 0.0


def test_capital_cost_golden(result):
    # 2026-07-05 갱신 2건:
    #  - 존 실면적 파싱: LED가 균등분할 대신 실측 거주면적 기준
    #  - 창호 DB 정제: 바닥재 오염 제거 → '창세트' 실단가(169,500/㎡)로 창호비 현실화
    #    (기존 15.1M은 오염 중앙값 27,486→가드 50,000원이 만든 과소평가)
    fin = result["financial"]
    assert fin["capital_cost"] == 247_931_532
    assert fin["cost_details"] == {
        "window": 51_124_790,
        "insulation": 12_840_300,
        "led": 8_333_082,
        "hvac": 175_633_358,
    }


def test_energy_bills_golden(result):
    fin = result["financial"]
    assert fin["annual_elec_bill"] == 11_805_449
    assert fin["annual_heat_bill"] == 4_259_969


def test_lcc_metrics_golden(result):
    fin = result["financial"]
    assert fin["npv"] == pytest.approx(-203_271_679, rel=1e-6)
    assert fin["irr"] == pytest.approx(-15.01, abs=0.01)


def test_monthly_structure(result):
    assert len(result["monthly"]) == 12
    assert {"name", "heating", "cooling"} <= set(result["monthly"][0].keys())


def test_response_contract(result):
    """프론트가 의존하는 키가 빠지면 화면이 깨진다 — 계약을 고정."""
    assert {"summary", "monthly", "matrix", "financial"} <= set(result.keys())
    fin = result["financial"]
    for key in ("capital_cost", "target_budget", "cost_details", "recommendations",
                "npv", "irr", "annual_elec_bill", "annual_heat_bill"):
        assert key in fin, f"financial.{key} 누락"
