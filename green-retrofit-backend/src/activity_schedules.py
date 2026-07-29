# src/activity_schedules.py
"""
용도(Activity)별 표준 운영 스케줄.

배경
----
gbXML/SBEM의 용도 코드는 _data/Data/ActivityIdList.txt 에 'ID ↔ 이름'으로만 있고,
시간대별 운영/설정온도 같은 '스케줄 값'은 들어있지 않다(실제 값은 iSBEM 바이너리 DB).
그래서 용도명을 키워드로 ~10개 아키타입(office/주거/판매/음식/교육/의료/연구/집회/숙박/보조)에
매핑하고, 아키타입별 표준 스케줄을 여기서 정의한다.

⚠️ 스케줄 값은 한국 건축물 에너지효율등급(ECO2) 표준 사용프로파일의 '구조'에 맞춘
   합리적 근사치다. 공식 인증표 숫자가 있으면 ARCHETYPES의 값만 교체하면 된다.

각 아키타입이 정의하는 것
- occupied_periods: 요일유형별 '재실(운영) 시간대' [(시작시, 끝시), ...]
- heat_setback / cool_setback: 비운영(설정후퇴) 시 난방/냉방 설정온도(℃)
운영 중 설정온도는 존(zone)이 가진 heatingSetpoint/coolingSetpoint를 그대로 쓴다
(= 아키타입은 '언제', 존 설정은 '몇 도'를 담당).
"""

import os
import re

# 요일 유형 → EnergyPlus Schedule:Compact 'For:' 키워드
_DAYTYPE_FOR = {
    "weekday": "Weekdays",
    "weekend": "Weekends",
    "holiday": "Holidays",
}

# ── 아키타입별 표준 스케줄 ────────────────────────────────────────────────────
# 운영(재실/조명/기기) 프로파일은 ASHRAE_OCC(아래)의 시간별 재실률을 사용한다.
# 냉난방은 '재실>임계' 시 존 설정온도, 그 외 setback(여기 값). 즉 타이밍=ASHRAE,
# 온도=사용자 설정. auxiliary만 ASHRAE 프로파일 없이 상시 저조도(op_fraction).
ARCHETYPES = {
    "office":      {"label": "업무시설(사무)",        "heat_setback": 16.0, "cool_setback": 30.0},
    "residential": {"label": "주거",                  "heat_setback": 18.0, "cool_setback": 28.0},
    "lodging":     {"label": "숙박(객실/기숙)",       "heat_setback": 18.0, "cool_setback": 28.0},
    "retail":      {"label": "판매시설",              "heat_setback": 16.0, "cool_setback": 30.0},
    "restaurant":  {"label": "음식점",                "heat_setback": 16.0, "cool_setback": 30.0},
    "education":   {"label": "교육연구(학교)",        "heat_setback": 16.0, "cool_setback": 30.0,
                    # 한국 학사일정: 3/2 개학(1학기), 9/1 개학(2학기) → 방학 구간 저점유
                    "academic_calendar": {
                        "vacation_occ": 0.10,   # 방학 중 점유(행정·돌봄·시설관리)
                        # (Through 날짜, 재학여부) — 달력 순서, 마지막은 12/31
                        "segments": [
                            ("3/1",   False),   # 1/1~3/1   겨울방학
                            ("7/20",  True),    # 3/2~7/20  1학기
                            ("8/31",  False),   # 7/21~8/31 여름방학
                            ("12/23", True),    # 9/1~12/23 2학기
                            ("12/31", False),   # 12/24~    겨울방학
                        ],
                    }},
    "university":  {"label": "대학교",                "heat_setback": 16.0, "cool_setback": 30.0,
                    # 대학 학사일정: 1학기 3/2~6월중순, 2학기 9/1~12월중순 (여름방학 김)
                    "academic_calendar": {
                        "vacation_occ": 0.10,
                        "segments": [
                            ("3/1",   False),   # 1/1~3/1   겨울방학
                            ("6/15",  True),    # 3/2~6/15  1학기
                            ("8/31",  False),   # 6/16~8/31 여름방학
                            ("12/15", True),    # 9/1~12/15 2학기
                            ("12/31", False),   # 12/16~    겨울방학
                        ],
                    }},
    "healthcare":  {"label": "의료시설",              "heat_setback": 22.0, "cool_setback": 26.0},
    "lab":         {"label": "연구/산업(실험·공정)",  "heat_setback": 18.0, "cool_setback": 28.0},
    "assembly":    {"label": "집회/체육/공연",        "heat_setback": 16.0, "cool_setback": 30.0},
    "auxiliary":   {"label": "보조공간(복도·계단·승강기·기계실)",
                    "heat_setback": 15.0, "cool_setback": 32.0,
                    # 복도·계단·승강기는 안전/피난용으로 24시간 상시 저조도 점등.
                    # 냉난방은 종일 setback (적극 공조 없음).
                    "op_fraction": 0.1, "op_hours": (0, 24)},
}

