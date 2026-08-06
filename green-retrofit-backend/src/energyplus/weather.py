"""EPW 기상 파일 선택.

`generate_idf_and_simulate()` 안에 있던 것을 옮겼다. 순수 이동이며 규칙을 바꾸지 않았다.

⚠️ 기상 파일이 바뀌면 **모든 결과가 바뀐다.** 어떤 파일이 왜 뽑혔는지 추적할 수
있어야 해서, 선택 근거를 값으로 돌려준다(로그 문자열로만 남기지 않는다).
"""
import os
import re
from dataclasses import dataclass
from typing import List, Optional


@dataclass(frozen=True)
class WeatherChoice:
    """선택된 기상 파일과 그 근거."""
    path: str
    reason: str                 # "forced" | "location" | "city" | "country" | "fallback" | "missing"
    candidates_found: int = 0

    @property
    def is_missing(self) -> bool:
        return self.reason == "missing"


def rank(path: str):
    """EPW 선택 우선순위. 값이 클수록 우선한다.

    같은 도시에 여러 관측 파일이 있을 때 알파벳 순으로 고르면 더 오래된 기간이나
    공항 관측소가 뽑힌다(대전 2007-2021, 수원·청주·여수 AP 등). 기준을 명시한다.
      ① 최신 TMYx 기간  ② 공항(AP)보다 관측소(WS)
    """
    name = os.path.basename(path)
    m = re.search(r"TMYx\.(\d{4})-(\d{4})", name)
    end_year = int(m.group(2)) if m else 0
    is_weather_station = 1 if ".WS." in name else 0
    return (end_year, is_weather_station)


def find_epw_files(db_dir: str) -> List[str]:
    """`_data/weather` 우선, 없으면 `_data` 전체를 훑는다.

    ⚠️ 프로젝트 루트 전체를 걸으면 node_modules·.git 까지 **매 요청마다** 순회한다.
    """
    weather_dir = os.path.join(db_dir, "weather")
    root = weather_dir if os.path.isdir(weather_dir) else db_dir

    found = []
    for walk_root, _dirs, files in os.walk(root):
        for name in files:
            if name.lower().endswith(".epw"):
                found.append(os.path.join(walk_root, name))
    # 동일 조건 다중 매칭 시 선택이 순회 순서에 좌우되지 않도록 고정
    found.sort()
    return found


def select_weather(db_dir: str, location_key: str, *,
                   forced_path: Optional[str] = None,
                   fallback_path: str = "") -> WeatherChoice:
    """지역 키에 맞는 EPW 를 고른다.

    매칭 순서: 지역 키 전체 → 도시명 → 한국(kor) → 첫 파일.
    같은 단계에서 여러 개가 걸리면 `rank()` 로 최신·관측소를 우선한다.
    """
    if forced_path:
        path = os.path.abspath(forced_path)
        if not os.path.isfile(path):
            raise FileNotFoundError(f"지정한 기상 파일이 없습니다: {path}")
        return WeatherChoice(path=path, reason="forced")

    candidates = find_epw_files(db_dir)
    if not candidates:
        return WeatherChoice(path=fallback_path, reason="missing")

    target = (location_key or "").lower()
    city = target.split("_")[-1] if target else ""

    for needle, reason in ((target, "location"), (city, "city"), ("kor", "country")):
        if not needle:
            continue
        matched = [f for f in candidates if needle in os.path.basename(f).lower()]
        if matched:
            matched.sort(key=rank, reverse=True)
            return WeatherChoice(path=os.path.abspath(matched[0]), reason=reason,
                                 candidates_found=len(matched))

    return WeatherChoice(path=os.path.abspath(candidates[0]), reason="fallback",
                         candidates_found=len(candidates))
