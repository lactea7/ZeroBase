"""`energyplus/weather.py` 단위시험 — EPW 선택 규칙.

⚠️ **기상 파일이 바뀌면 모든 결과가 바뀐다.** 그런데 이 로직은 분리 전까지
직접 시험이 없었다(기존 test_weather_selection.py 는 순위 함수만 봤다).
"""
import os
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND)

from src.energyplus.weather import find_epw_files, rank, select_weather  # noqa: E402


def _make(tmp_path, *names, subdir="weather"):
    root = tmp_path / "_data"
    target = root / subdir if subdir else root
    target.mkdir(parents=True, exist_ok=True)
    for n in names:
        (target / n).write_text("EPW")
    return str(root)


# ── 순위 ────────────────────────────────────────────────

def test_newer_period_wins():
    """⚠️ 알파벳 순으로 고르면 더 오래된 기간이 뽑힌다(대전 2007-2021 vs 2009-2023)."""
    old = "KOR_Daejeon.471330_TMYx.2007-2021.epw"
    new = "KOR_Daejeon.471330_TMYx.2009-2023.epw"
    assert rank(new) > rank(old)


def test_weather_station_beats_airport():
    """관측소(WS)가 공항(AP)보다 도시 대표 기상에 가깝다."""
    ap = "KOR_Suwon.AP.471190_TMYx.2009-2023.epw"
    ws = "KOR_Suwon.WS.471190_TMYx.2009-2023.epw"
    assert rank(ws) > rank(ap)


def test_period_outranks_station_type():
    """기간이 1순위다 — 최신 공항이 오래된 관측소를 이긴다."""
    old_ws = "KOR_X.WS.1_TMYx.2004-2018.epw"
    new_ap = "KOR_X.AP.1_TMYx.2009-2023.epw"
    assert rank(new_ap) > rank(old_ws)


# ── 탐색 ────────────────────────────────────────────────

def test_prefers_weather_subdirectory(tmp_path):
    root = _make(tmp_path, "a.epw", "b.epw")
    (tmp_path / "_data" / "stray.epw").write_text("EPW")
    found = find_epw_files(root)
    assert all("weather" in f for f in found), "_data 루트의 파일까지 긁었다"


def test_falls_back_to_data_root(tmp_path):
    root = _make(tmp_path, "only.epw", subdir="")
    assert len(find_epw_files(root)) == 1


def test_results_are_sorted_for_determinism(tmp_path):
    """⚠️ 순회 순서에 좌우되면 같은 입력이 다른 기상을 고를 수 있다."""
    root = _make(tmp_path, "z.epw", "a.epw", "m.epw")
    assert find_epw_files(root) == sorted(find_epw_files(root))


# ── 선택 ────────────────────────────────────────────────

def test_forced_path_wins(tmp_path):
    root = _make(tmp_path, "KOR_Seoul.epw")
    forced = tmp_path / "bench.epw"
    forced.write_text("EPW")
    choice = select_weather(root, "KOR_Seoul", forced_path=str(forced))
    assert choice.reason == "forced"
    assert choice.path == str(forced)


def test_forced_missing_path_raises(tmp_path):
    """조용히 다른 기상으로 넘어가면 벤치마크가 무의미해진다."""
    root = _make(tmp_path, "KOR_Seoul.epw")
    with pytest.raises(FileNotFoundError):
        select_weather(root, "KOR_Seoul", forced_path=str(tmp_path / "없음.epw"))


def test_location_key_match(tmp_path):
    root = _make(tmp_path, "KOR_Seoul.471080_TMYx.2009-2023.epw", "KOR_Busan.epw")
    choice = select_weather(root, "KOR_Seoul")
    assert choice.reason == "location"
    assert "Seoul" in choice.path


def test_city_fallback_when_full_key_misses(tmp_path):
    root = _make(tmp_path, "KOR_KS_Seoul.epw")
    choice = select_weather(root, "KOR_Seoul")
    assert choice.reason in ("city", "country")
    assert "Seoul" in choice.path


def test_country_fallback(tmp_path):
    root = _make(tmp_path, "KOR_Daegu.epw", "USA_Denver.epw")
    choice = select_weather(root, "KOR_없는도시")
    assert choice.reason == "country"
    assert "KOR" in os.path.basename(choice.path)


def test_newest_wins_among_matches(tmp_path):
    root = _make(tmp_path,
                 "KOR_Daejeon.471330_TMYx.2007-2021.epw",
                 "KOR_Daejeon.471330_TMYx.2009-2023.epw")
    choice = select_weather(root, "KOR_Daejeon")
    assert "2009-2023" in choice.path
    assert choice.candidates_found == 2


def test_missing_is_reported_not_silently_defaulted(tmp_path):
    """⚠️ 기상이 없으면 결과가 무의미하다 — 조용히 넘어가면 안 된다."""
    root = str(tmp_path / "_data")
    os.makedirs(root, exist_ok=True)
    choice = select_weather(root, "KOR_Seoul", fallback_path="/tmp/default.epw")
    assert choice.is_missing
    assert choice.path == "/tmp/default.epw"