DEFAULT_ARCHETYPE = "office"

# ── 용도별 표준 부하밀도·재실·급탕·설정온도 (존에 명시값 없을 때 기본값) ─────────
# lighting/equipment: W/m², people: 인/m², dhw_lpd: L/인·일, heat/cool: ℃(운영중)
# ⚠️ ECO2/ASHRAE 통상값 기반 근사 — 정확표 있으면 숫자만 교체.
# (기존엔 용도무관 조명10·기기15 일괄 → 냉방 과대평가의 원인이었음)
ARCHETYPE_LOADS = {
    "office":      {"lighting": 9,  "equipment": 12, "people": 0.06, "dhw_lpd": 5,   "heat": 20, "cool": 26},
    "residential": {"lighting": 6,  "equipment": 4,  "people": 0.03, "dhw_lpd": 100, "heat": 20, "cool": 26},
    "lodging":     {"lighting": 8,  "equipment": 5,  "people": 0.05, "dhw_lpd": 120, "heat": 20, "cool": 26},
    "retail":      {"lighting": 13, "equipment": 5,  "people": 0.15, "dhw_lpd": 5,   "heat": 20, "cool": 26},
    "restaurant":  {"lighting": 11, "equipment": 25, "people": 0.50, "dhw_lpd": 40,  "heat": 20, "cool": 26},
    "education":   {"lighting": 9,  "equipment": 8,  "people": 0.25, "dhw_lpd": 8,   "heat": 20, "cool": 26},
    "university":  {"lighting": 10, "equipment": 12, "people": 0.20, "dhw_lpd": 10,  "heat": 20, "cool": 26},
    "healthcare":  {"lighting": 11, "equipment": 18, "people": 0.10, "dhw_lpd": 90,  "heat": 22, "cool": 25},
    "lab":         {"lighting": 12, "equipment": 25, "people": 0.10, "dhw_lpd": 15,  "heat": 20, "cool": 26},
    "assembly":    {"lighting": 9,  "equipment": 5,  "people": 0.30, "dhw_lpd": 10,  "heat": 20, "cool": 26},
    "auxiliary":   {"lighting": 4,  "equipment": 1,  "people": 0.02, "dhw_lpd": 2,   "heat": 18, "cool": 28},
}


def get_archetype_loads(archetype_key: str) -> dict:
    """아키타입의 표준 부하/재실/급탕/설정온도 기본값."""
    return ARCHETYPE_LOADS.get(archetype_key, ARCHETYPE_LOADS[DEFAULT_ARCHETYPE])


_DEFAULT_DB_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "_data"
)
_ACTIVITY_NAME_CACHE = {}


