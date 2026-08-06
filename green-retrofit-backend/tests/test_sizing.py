"""`domain/sizing.py` 단위시험 — 피크·설비용량.

⚠️ **economics 가 아니라 domain 이다.** 요금표가 아니라 물리량에서 나오고,
전기 기본요금(요금)과 설비 공사비(자본비) **양쪽이 이것을 입력으로** 받는다.
여기가 틀리면 요금과 공사비가 함께 틀어진다.
"""
import os
import sys

import numpy as np
import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.sizing import (  # noqa: E402
    DIVERSITY_FACTOR,
    FALLBACK_PEAK_KW_PER_M2,
    MAX_HVAC_KW_PER_M2,
    MIN_HVAC_KW_PER_M2,
    hvac_capacity_kw,
    peak_electric_kw,
)


def _peak(base, cool=None, heat=None, vent=None, area=100.0):
    n = len(base)
    return peak_electric_kw(
        base_demand_w=base, cooling_rate_w=cool or [0.0] * n,
        heating_rate_w=heat or [0.0] * n, ventilation_kg_s=vent or [0.0] * n,
        floor_area_m2=area, np_mod=np)


# ── 피크 전력 ────────────────────────────────────────────

def test_peak_applies_diversity_factor():
    """모든 부하가 같은 순간에 최대가 되지는 않는다."""
    assert _peak([10_000.0, 0.0]) == pytest.approx(10.0 * DIVERSITY_FACTOR)


def test_peak_sums_base_cooling_heating():
    got = _peak([1_000.0], cool=[2_000.0], heat=[3_000.0])
    assert got == pytest.approx(6.0 * DIVERSITY_FACTOR)


def test_peak_falls_back_to_area_when_zero():
    """⚠️ 피크가 0 이면 기본요금이 0 이 된다 — 면적 기반으로 최소값을 잡는다."""
    assert _peak([0.0, 0.0], area=200.0) == pytest.approx(200.0 * FALLBACK_PEAK_KW_PER_M2)


def test_peak_of_empty_series_uses_fallback():
    assert _peak([], area=50.0) == pytest.approx(50.0 * FALLBACK_PEAK_KW_PER_M2)


def test_ventilation_flow_becomes_power():
    """환기 질량유량(kg/s)이 전력에 반영돼야 한다 — 빠지면 피크가 과소해진다."""
    without = _peak([1_000.0])
    with_vent = _peak([1_000.0], vent=[1.2])
    assert with_vent > without


# ── 설비 용량 ────────────────────────────────────────────

def _capacity(heat, cool=None, area=100.0):
    return hvac_capacity_kw(heating_requirement_kwh=heat,
                            cooling_requirement_kwh=cool or [0.0] * len(heat),
                            floor_area_m2=area, np_mod=np)


def test_capacity_uses_percentile_not_max():
    """⚠️ 순간 최대값을 쓰면 셋백 복귀 시 치솟아 설비비가 크게 과대평가된다.
    99퍼센타일이면 이상치 하나가 용량을 좌우하지 못한다."""
    normal = [5.0] * 999
    spike = normal + [500.0]                      # 이상치 하나
    assert _capacity(spike, area=1000.0) < 100.0  # max 였다면 500 근처였을 것


def test_capacity_is_clamped_to_realistic_range():
    """현실 설계부하 40~100 W/㎡ 로 묶는다."""
    huge = _capacity([9999.0] * 100, area=100.0)
    assert huge == pytest.approx(100.0 * MAX_HVAC_KW_PER_M2)
    tiny = _capacity([0.0] * 100, area=100.0)
    assert tiny == pytest.approx(100.0 * MIN_HVAC_KW_PER_M2)


def test_capacity_takes_the_larger_of_heating_and_cooling():
    heat_driven = _capacity([8.0] * 100, cool=[1.0] * 100, area=100.0)
    cool_driven = _capacity([1.0] * 100, cool=[8.0] * 100, area=100.0)
    assert heat_driven == pytest.approx(cool_driven)


def test_empty_series_still_returns_minimum():
    assert _capacity([], area=100.0) == pytest.approx(100.0 * MIN_HVAC_KW_PER_M2)
