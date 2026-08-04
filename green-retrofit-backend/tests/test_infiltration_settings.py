"""침기 설정 해석과 진단 집계 단위시험.

EnergyPlus 를 돌리지 않는다 — 순수 함수 수준에서 계약을 고정한다.
침기 ACH 는 난방부하를 지배하므로(실측에서 0.3~1.0 사이에 난방이 수 배 변했다)
잘못된 입력이 조용히 통과하면 결과가 통째로 무의미해진다.
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)
sys.path.insert(0, os.path.join(BACKEND, "src"))

from src.ep_simulator import (  # noqa: E402
    DEFAULT_INFILTRATION_ACH,
    INFILTRATION_MODEL_VERSION,
    LEGACY_INFILTRATION_MODEL_VERSION,
    MAX_INFILTRATION_ACH,
    _infiltration_assumption,
    _measure_infiltration,
    resolve_infiltration_settings,
)


# ── 설정 해석 ──────────────────────────────────────────────

def test_default_is_fixed_ach():
    """기본은 고정 ACH 다. AFN 은 표면 개수 의존 결함이 있어 기본이 될 수 없다."""
    use_afn, ach = resolve_infiltration_settings({}, {})
    assert use_afn is False
    assert ach == DEFAULT_INFILTRATION_ACH


def test_afn_requires_explicit_opt_in():
    use_afn, _ = resolve_infiltration_settings({"infiltrationModel": "afn"}, {})
    assert use_afn is True


def test_benchmark_can_force_afn_off():
    """벤치마크는 지정 침기만 써야 하므로 AFN 요청을 덮어쓴다."""
    use_afn, _ = resolve_infiltration_settings(
        {"infiltrationModel": "afn"}, {"disableAirflowNetwork": True})
    assert use_afn is False


def test_benchmark_ach_overrides_project():
    _, ach = resolve_infiltration_settings(
        {"infiltrationAch": 0.7}, {"infiltrationAch": 0.25})
    assert ach == 0.25


@pytest.mark.parametrize("model", ["hybrid", "AFN2", "none", "  "])
def test_unknown_model_is_rejected(model):
    with pytest.raises(ValueError, match="infiltrationModel"):
        resolve_infiltration_settings({"infiltrationModel": model}, {})


@pytest.mark.parametrize("empty", [None, ""])
def test_empty_model_means_unspecified_not_error(empty):
    """빈 값은 오류가 아니라 '미지정' — 기본(고정 ACH)으로 간다."""
    use_afn, _ = resolve_infiltration_settings({"infiltrationModel": empty}, {})
    assert use_afn is False


def test_model_name_is_case_insensitive():
    use_afn, _ = resolve_infiltration_settings({"infiltrationModel": "AFN"}, {})
    assert use_afn is True


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf"), MAX_INFILTRATION_ACH + 1])
def test_out_of_range_ach_is_rejected(bad):
    with pytest.raises(ValueError, match="infiltrationAch"):
        resolve_infiltration_settings({"infiltrationAch": bad}, {})


def test_non_numeric_ach_is_rejected():
    with pytest.raises(ValueError, match="숫자"):
        resolve_infiltration_settings({"infiltrationAch": "보통"}, {})


# ── 가정 블록 ──────────────────────────────────────────────

ZONES = [{"id": "A", "height": 3.0}, {"id": "B", "height": 3.0}]
AREAS = {"A": 100.0, "B": 100.0}


def test_afn_run_is_recorded_as_legacy_version():
    """AFN 으로 돌린 결과를 fixed-ach-v2 로 적으면 재계산 판단이 깨진다."""
    a = _infiltration_assumption(ZONES, {"A", "B"}, AREAS, 0.5, use_afn=True)
    assert a["modelVersion"] == LEGACY_INFILTRATION_MODEL_VERSION


def test_fixed_run_is_recorded_as_current_version():
    a = _infiltration_assumption(ZONES, set(), AREAS, 0.5, use_afn=False)
    assert a["modelVersion"] == INFILTRATION_MODEL_VERSION
    assert a["detail"]["model"] == "fixed"


def test_assumption_uses_volume_not_area_share():
    """존 높이가 다르면 면적 비율로는 공기량 비율을 알 수 없다."""
    zones = [{"id": "A", "height": 6.0}, {"id": "B", "height": 2.0}]
    a = _infiltration_assumption(zones, {"A"}, {"A": 100.0, "B": 100.0}, 0.5, use_afn=True)
    # 면적은 50% 지만 체적은 600/800 = 75%
    assert a["detail"]["afnVolumePct"] == pytest.approx(75.0, abs=0.1)


def test_measured_mismatch_adds_warning():
    """의도한 ACH 와 실제 적용된 ACH 가 다르면 그 자체가 경고다."""
    a = _infiltration_assumption(ZONES, set(), AREAS, 0.5, use_afn=False,
                                 measured={"effectiveAchBuildingAvg": 0.33})
    assert "0.33" in a["note"]


def test_no_warning_when_measured_matches():
    a = _infiltration_assumption(ZONES, set(), AREAS, 0.5, use_afn=False,
                                 measured={"effectiveAchBuildingAvg": 0.508})
    assert "실제 적용된 평균 침기는" not in a["note"]


def test_fixed_model_is_not_called_standard():
    """0.5 는 국내 실측 기반 표준값이 아니라 임시값이다 — 그렇게 표기하면 안 된다."""
    a = _infiltration_assumption(ZONES, set(), AREAS, 0.5, use_afn=False)
    assert "표준" not in a["summary"]
    assert a["confidence"] == "low"


# ── 측정 집계 ──────────────────────────────────────────────

def _write_csv(tmp_path, header, rows):
    p = tmp_path / "eplusout.csv"
    p.write_text("\n".join([",".join(header)] + [",".join(str(v) for v in r) for r in rows]))
    return str(tmp_path)


def test_mixed_afn_and_fixed_zones_are_both_counted(tmp_path):
    """⚠️ 회귀 방지: AFN 열이 있으면 고정 ACH 존을 빼먹던 버그.

    legacy 모델은 한 건물에 두 침기 경로가 섞였다(외기면 2개 이상 존만 AFN).
    AFN 열만 집계하면 나머지 존이 통째로 빠져 건물 실효 ACH 가 왜곡된다.
    """
    header = ["Date/Time",
              "A:AFN Zone Infiltration Volume [m3](Hourly)",
              "B:Zone Infiltration Standard Density Volume [m3](Hourly)"]
    # 2시간치. A 는 시간당 10 m3, B 는 20 m3
    rows = [["01/01  01:00:00", 10, 20], ["01/01  02:00:00", 10, 20]]
    zones = [{"id": "A", "height": 3.0}, {"id": "B", "height": 3.0}]
    out = _measure_infiltration(_write_csv(tmp_path, header, rows), zones,
                                {"A": 100.0, "B": 100.0})
    assert out["measuredZoneCount"] == 2, "두 경로 중 하나만 집계됐다"
    assert out["annualInfiltrationVolumeM3"] == pytest.approx(60.0)
    # 총 체적 600 m3, 2시간 → 60/600/2 = 0.05
    assert out["effectiveAchBuildingAvg"] == pytest.approx(0.05, abs=1e-3)


def test_measure_uses_supplied_floor_areas(tmp_path):
    """IDF 생성에 쓴 면적과 같은 분모를 써야 한다 — 원본 area 와 다를 수 있다."""
    header = ["Date/Time", "A:Zone Infiltration Standard Density Volume [m3](Hourly)"]
    rows = [["01/01  01:00:00", 30]]
    zones = [{"id": "A", "height": 3.0, "area": 999.0}]   # 원본 면적은 틀렸다
    out = _measure_infiltration(_write_csv(tmp_path, header, rows), zones, {"A": 10.0})
    # 체적 30 m3, 1시간, 침기 30 → 1.0 ACH
    assert out["effectiveAchBuildingAvg"] == pytest.approx(1.0, abs=1e-3)


def test_missing_csv_returns_empty(tmp_path):
    """진단 실패가 시뮬레이션을 막으면 안 된다."""
    assert _measure_infiltration(str(tmp_path), ZONES, AREAS) == {}