def archetype_key_for_activity(activity_id, db_dir: str = None) -> str:
    """activityId → 아키타입 키. 시뮬레이터와 반드시 같은 경로를 쓴다.

    ep_simulator 는 activityId 를 ActivityIdList DB 의 이름으로 바꾼 뒤 분류한다.
    파서가 Space 이름으로 따로 분류하면 두 경로가 어긋날 수 있으므로, 기본값을
    채울 때도 이 함수를 거치게 한다.
    """
    key = db_dir or _DEFAULT_DB_DIR
    if key not in _ACTIVITY_NAME_CACHE:
        _ACTIVITY_NAME_CACHE[key] = load_activity_names(key)
    names = _ACTIVITY_NAME_CACHE[key]
    try:
        aid = int(activity_id)
    except (TypeError, ValueError):
        return DEFAULT_ARCHETYPE
    return classify_activity(names.get(aid, ""))


def daily_op_hours(archetype_key: str) -> float:
    """운영 스케줄의 하루 적분값(=등가 운영시간/일). 급탕 peak-flow 산정에 사용.
    DHW가 op 스케줄로 변조되므로, 일일 사용량을 맞추려면 이 값으로 나눠야 한다."""
    occ = ASHRAE_OCC.get(archetype_key)
    if occ:
        return max(sum(occ["weekday"]), 1.0)
    arch = ARCHETYPES.get(archetype_key, {})
    frac = arch.get("op_fraction", 0.1)
    s, e = arch.get("op_hours", (0, 24))
    return max(frac * (e - s), 1.0)

# ── 시간별 재실률 (출처: ASHRAE 90.1 / DOE Prototype, openstudio-standards) ─────
# 각 아키타입의 평일/주말 24시간 재실 프로파일. op(조명/기기/재실)에 그대로 쓰고,
# 냉난방은 이 값이 OCC_THRESHOLD 이상인 시간만 설정온도로 본다.
OCC_THRESHOLD = 0.15
ASHRAE_OCC = {
    "office": {  # OfficeMedium BLDG_OCC_SCH
        "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2, 0.95, 0.95, 0.95, 0.95, 0.5, 0.95, 0.95, 0.95, 0.95, 0.3, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05],
        "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.1, 0.3, 0.3, 0.3, 0.3, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "residential": {  # ApartmentHighRise OCC_APT_SCH
        "weekday": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.85, 0.39, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.3, 0.52, 0.87, 0.87, 0.87, 1.0, 1.0, 1.0],
        "weekend": [1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 0.85, 0.39, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.25, 0.3, 0.52, 0.87, 0.87, 0.87, 1.0, 1.0, 1.0],
    },
    "lodging": {  # SmallHotel GuestRoom Occ
        "weekday": [0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.5, 0.28, 0.28, 0.13, 0.13, 0.13, 0.13, 0.13, 0.13, 0.2, 0.35, 0.35, 0.35, 0.5, 0.5, 0.58, 0.65, 0.65],
        "weekend": [0.65, 0.65, 0.65, 0.65, 0.65, 0.65, 0.5, 0.34, 0.34, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.2, 0.34, 0.35, 0.65, 0.65, 0.5, 0.5, 0.5],
    },
    "retail": {  # RetailStandalone BLDG_OCC_SCH
        "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2, 0.5, 0.5, 0.7, 0.7, 0.7, 0.7, 0.8, 0.7, 0.5, 0.5, 0.3, 0.3, 0.0, 0.0, 0.0],
        "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.2, 0.5, 0.6, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.6, 0.2, 0.2, 0.2, 0.1, 0.0, 0.0],
    },
    "restaurant": {  # FullServiceRestaurant Bldg Occ
        "weekday": [0.05, 0.0, 0.0, 0.0, 0.0, 0.05, 0.1, 0.4, 0.4, 0.4, 0.2, 0.5, 0.8, 0.7, 0.4, 0.2, 0.25, 0.5, 0.8, 0.8, 0.8, 0.5, 0.35, 0.2],
        "weekend": [0.05, 0.0, 0.0, 0.0, 0.0, 0.0, 0.05, 0.5, 0.5, 0.4, 0.2, 0.45, 0.5, 0.5, 0.35, 0.3, 0.3, 0.3, 0.7, 0.9, 0.7, 0.65, 0.55, 0.35],
    },
    "education": {  # SecondarySchool Bldg Occ
        "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.7, 0.15, 0.15, 0.15, 0.15, 0.15, 0.0, 0.0, 0.0],
        "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "university": {  # College BLDG_OCC_SCH
        "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.95, 0.15, 0.15, 0.15, 0.15, 0.15, 0.0, 0.0, 0.0],
        "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "healthcare": {  # Hospital BLDG_OCC_SCH
        "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.5, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.8, 0.5, 0.3, 0.3, 0.2, 0.2, 0.0, 0.0],
        "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 0.3, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0],
    },
    "lab": {  # Lab_OCC_SCH
        "weekday": [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.2, 0.9, 0.9, 0.45, 0.45, 0.9, 0.9, 0.9, 0.9, 0.9, 0.3, 0.1, 0.1, 0.1, 0.05, 0.05, 0.05],
        "weekend": [0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.1, 0.1, 0.3, 0.3, 0.3, 0.3, 0.1, 0.1, 0.1, 0.1, 0.1, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05, 0.05],
    },
    "assembly": {  # SecondarySchool Gym Occ
        "weekday": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.95, 0.95, 0.95, 0.95, 0.95, 0.0, 0.0, 0.0],
        "weekend": [0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.35, 0.95, 0.95, 0.95, 0.95, 0.95, 0.0, 0.0, 0.0],
    },
}

