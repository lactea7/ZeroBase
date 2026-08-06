# 골든(회귀) 테스트: ARK 샘플 건물 + 월별 EnergyPlus 출력 기준의 기대값을 고정한다.
# 산식을 의도적으로 바꿨다면 아래 golden 값을 함께 갱신할 것 — 그 외의 값 변화는 회귀다.
#
# 2026-07-07 픽스처·골든 전면 갱신:
#  - 구 픽스처 CSV는 다른 건물(12존 박스)의 출력이라 ARK 존과 하나도 매칭되지 않았고,
#    'HEATING'이라는 존이 부분문자열 매칭으로 모든 난방 컬럼을 합산한 값이 골든에 박혀 있었다.
#  - 존-컬럼 매칭을 '{존ID}_IDEAL:' 접두 정확 매칭으로 수정하고, 존 면적 100㎡ 고정 폴백
#    (겨울 냉방 버그의 원인)을 고친 뒤 ARK 건물을 이상부하 모드로 재실행해 픽스처를 재생성.
import pytest


@pytest.fixture(scope="module")
def result(analyzer, base_kwargs):
    return analyzer.calculate(**base_kwargs)


def test_summary_golden(result):
    s = result["summary"]
    assert s["consume_per_m2"] == pytest.approx(221.2, abs=0.1)
    # 2026-07-29 의도된 변경: 247.6 → 246.9
    #   환기 '요구량'이 체적유량 적산값(m³)이라 kWh 합계에 차원이 다른 값이 더해지고
    #   있었다. 소요량과 동일하게 SFP(0.8 kW/(m³/s))를 적용해 에너지로
    #   맞추면서 환기 req 가 줄었다. consume/primary/co2 는 불변.
    assert s["demand_per_m2"] == pytest.approx(246.9, abs=0.1)
    assert s["primary_per_m2"] == pytest.approx(239.0, abs=0.1)
    assert s["co2_per_m2"] == pytest.approx(59.85, abs=0.01)


def test_matrix_golden(result):
    m = result["matrix"]
    assert m["heating"]["con"] == pytest.approx(142.9, abs=0.1)
    assert m["cooling"]["con"] == pytest.approx(19.3, abs=0.1)
    assert m["lighting"]["con"] == pytest.approx(22.0, abs=0.1)
    assert m["equipment"]["con"] == pytest.approx(14.8, abs=0.1)


def test_no_winter_cooling(result):
    """겨울(11~3월)에 냉방이 잡히면 안 된다.

    존 면적 폴백(바닥 폴리곤 <1㎡ → 100㎡ 고정)이 5㎡ 화장실·0.5㎡ 샤프트에 100㎡분
    내부발열을 주입해 한겨울에도 냉방이 돌던 버그의 회귀 가드. 여름 냉방은 있어야 한다.
    """
    monthly = {m["name"]: m for m in result["monthly"]}
    for name in ("1월", "2월", "3월", "11월", "12월"):
        assert monthly[name]["cooling"] == 0.0, f"{name}에 냉방 발생"
    assert monthly["8월"]["cooling"] > 1.0


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
    assert fin["annual_elec_bill"] == 11_032_473
    assert fin["annual_heat_bill"] == 18_383_548


def test_lcc_metrics_golden(result):
    fin = result["financial"]
    assert fin["npv"] == pytest.approx(-58_158_941, rel=1e-6)
    assert fin["irr"] == pytest.approx(1.93, abs=0.01)


def test_monthly_structure(result):
    assert len(result["monthly"]) == 12
    assert {"name", "heating", "cooling", "lighting", "equipment", "hotwater"} <= set(result["monthly"][0].keys())


# 월별 값 자체를 고정한다 (구조만 보던 시험으로는 **월 배분 오류를 못 잡는다**).
# 시계열 → 월별 집계를 별도 모듈로 옮기기 전에 현재 동작을 못박아 둔다.
# 단위는 kWh/㎡. 값을 의도적으로 바꿨다면 아래를 함께 갱신할 것.
MONTHLY_GOLDEN = [
    # (월, 난방, 냉방, 조명, 기기, 급탕)
    (1,  44.9, 0.0, 1.9, 1.3, 1.7),
    (2,  29.1, 0.0, 1.7, 1.1, 1.5),
    (3,  14.5, 0.0, 1.9, 1.3, 1.7),
    (4,   6.6, 0.0, 1.8, 1.2, 1.6),
    (5,   0.0, 0.3, 1.9, 1.3, 1.7),
    (6,   0.0, 3.1, 1.8, 1.2, 1.6),
    (7,   0.0, 6.4, 1.9, 1.3, 1.7),
    (8,   0.0, 7.1, 1.9, 1.3, 1.7),
    (9,   0.0, 2.3, 1.8, 1.2, 1.6),
    (10,  0.9, 0.1, 1.9, 1.3, 1.7),
    (11, 12.5, 0.0, 1.8, 1.2, 1.6),
    (12, 34.4, 0.0, 1.9, 1.3, 1.7),
]


@pytest.mark.parametrize("month,heating,cooling,lighting,equipment,hotwater", MONTHLY_GOLDEN)
def test_monthly_values_golden(result, month, heating, cooling, lighting, equipment, hotwater):
    row = result["monthly"][month - 1]
    assert row["name"] == f"{month}월"
    assert row["heating"] == pytest.approx(heating, abs=0.05)
    assert row["cooling"] == pytest.approx(cooling, abs=0.05)
    assert row["lighting"] == pytest.approx(lighting, abs=0.05)
    assert row["equipment"] == pytest.approx(equipment, abs=0.05)
    assert row["hotwater"] == pytest.approx(hotwater, abs=0.05)


def test_monthly_sums_match_annual(result):
    """월별 합이 연간 값과 어긋나면 월 배분이 틀린 것이다."""
    m = result["matrix"]
    total_heat = sum(r["heating"] for r in result["monthly"])
    total_cool = sum(r["cooling"] for r in result["monthly"])
    assert total_heat == pytest.approx(m["heating"]["con"], rel=0.02)
    assert total_cool == pytest.approx(m["cooling"]["con"], rel=0.02)


def test_no_cooling_outside_season(result):
    """냉방기간(5~10월) 밖에 냉방이 잡히면 계절 마스크가 깨진 것이다."""
    for month in (1, 2, 3, 4, 11, 12):
        assert result["monthly"][month - 1]["cooling"] == pytest.approx(0.0, abs=0.05)


def test_pv_reduces_elec_bill(analyzer, base_kwargs):
    """PV 자가소비가 전기요금에서 차감돼야 한다.

    기존엔 PV가 ZEB 자립률 표시에만 쓰이고 요금은 그대로인 버그가 있었다
    (100kW를 설치해도 요금 동일 — 전수 스윕에서 발견).
    """
    base = analyzer.calculate(**base_kwargs)
    pv = analyzer.calculate(**dict(base_kwargs, pv_capacity_kw=10.0))
    assert pv["financial"]["annual_elec_bill"] < base["financial"]["annual_elec_bill"]
    assert pv["matrix"]["renewable"]["con"] < 0
    # 과대 차감 방지: 절감액 ≤ 발전량 × 최고 요율
    saved = base["financial"]["annual_elec_bill"] - pv["financial"]["annual_elec_bill"]
    assert saved <= 10.0 * 1300.0 * 150.0


# 응답 계약(키·타입·관계)은 tests/test_response_contract.py 로 옮겼다.
# 이 파일은 **수치 골든**만 담당한다 — 두 관심사를 한 파일에 두면 계약을 고칠 때
# 골든 값을 건드릴 위험이 생긴다.
