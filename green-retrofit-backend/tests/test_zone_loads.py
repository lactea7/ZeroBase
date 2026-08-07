"""`domain/zone_loads.py` 단위시험 — 존 내부발열.

⚠️ 여기가 틀리면 **결과가 통째로 틀어진다.** 용호동에서 조명+기기가
44.5 kWh/㎡·년으로 난방(19.0)보다 크다. 그런데 이 정리 로직은 존 루프 안에
인라인으로 있어 시험이 없었다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.domain.zone_loads import ZoneLoads, resolve  # noqa: E402

ARCH = {"people": 0.1, "lighting": 9.0, "equipment": 12.0, "dhw_lpd": 5.0}


def _resolve(zone=None, area=100.0, **kw):
    return resolve(zone or {}, area, ARCH, **kw)


# ── 사용자 입력 vs 아키타입 기본값 ───────────────────────

def test_archetype_defaults_apply_when_unset():
    loads = _resolve()
    assert (loads.people_density, loads.lighting_w_m2) == (0.1, 9.0)
    assert loads.equipment_w_m2 == 12.0


def test_user_input_wins_over_archetype():
    loads = _resolve({"lightingPower": 4.5, "equipmentPower": 20.0,
                      "peopleDensity": 0.05})
    assert (loads.lighting_w_m2, loads.equipment_w_m2) == (4.5, 20.0)
    assert loads.people_density == 0.05


@pytest.mark.parametrize("key,attr", [
    ("lightingPower", "lighting_w_m2"),
    ("equipmentPower", "equipment_w_m2"),
    ("peopleDensity", "people_density"),
])
def test_explicit_zero_is_honoured(key, attr):
    """⚠️ `or` 를 쓰면 사용자가 명시한 0(조명 없는 창고 등)이 기본값으로 바뀐다."""
    assert getattr(_resolve({key: 0}), attr) == 0


# ── 콘센트 ───────────────────────────────────────────────
# ⚠️ 기본이 `sum` 인데, 아키타입 기기부하가 이미 일반 콘센트를 포함한 값이라면
# **이중계산**이다. 그 판단은 아직 안 끝났으므로 현재 동작을 값으로 고정한다.

def test_outlets_are_added_by_default():
    loads = _resolve({"outletCount": 20}, outlet_w_m2=8.0)
    assert loads.equipment_w_m2 == 20.0        # 아키타입 12 + 콘센트 8
    assert loads.outlet_load_type == "sum"


def test_max_mode_takes_the_larger_not_the_sum():
    loads = _resolve({"outletLoadType": "max"}, outlet_w_m2=8.0)
    assert loads.equipment_w_m2 == 12.0        # max(12, 8)


def test_max_mode_can_exceed_the_archetype():
    loads = _resolve({"outletLoadType": "max"}, outlet_w_m2=30.0)
    assert loads.equipment_w_m2 == 30.0


def test_outlet_component_is_reported_separately():
    """합산된 값만 보면 이중계산 여부를 나중에 판정할 수 없다."""
    loads = _resolve(outlet_w_m2=8.0)
    assert loads.outlet_w_m2 == 8.0
    assert loads.has_outlets is True


def test_no_outlet_input_means_no_outlet_component():
    assert _resolve().has_outlets is False


def test_user_equipment_and_outlets_still_sum():
    """⚠️ 사용자가 기기부하를 명시해도 콘센트가 더해진다 — 이중계산의 핵심 경로다."""
    loads = _resolve({"equipmentPower": 30.0}, outlet_w_m2=8.0)
    assert loads.equipment_w_m2 == 38.0


# ── 급탕 ─────────────────────────────────────────────────
# ⚠️ 이 유량은 운영 스케줄로 **변조**된다. 예전엔 `/3600` 으로 "1시간 가동"을
# 가정해 스케줄 적분만큼(약 10배) 과다했다.

def test_dhw_flow_delivers_the_daily_volume_over_operating_hours():
    loads = _resolve()                     # 0.1 인/㎡ × 100㎡ = 10인, 5 L/인·일
    flow = loads.dhw_peak_flow_m3_s(100.0, daily_operating_hours=10.0)
    # 10인 × 5L = 50 L/일 을 10시간에 걸쳐 → 50e-3 m³ / 36,000 s
    assert flow == pytest.approx(50e-3 / 36000.0)


def test_longer_operating_hours_lower_the_peak_flow():
    """같은 일일 사용량을 더 긴 시간에 나눠 쓰면 최대 유량은 낮아야 한다."""
    loads = _resolve()
    assert loads.dhw_peak_flow_m3_s(100.0, 20.0) < loads.dhw_peak_flow_m3_s(100.0, 5.0)


def test_dhw_scales_with_occupancy():
    loads = _resolve()
    assert loads.dhw_peak_flow_m3_s(200.0, 10.0) == pytest.approx(
        2 * loads.dhw_peak_flow_m3_s(100.0, 10.0))


@pytest.mark.parametrize("area,hours", [(0.0, 10.0), (100.0, 0.0), (100.0, -1.0)])
def test_dhw_never_divides_by_zero(area, hours):
    assert _resolve().dhw_peak_flow_m3_s(area, hours) == 0.0


def test_no_people_means_no_hot_water():
    assert _resolve({"peopleDensity": 0}).dhw_peak_flow_m3_s(100.0, 10.0) == 0.0


# ── ASHRAE 140 ───────────────────────────────────────────

def test_benchmark_suppresses_every_automatic_load():
    """⚠️ 140 은 내부발열을 사양대로 못박는다(600 = 순수 현열 200 W).
    용도별 자동 추정이 하나라도 섞이면 그 사양을 표현할 수 없다."""
    loads = _resolve({"peopleDensity": 0.5, "lightingPower": 15.0,
                      "equipmentPower": 20.0, "outletCount": 40},
                     outlet_w_m2=25.0, suppress_auto=True)
    assert loads == ZoneLoads()
    assert loads.dhw_peak_flow_m3_s(100.0, 10.0) == 0.0


# ── 불변 ─────────────────────────────────────────────────

def test_result_is_immutable():
    with pytest.raises(Exception):
        _resolve().lighting_w_m2 = 99.0


def test_zone_dict_is_not_mutated():
    zone = {"lightingPower": 4.5}
    _resolve(zone, outlet_w_m2=8.0)
    assert zone == {"lightingPower": 4.5}