# ── 용도명 키워드 → 아키타입 (위에서부터 먼저 맞는 것 채택) ─────────────────────
_KEYWORD_RULES = [
    (["domestic", "en suite", "bedroom", "lounge", "dwelling", "living", "bathroom", "washing"], "residential"),
    (["hotel", "guest", "dormitory", "기숙"], "lodging"),
    (["sales area", "shop", "retail", "store unit", "판매"], "retail"),
    (["food preparation", "eating", "drinking", "restaurant", "kitchen", "음식", "식당"], "restaurant"),
    (["university", "college", "campus", "대학", "lecture theatre", "lecture theater"], "university"),
    (["classroom", "lecture", "teaching", "seminar", "library", "school", "교육", "강의"], "education"),
    (["ward", "surgery", "patient", "hospital", "treatment", "consulting", "post mortem", "medical", "의료", "병"], "healthcare"),
    (["laboratory", "industrial process", "workshop", "실험", "공정"], "lab"),
    (["assembly", "performance", "stage", "sports hall", "swimming pool", "gym", "fitness", "hall", "sauna", "pool", "집회", "공연", "체육"], "assembly"),
    (["office", "reception", "사무"], "office"),
    # 보조/비주거 공간
    (["store room", "warehouse", "storage", "circulation", "corridor", "stairway", "stair",
      "vestibule", "chase", "shaft", "lift", "elevator", "parking", "toilet", "changing", "locker",
      "laundry", "plant room", "boiler", "mechanical", "lobby",
      "창고", "복도", "계단", "화장실", "기계", "주차"], "auxiliary"),
]


# ── Space 이름 키워드 → 대표 SBEM activityId (parser의 용도 추론용) ─────────────
# gbXML에 spaceType이 없을 때 Space 이름(예: "1 BATHROOM")으로 용도를 추정한다.
# ⚠️ 순서 중요: 'room'은 다른 단어의 부분문자열(BATHROOM, STORE ROOM 등)이므로 맨 뒤.
# 합성 용도(ActivityIdList에 없는 용도) — load_activity_names가 병합
SYNTHETIC_ACTIVITIES = {
    9001: "University Campus",   # → classify_activity: university
}

