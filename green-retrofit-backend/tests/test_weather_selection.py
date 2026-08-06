# 기상 파일 선택 규칙 — **실제 `_data` 의 EPW 파일**로 확인한다.
#
# 규칙 자체의 단위시험은 `test_weather_selection_unit.py` 에 있다. 여기는
# 저장소에 실제로 들어 있는 파일과 프런트의 지역 목록이 서로 맞는지를 본다.
#
# 두 가지 회귀를 고정한다.
#  1) 프런트의 지역 ID 가 EPW 파일명과 어긋나면 전체키 매칭이 실패하고 도시명 폴백으로
#     엉뚱한 관측소가 뽑힌다. 실제로 기본값 'KOR_SQ_Seoul' 이 서울 관측소(KOR_SO_Seoul.WS)
#     대신 성남 공항(KOR_KG_Seoul-Seongnam.AP)을 집고 있었다.
#  2) 같은 도시에 파일이 여럿이면 알파벳 순으로 골라 더 오래된 기간(대전 2007-2021)이나
#     공항 관측소(수원·청주 AP)가 뽑혔다.
#
# ⚠️ 예전에는 이 파일이 매칭 로직을 **다시 구현**해서 비교했다. 그러면 구현이 바뀌어도
# 시험이 통과한다. 지금은 `select_weather()` 를 그대로 호출한다.
import os
import re

import pytest

from src.energyplus.weather import find_epw_files, select_weather

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEATHER_DIR = os.path.join(REPO_ROOT, "_data")
CONSTANTS = os.path.join(REPO_ROOT, "green-retrofit-frontend", "src", "data", "constants.js")


def _resolve(location_key):
    choice = select_weather(WEATHER_DIR, location_key)
    return choice.reason, os.path.basename(choice.path)


@pytest.fixture(scope="module", autouse=True)
def _require_epw():
    if not find_epw_files(WEATHER_DIR):
        pytest.skip("_data 에 EPW 파일이 없음")


def test_every_frontend_location_matches_by_full_key():
    """프런트 지역 ID 는 전부 전체키로 매칭돼야 한다 — 도시명 폴백에 의존하면 안 된다."""
    if not os.path.exists(CONSTANTS):
        pytest.skip("constants.js 없음")
    ids = [i for i in re.findall(r"id: '([^']+)'", open(CONSTANTS, encoding="utf-8").read())
           if i.startswith("KOR_")]
    assert ids, "지역 ID 를 찾지 못했다"

    bad = [(loc, *_resolve(loc)) for loc in ids if _resolve(loc)[0] != "location"]
    assert bad == [], f"전체키 매칭 실패: {bad}"


def test_seoul_uses_seoul_station_not_seongnam():
    """서울은 성남 공항이 아니라 서울 관측소를 써야 한다."""
    _reason, name = _resolve("KOR_SO_Seoul")
    assert name.startswith("KOR_SO_Seoul"), f"서울 관측소가 아님: {name}"
    assert "Seongnam" not in name


def test_prefers_newer_tmyx_period():
    """같은 관측소에 기간이 둘이면 최신을 고른다 (대전 2007-2021 vs 2009-2023)."""
    _reason, name = _resolve("KOR_TJ_Daejeon")
    assert "2009-2023" in name, f"오래된 기간이 선택됨: {name}"


def test_prefers_weather_station_over_airport():
    """관측소(WS)와 공항(AP)이 함께 있으면 관측소를 고른다."""
    for loc in ("KOR_KG_Suwon", "KOR_HB_Cheongju"):
        _reason, name = _resolve(loc)
        assert ".WS." in name, f"{loc}: 공항이 선택됨 ({name})"
