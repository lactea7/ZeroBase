# 기상 파일 선택 규칙.
#
# 두 가지 회귀를 고정한다.
#  1) 프런트의 지역 ID 가 EPW 파일명과 어긋나면 전체키 매칭이 실패하고 도시명 폴백으로
#     엉뚱한 관측소가 뽑힌다. 실제로 기본값 'KOR_SQ_Seoul' 이 서울 관측소(KOR_SO_Seoul.WS)
#     대신 성남 공항(KOR_KG_Seoul-Seongnam.AP)을 집고 있었다.
#  2) 같은 도시에 파일이 여럿이면 알파벳 순으로 골라 더 오래된 기간(대전 2007-2021)이나
#     공항 관측소(수원·청주 AP)가 뽑혔다.
import os
import re

import pytest

from src.ep_simulator import _weather_rank

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WEATHER_DIR = os.path.join(REPO_ROOT, "_data")
CONSTANTS = os.path.join(REPO_ROOT, "green-retrofit-frontend", "src", "data", "constants.js")


def _epw_files():
    out = []
    for root, _dirs, files in os.walk(WEATHER_DIR):
        for f in files:
            if f.lower().endswith(".epw"):
                out.append(os.path.join(root, f))
    return sorted(out)


def _resolve(location_key, files):
    """ep_simulator 의 매칭 로직과 동일한 순서."""
    target = location_key.lower()
    city = location_key.split("_")[-1].lower()
    matched = [f for f in files if target in os.path.basename(f).lower()]
    stage = "full"
    if not matched:
        matched = [f for f in files if city in os.path.basename(f).lower()]
        stage = "city"
    if not matched:
        matched = [f for f in files if "kor" in os.path.basename(f).lower()]
        stage = "fallback"
    matched.sort(key=_weather_rank, reverse=True)
    return stage, (os.path.basename(matched[0]) if matched else None)


@pytest.fixture(scope="module")
def files():
    f = _epw_files()
    if not f:
        pytest.skip("_data 에 EPW 파일이 없음")
    return f


def test_every_frontend_location_matches_by_full_key(files):
    """프런트 지역 ID 는 전부 전체키로 매칭돼야 한다 — 도시명 폴백에 의존하면 안 된다."""
    if not os.path.exists(CONSTANTS):
        pytest.skip("constants.js 없음")
    ids = [i for i in re.findall(r"id: '([^']+)'", open(CONSTANTS, encoding="utf-8").read())
           if i.startswith("KOR_")]
    assert ids, "지역 ID 를 찾지 못했다"

    bad = []
    for loc in ids:
        stage, name = _resolve(loc, files)
        if stage != "full":
            bad.append((loc, stage, name))
    assert bad == [], f"전체키 매칭 실패: {bad}"


def test_seoul_uses_seoul_station_not_seongnam(files):
    """서울은 성남 공항이 아니라 서울 관측소를 써야 한다."""
    _stage, name = _resolve("KOR_SO_Seoul", files)
    assert name.startswith("KOR_SO_Seoul"), f"서울 관측소가 아님: {name}"
    assert "Seongnam" not in name


def test_prefers_newer_tmyx_period(files):
    """같은 관측소에 기간이 둘이면 최신을 고른다 (대전 2007-2021 vs 2009-2023)."""
    _stage, name = _resolve("KOR_TJ_Daejeon", files)
    assert "2009-2023" in name, f"오래된 기간이 선택됨: {name}"


def test_prefers_weather_station_over_airport(files):
    """관측소(WS)와 공항(AP)이 함께 있으면 관측소를 고른다."""
    for loc in ("KOR_KG_Suwon", "KOR_HB_Cheongju"):
        _stage, name = _resolve(loc, files)
        assert ".WS." in name, f"{loc}: 공항이 선택됨 ({name})"


def test_rank_is_deterministic():
    """정렬 키가 (최신기간, 관측소여부) 순으로 동작한다."""
    old_ws = "KOR_X_City.WS.1_TMYx.2007-2021.epw"
    new_ap = "KOR_X_City.AP.2_TMYx.2009-2023.epw"
    new_ws = "KOR_X_City.WS.3_TMYx.2009-2023.epw"
    ranked = sorted([old_ws, new_ap, new_ws], key=_weather_rank, reverse=True)
    assert ranked[0] == new_ws
    assert ranked[1] == new_ap   # 기간이 우선, 그 다음이 관측소
    assert ranked[2] == old_ws