_NAME_TO_ACTIVITY = [
    (["university", "college", "campus", "대학"], 9001),  # 대학 → 합성 용도
    (["bathroom", "washing"], 1185),   # Domestic Bathroom
    (["toilet", " wc", "restroom"], 1182),  # Domestic Toilet
    (["kitchen"], 1183),               # Domestic Kitchen
    (["sauna", "gym", "fitness", "sports", "pool"], 1106),  # Fitness/gym
    (["dining"], 1181),                # Domestic Dining
    (["lounge", "living", "communal", "common space"], 1179),  # Domestic Lounge
    (["store", "storage", "parking", "warehouse"], 1100),  # Store Room
    (["stair", "vestibule", "chase", "shaft", "lift", "elevator",
      "corridor", "circulation", "lobby", "locker", "changing"], 1101),  # Circulation
    (["plant", "boiler", "mechanical", "vent", "heating", "electrical"], 1104),  # Plant room
    (["office"], 1105),
    # ── 한글 Space 이름 ──────────────────────────────────────────────
    # 영문 키워드만 있어 한글 실명(예: "103 계단실", "101 남자화장실")이 전부
    # DEFAULT_ACTIVITY_ID(1105 일반 사무실)로 폴백되던 문제 수정. 이 폴백은
    # 이름만 잘못 표시하는 게 아니라 ep_simulator가 activity_names[1105]="Generic
    # Office Area"→classify_activity()로 office 아키타입(사무 스케줄·냉난방
    # 설정)을 배정해, 실제로는 비공조·저점유인 화장실·계단실이 업무시간 내내
    # 냉난방되는 것처럼 계산되는 에너지 오차로 이어진다. 아래는 일반(비주거)
    # 카테고리로 매핑해 auxiliary 아키타입(24h 저점유, 냉난방 setback)이 정확히
    # 배정되도록 한다 — _KEYWORD_RULES의 한글 매핑과 동일한 의도.
    (["화장실", "욕실", "세면", "샤워"], 1102),        # Toilet
    (["계단", "복도", "승강기", "엘리베이터"], 1101),  # Circulation
    (["창고", "주차"], 1100),                          # Store Room
    (["기계실", "전기실", "설비실", "펌프실"], 1104),  # Plant room
    (["로비", "접수", "안내"], 1103),                  # Reception
    (["사무", "민원", "상담", "회의", "전산"], 1105),   # Generic Office Area
    (["bedroom", "room"], 1180),       # 남은 ROOM = 침실(주거) — 반드시 맨 뒤
]
DEFAULT_ACTIVITY_ID = 1105


def activity_id_from_space_name(name: str) -> int:
    """Space 이름으로 대표 용도(activityId)를 추정한다. 못 찾으면 1105(사무) 폴백."""
    if name:
        low = name.lower()
        for keywords, aid in _NAME_TO_ACTIVITY:
            if any(kw in low for kw in keywords):
                return aid
    return DEFAULT_ACTIVITY_ID


def classify_activity(name: str) -> str:
    """용도명을 아키타입 키로 분류한다."""
    if not name:
        return DEFAULT_ARCHETYPE
    low = name.lower()
    for keywords, arch in _KEYWORD_RULES:
        if any(kw in low for kw in keywords):
            return arch
    return DEFAULT_ARCHETYPE


def load_activity_names(db_dir: str) -> dict:
    """ActivityIdList.txt(#ID #Name) → {activity_id(int): name(str)}.
    ActivityIdList에 없는 합성 용도(SYNTHETIC_ACTIVITIES)도 함께 병합한다."""
    names = dict(SYNTHETIC_ACTIVITIES)
    if not db_dir:
        return names
    path = None
    for root, _dirs, files in os.walk(db_dir):
        for f in files:
            if f.lower() == "activityidlist.txt":
                path = os.path.join(root, f)
                break
        if path:
            break
    if not path:
        return names
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                m = re.match(r"\s*#(\d+)\s*#(.+?)\s*$", line)
                if m:
                    names[int(m.group(1))] = m.group(2).strip()
    except Exception:
        pass
    return names


def _hourly_to_compact_day(values24):
    """24개 시간값 → 'Until: HH:00, v' 세그먼트(연속 동일값 압축)."""
    segs = []
    i, n = 0, len(values24)
    while i < n:
        v = values24[i]
        j = i
        while j + 1 < n and values24[j + 1] == v:
            j += 1
        segs.append(f"Until: {j + 1:02d}:00, {v}")
        i = j + 1
    return ", ".join(segs)


