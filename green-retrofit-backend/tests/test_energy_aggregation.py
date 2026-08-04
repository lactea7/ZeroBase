"""`domain/energy_aggregation.py` 단위시험 — 순수 합산 계약.

golden 은 실제 fixture 로 값을 고정하지만, 여기서는 **경계 규칙**을 직접 못박는다:
난방에 급탕이 섞이지 않을 것, 환기 요구량이 팬을 뺀 값일 것,
급탕 요구량이 배관손실을 되돌린 값일 것, 월이 정확히 배분될 것.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.energy_aggregation import (  # noqa: E402
    DHW_DISTRIBUTION_LOSS,
    annual_summary,
    monthly_breakdown,
)
from src.domain.models import EnergyTimeSeries, TimeResolution  # noqa: E402


def _series(months, **override):
    n = len(months)
    base = dict(
        heating_requirement_kwh=[0.0] * n, cooling_requirement_kwh=[0.0] * n,
        heating_consumption_kwh=[0.0] * n, cooling_consumption_kwh=[0.0] * n,
        heating_rate_w=[0.0] * n, cooling_rate_w=[0.0] * n,
        lighting_kwh=[0.0] * n, equipment_kwh=[0.0] * n, dhw_kwh=[0.0] * n,
        fan_kwh=[0.0] * n, ventilation_kg_s=[0.0] * n,
    )
    base.update(override)
    return EnergyTimeSeries.build(TimeResolution.HOURLY, months, [12] * n, **base)


# ── 월별 배분 ────────────────────────────────────────────

def test_values_land_in_the_right_month():
    s = _series([1, 1, 7, 12], heating_consumption_kwh=[10, 5, 0, 20])
    rows = monthly_breakdown(s, total_area_m2=1.0)
    assert rows[0]["heating"] == pytest.approx(15.0)    # 1월 = 10+5
    assert rows[6]["heating"] == pytest.approx(0.0)
    assert rows[11]["heating"] == pytest.approx(20.0)


def test_always_twelve_months_even_if_data_is_partial():
    """설계일 실행처럼 한 달치만 있어도 12개월 구조를 유지해야 한다."""
    rows = monthly_breakdown(_series([7, 7], cooling_consumption_kwh=[3, 4]), 1.0)
    assert len(rows) == 12
    assert [r["name"] for r in rows][:2] == ["1월", "2월"]
    assert rows[6]["cooling"] == pytest.approx(7.0)


def test_hot_water_is_not_mixed_into_heating():
    """⚠️ 예전엔 난방에 급탕이 섞여 **여름에도 난방값이 떠 보였다.**"""
    s = _series([7], heating_consumption_kwh=[0.0], dhw_kwh=[9.0])
    row = monthly_breakdown(s, 1.0)[6]
    assert row["heating"] == pytest.approx(0.0)
    assert row["hotwater"] == pytest.approx(9.0)


def test_values_are_per_floor_area():
    s = _series([3], heating_consumption_kwh=[100.0])
    assert monthly_breakdown(s, total_area_m2=50.0)[2]["heating"] == pytest.approx(2.0)


def test_zero_area_does_not_divide_by_zero():
    s = _series([1], heating_consumption_kwh=[5.0])
    assert monthly_breakdown(s, total_area_m2=0.0)[0]["heating"] == pytest.approx(5.0)


# ── 연간 집계 ────────────────────────────────────────────

def test_ventilation_requirement_excludes_fan():
    """환기 요구량 = 처리에너지. 팬 전력은 **소비 쪽에만** 붙는다."""
    s = _series([1, 2], fan_kwh=[1.0, 2.0])
    a = annual_summary(s, ventilation_kwh=[10.0, 20.0])
    assert a.ventilation_consumption_kwh == pytest.approx(30.0)
    assert a.ventilation_requirement_kwh == pytest.approx(27.0)   # 30 − 3
    assert a.fan_kwh == pytest.approx(3.0)


def test_dhw_requirement_reverses_distribution_loss():
    """`dhw_kwh` 에는 배관손실이 이미 곱해져 있다."""
    s = _series([1], dhw_kwh=[11.0])
    a = annual_summary(s, ventilation_kwh=[0.0])
    assert a.dhw_consumption_kwh == pytest.approx(11.0)
    assert a.dhw_requirement_kwh == pytest.approx(11.0 / DHW_DISTRIBUTION_LOSS)


def test_fan_is_counted_once_in_total():
    """⚠️ 팬은 환기 소비에 이미 들어있다. 총합에서 또 더하면 이중계산이다."""
    s = _series([1], fan_kwh=[2.0], lighting_kwh=[5.0])
    a = annual_summary(s, ventilation_kwh=[8.0])   # 처리 6 + 팬 2
    assert a.total_consumption_kwh == pytest.approx(8.0 + 5.0)


def test_requirement_and_consumption_are_kept_separate():
    s = _series([1], heating_requirement_kwh=[10.0], heating_consumption_kwh=[4.0])
    a = annual_summary(s, ventilation_kwh=[0.0])
    assert a.heating_requirement_kwh == pytest.approx(10.0)
    assert a.heating_consumption_kwh == pytest.approx(4.0)
