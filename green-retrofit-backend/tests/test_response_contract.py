"""API 응답 계약 — **프런트가 이 키에 직접 의존한다.**

codex 권고대로 세 층으로 나눈다:
  ① 스키마 — 키·타입·nullable·배열 길이
  ② 의미 불변 — 필드 사이의 관계 (test_cost_golden 이 수치를 고정하고, 여기선 관계)
  ③ 축소 snapshot — 별도 파일(surface 전체를 snapshot 하면 면수×12 로 diff 가 폭발)

전체 응답을 통째로 snapshot 하지 않는 이유: surface 데이터가 면 수 × 12개월이라
경고 문구 한 줄만 바뀌어도 전체 갱신이 필요해진다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.simulation.result_assembler import LEGACY_NESTED_KEY, TOP_LEVEL_KEYS  # noqa: E402


@pytest.fixture(scope="module")
def result(analyzer, base_kwargs):
    return analyzer.calculate(**base_kwargs)


# ── ① 스키마 ────────────────────────────────────────────

def test_top_level_keys(result):
    assert set(TOP_LEVEL_KEYS) <= set(result)


def test_legacy_nested_copy_is_identical(result):
    """⚠️ 같은 내용을 두 번 싣는다. 프런트가 두 경로를 섞어 써서 한쪽만 없애면
    화면이 깨진다 — 프런트를 한 경로로 모은 뒤에 제거할 것."""
    nested = result[LEGACY_NESTED_KEY]
    for key in TOP_LEVEL_KEYS:
        assert nested[key] is result[key], f"{key} 가 최상위와 다른 객체다"


def test_summary_fields(result):
    s = result["summary"]
    for key in ("demand_per_m2", "consume_per_m2", "primary_per_m2",
                "co2_per_m2", "independence"):
        assert isinstance(s[key], (int, float)), f"{key} 가 숫자가 아니다"


def test_monthly_has_twelve_entries_with_all_categories(result):
    rows = result["monthly"]
    assert len(rows) == 12
    for row in rows:
        assert {"name", "heating", "cooling", "lighting", "equipment", "hotwater"} <= set(row)


def test_matrix_categories_and_shape(result):
    m = result["matrix"]
    assert {"heating", "cooling", "hotwater", "lighting",
            "ventilation", "equipment", "renewable"} <= set(m)
    for name, entry in m.items():
        assert {"req", "con"} <= set(entry), f"{name} 에 req/con 이 없다"


def test_surface_arrays_are_twelve_months(result):
    for surface, series in result["surfaceThermal"].items():
        assert len(series["temperature"]) == 12, f"{surface} 온도 배열이 12개가 아니다"
        assert len(series["radiation"]) == 12
    for surface, series in result["surfaceAirflow"].items():
        assert len(series["inflow"]) == 12
        assert len(series["outflow"]) == 12


def test_financial_required_fields(result):
    f = result["financial"]
    for key in ("annual_elec_bill", "annual_heat_bill", "total_energy_bill",
                "capital_cost", "cost_details", "npv", "total_lcc",
                "cumulative_lcc_30y", "lcc_parameters", "npv_sensitivity",
                "baseline_assumptions", "cost_warnings", "recommendations"):
        assert key in f, f"financial.{key} 가 없다"


def test_nullable_fields_are_nullable_not_zero(result):
    """⚠️ IRR·회수기간은 **None 일 수 있다.** 0 으로 바꾸면
    'IRR 0%' / '즉시 회수'로 오해된다."""
    f = result["financial"]
    for key in ("irr", "simple_payback_years"):
        assert key in f
        assert f[key] is None or isinstance(f[key], (int, float))


def test_baseline_source_is_an_allowed_value(result):
    assert result["financial"]["baseline_assumptions"]["source"] in (
        "actual_bill", "actual_usage", "simulated", "estimate")


def test_cost_warnings_is_a_list_of_strings(result):
    warnings = result["financial"]["cost_warnings"]
    assert isinstance(warnings, list)
    assert all(isinstance(w, str) for w in warnings)


# ── ② 의미 불변 ──────────────────────────────────────────

def test_total_bill_is_sum_of_parts(result):
    f = result["financial"]
    assert f["total_energy_bill"] == pytest.approx(
        f["annual_elec_bill"] + f["annual_heat_bill"], abs=1)


def test_capital_cost_is_sum_of_details(result):
    f = result["financial"]
    d = f["cost_details"]
    assert f["capital_cost"] == pytest.approx(sum(d.values()), abs=4)


def test_summary_consumption_matches_matrix(result):
    """요약 카드와 상세 표가 어긋나면 사용자가 어느 쪽을 믿을지 알 수 없다."""
    m = result["matrix"]
    total = sum(v["con"] for k, v in m.items() if k != "renewable")
    assert result["summary"]["consume_per_m2"] == pytest.approx(total, abs=0.15)


def test_grade_primary_sums_to_summary_primary(result):
    m = result["matrix"]
    total = sum(v.get("gradePrimary", 0) for v in m.values())
    assert result["summary"]["primary_per_m2"] == pytest.approx(total, abs=0.15)


def test_cumulative_lcc_length_matches_analysis_years(result):
    """⚠️ 키 이름은 `cumulative_lcc_30y` 인데 길이는 분석기간을 따른다."""
    f = result["financial"]
    assert len(f["cumulative_lcc_30y"]) == f["lcc_parameters"]["lifecycle_years"]


def test_npv_sensitivity_base_matches_npv(result):
    f = result["financial"]
    for row in f["npv_sensitivity"]:
        assert row["base"] == f["npv"]


def test_renewable_is_negative_or_zero(result):
    """상계 항목이므로 수요·소비에서 빠진다."""
    r = result["matrix"]["renewable"]
    assert r["con"] <= 0 and r["req"] <= 0