def _day_block(weekday24, weekend24):
    """한 'Through' 구간의 For: 블록들 (평일/주말·공휴일·기타일)."""
    wd = _hourly_to_compact_day(weekday24)
    we = _hourly_to_compact_day(weekend24)
    return (f"For: Weekdays, {wd}, For: Weekends, {we}, "
            f"For: Holidays, {we}, For: AllOtherDays, {we}")


def _weekly_compact(weekday24, weekend24):
    """연중 동일 평일/주말 24h 배열 → Schedule:Compact 본문."""
    return f"Through: 12/31, {_day_block(weekday24, weekend24)}"


# ── 냉방기간(냉방 가용 계절) ────────────────────────────────────────────────
# 실건물은 동절기에 냉방을 가동하지 않지만, 연중 동일 냉방 설정(26℃)이면 겨울에도
# 일사·내부발열로 존 온도가 설정을 넘는 순간 시뮬레이션이 냉방을 돌린다(1~2월 유령 냉방).
# 냉방기간 밖에는 설정온도를 COOLING_OFF_TEMP로 올려 냉방을 원천 차단한다.
# (서모스탯 기준이므로 WindowAC·PTHP·이상부하 전 모드에 동일하게 적용된다)
COOLING_SEASON_START = (5, 1)    # 냉방기간 시작 (5/1)
COOLING_SEASON_END = (10, 31)    # 냉방기간 끝 (10/31)
COOLING_OFF_TEMP = 35.0          # 기간 밖 냉방 설정온도 — 실내가 도달할 수 없는 값


def monthly_ground_temperatures(heat_setpoint: float = 20.0,
                                cool_setpoint: float = 26.0,
                                offset_k: float = 2.0) -> list:
    """슬래브 하부 월별 지중온도(℃) 12개.

    EnergyPlus 매뉴얼 지침에 따라 '실내온도보다 약 2K 낮은 값'을 쓴다.
    난방기에는 난방 설정온도, 냉방기에는 냉방 설정온도를 기준으로 삼고,
    냉방기간(COOLING_SEASON_START~END)은 스케줄 쪽 정의를 그대로 따른다.

    EPW 헤더의 비교란 토양온도를 쓰지 않는 이유는 idf_builder
    .add_ground_temperatures() 주석 참조.
    """
    start_m = COOLING_SEASON_START[0]
    end_m = COOLING_SEASON_END[0]
    out = []
    for m in range(1, 13):
        in_cooling = start_m <= m <= end_m
        base = cool_setpoint if in_cooling else heat_setpoint
        out.append(round(base - offset_k, 2))
    return out


def _cooling_season_segments(segments):
    """(학사)세그먼트에 냉방기간 마스크를 일 단위로 교차해 [(through, state)]로 재압축.

    state: 'off'(냉방기간 밖) | 'session'(기간 내 재학/일반) | 'vac'(기간 내 방학)
    segments는 (Through "M/D", 재학여부) 오름차순, 마지막 12/31 가정.
    """
    import datetime as _dt

    def _md(s):
        m, d = s.split("/")
        return (int(m), int(d))

    seg_keys = [(_md(t), b) for t, b in segments]
    days = []
    for i in range(365):  # 비윤년 기준 (E+ 기본 RunPeriod와 동일)
        d = _dt.date(2025, 1, 1) + _dt.timedelta(days=i)
        md = (d.month, d.day)
        in_session = next(b for t, b in seg_keys if md <= t)
        in_season = COOLING_SEASON_START <= md <= COOLING_SEASON_END
        state = ("session" if in_session else "vac") if in_season else "off"
        days.append((md, state))

    out = []
    for i, (md, st) in enumerate(days):
        if i + 1 == len(days) or days[i + 1][1] != st:
            out.append((f"{md[0]}/{md[1]}", st))
    return out


