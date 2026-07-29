# 에너지 매트릭스 계약 — 프런트가 그대로 표시하는 값이므로 백엔드가 단일 출처여야 한다.
#
# 과거 버그 두 가지를 고정한다.
#  1) 환기 req 가 체적(m³)이라 kWh 요구량 합계에 차원이 다른 값이 더해졌다.
#  2) 프런트가 모든 항목에 전기계수(2.75/0.466)를 곱해, 지역난방을 고르면
#     상세 표 합계와 요약 카드가 서로 달랐다.
import pytest


@pytest.fixture(scope="module")
def result(analyzer, base_kwargs):
    # base_kwargs 의 heat_source=11(지역난방) — 1차계수 0.728 로 전기 2.75 와 크게 달라
    # 계수 혼동이 있으면 바로 드러난다.
    return analyzer.calculate(**base_kwargs)


def _matrix(result):
    m = result["matrix"]
    assert m, "matrix 가 결과에 없다"
    return m


def test_every_category_carries_factors(result):
    """항목마다 primary / co2 / gradePrimary 가 실려 있어야 한다."""
    for cat, v in _matrix(result).items():
        assert "primary" in v, f"{cat} 에 primary 없음"
        assert "co2" in v, f"{cat} 에 co2 없음"
        assert "gradePrimary" in v, f"{cat} 에 gradePrimary 없음"


def test_heat_categories_use_fuel_factor_not_electric(result):
    """난방·급탕은 열원 계수(지역난방 0.728)를 써야 한다 — 전기계수 2.75 가 아니다."""
    m = _matrix(result)
    for cat in ("heating", "hotwater"):
        con = m[cat]["con"]
        if abs(con) < 0.05:
            continue
        assert m[cat]["primary"] == pytest.approx(round(con * 0.728, 1), abs=0.05), \
            f"{cat} 에 지역난방 1차계수가 적용되지 않았다"
        # 전기계수를 썼다면 값이 3.8배 가까이 커진다 — 그 오적용을 명시적으로 배제한다
        assert m[cat]["primary"] != pytest.approx(round(con * 2.75, 1), abs=0.05)


def test_electric_categories_use_electric_factor(result):
    """냉방·조명·환기는 전기 1차계수 2.75 를 쓴다."""
    m = _matrix(result)
    for cat in ("cooling", "lighting", "ventilation"):
        con = m[cat]["con"]
        if abs(con) < 0.05:
            continue
        assert m[cat]["primary"] == pytest.approx(round(con * 2.75, 1), abs=0.05)


def test_grade_primary_sums_to_summary(result):
    """등급용 1차의 합계가 요약 카드의 primary_per_m2 와 일치해야 한다.

    프런트 표와 카드가 어긋나던 것이 이 버그였다.
    """
    m = _matrix(result)
    summary = result["summary"]
    total = sum(v["gradePrimary"] for v in m.values())
    assert total == pytest.approx(summary["primary_per_m2"], abs=0.3)


def test_co2_sums_to_summary(result):
    """항목별 CO2 합계가 요약의 co2_per_m2 와 일치해야 한다."""
    m = _matrix(result)
    summary = result["summary"]
    total = sum(v["co2"] for v in m.values())
    assert total == pytest.approx(summary["co2_per_m2"], abs=0.3)


def test_equipment_excluded_from_grade_primary(result):
    """기기부하는 등급 산정에서 빠진다 (5대 에너지 아님)."""
    assert _matrix(result)["equipment"]["gradePrimary"] == 0.0


def test_ventilation_req_is_energy_not_volume(result):
    """환기 요구량이 체적이 아니라 에너지여야 한다.

    체적 그대로면 소요량 대비 비율이 1/0.8 배 이상으로 튄다.
    (con = 체적×0.8 + 팬전력 이므로 req ≤ con 이어야 정상)
    """
    v = _matrix(result)["ventilation"]
    if abs(v["con"]) < 0.05:
        pytest.skip("환기 소요량이 0")
    assert v["req"] <= v["con"] + 0.1, \
        f"환기 요구량({v['req']})이 소요량({v['con']})보다 크다 — 단위가 다를 가능성"