def cooling_compact_with_season(session_wd, session_we, vac_day=None, segments=None):
    """냉방 Schedule:Compact 본문 — 냉방기간 밖은 미가동(고온 설정)으로 마스크."""
    off_day = [COOLING_OFF_TEMP] * 24
    segs = segments or [("12/31", True)]
    parts = []
    for through, state in _cooling_season_segments(segs):
        if state == "session":
            parts.append(f"Through: {through}, {_day_block(session_wd, session_we)}")
        elif state == "vac":
            v = vac_day if vac_day is not None else session_we
            parts.append(f"Through: {through}, {_day_block(v, v)}")
        else:
            parts.append(f"Through: {through}, {_day_block(off_day, off_day)}")
    return ", ".join(parts)


def _seasonal_compact(segments, session_wd, session_we, vac_day):
    """학기/방학 등 날짜구간별 Schedule:Compact. segments=[(through, 재학여부)...].
    재학=session 평일/주말 배열, 방학=vac_day 종일."""
    parts = []
    for through, in_session in segments:
        if in_session:
            parts.append(f"Through: {through}, {_day_block(session_wd, session_we)}")
        else:
            parts.append(f"Through: {through}, {_day_block(vac_day, vac_day)}")
    return ", ".join(parts)


def build_schedules(archetype_key: str, heat_set: float, cool_set: float) -> dict:
    """아키타입 + 존 설정온도로 운영/난방/냉방 Schedule:Compact 본문을 만든다.

    반환: {op, heating, cooling}
      op      : 시간별 재실률(ASHRAE) — 조명/기기/재실 구동
      heating : 재실 ≥ OCC_THRESHOLD 시간만 heat_set, 그 외 heat_setback
      cooling : 재실 ≥ OCC_THRESHOLD 시간만 cool_set, 그 외 cool_setback
    (타이밍=ASHRAE 시간프로파일, 온도=사용자 존 설정. auxiliary는 상시 저조도)
    """
    arch = ARCHETYPES.get(archetype_key, ARCHETYPES[DEFAULT_ARCHETYPE])
    occ = ASHRAE_OCC.get(archetype_key)

    if occ is None:
        # ASHRAE 프로파일 없는 보조공간: 상시 저조도, 냉난방은 종일 setback
        frac = arch.get("op_fraction", 0.0)
        s, e = arch.get("op_hours", (0, 24))
        op_day = [frac if s <= h < e else 0.0 for h in range(24)]
        hb = [arch["heat_setback"]] * 24
        cb = [arch["cool_setback"]] * 24
        return {
            "op": _weekly_compact(op_day, op_day),
            "heating": _weekly_compact(hb, hb),
            "cooling": cooling_compact_with_season(cb, cb),
        }

    wd, we = occ["weekday"], occ["weekend"]

    def setp(occ_day, on, off):
        return [on if v >= OCC_THRESHOLD else off for v in occ_day]

    cal = arch.get("academic_calendar")
    if cal:
        # 학교: 학기엔 ASHRAE 프로파일, 방학엔 저점유(vacation_occ)
        segs = cal["segments"]
        vac = cal.get("vacation_occ", 0.1)
        op_vac = [vac] * 24
        # 방학 점유가 임계 미만이면 냉난방은 종일 setback
        heat_vac = [(heat_set if vac >= OCC_THRESHOLD else arch["heat_setback"])] * 24
        cool_vac = [(cool_set if vac >= OCC_THRESHOLD else arch["cool_setback"])] * 24
        return {
            "op": _seasonal_compact(segs, wd, we, op_vac),
            "heating": _seasonal_compact(segs, setp(wd, heat_set, arch["heat_setback"]),
                                         setp(we, heat_set, arch["heat_setback"]), heat_vac),
            "cooling": cooling_compact_with_season(
                setp(wd, cool_set, arch["cool_setback"]),
                setp(we, cool_set, arch["cool_setback"]),
                vac_day=cool_vac, segments=segs),
        }

    return {
        "op": _weekly_compact(wd, we),
        "heating": _weekly_compact(setp(wd, heat_set, arch["heat_setback"]),
                                   setp(we, heat_set, arch["heat_setback"])),
        "cooling": cooling_compact_with_season(setp(wd, cool_set, arch["cool_setback"]),
                                                setp(we, cool_set, arch["cool_setback"])),
    }
