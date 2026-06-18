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

# ── 아키타입별 표준 스케줄 (ECO2 구조 기반 근사) ───────────────────────────────
# 시간은 24h 기준. 빈 리스트 = 해당 요일 비운영(종일 설정후퇴).
ARCHETYPES = {
    "office": {
        "label": "업무시설(사무)",
        "weekday": [(9, 18)], "weekend": [], "holiday": [],
        "heat_setback": 16.0, "cool_setback": 30.0,
    },
    "residential": {
        "label": "주거",
        # 거주: 저녁~아침 위주 + 주말 종일 (낮 시간 외출 가정)
        "weekday": [(0, 9), (18, 24)], "weekend": [(0, 24)], "holiday": [(0, 24)],
        "heat_setback": 18.0, "cool_setback": 28.0,
    },
    "lodging": {
        "label": "숙박(객실/기숙)",
        "weekday": [(0, 9), (17, 24)], "weekend": [(0, 24)], "holiday": [(0, 24)],
        "heat_setback": 18.0, "cool_setback": 28.0,
    },
    "retail": {
        "label": "판매시설",
        "weekday": [(10, 20)], "weekend": [(10, 20)], "holiday": [(10, 20)],
        "heat_setback": 16.0, "cool_setback": 30.0,
    },
    "restaurant": {
        "label": "음식점",
        # 점심·저녁 영업 (매일)
        "weekday": [(10, 15), (17, 22)], "weekend": [(10, 15), (17, 22)], "holiday": [(10, 15), (17, 22)],
        "heat_setback": 16.0, "cool_setback": 30.0,
    },
    "education": {
        "label": "교육연구(학교)",
        "weekday": [(9, 17)], "weekend": [], "holiday": [],
        "heat_setback": 16.0, "cool_setback": 30.0,
    },
    "healthcare": {
        "label": "의료시설",
        "weekday": [(0, 24)], "weekend": [(0, 24)], "holiday": [(0, 24)],
        "heat_setback": 22.0, "cool_setback": 26.0,
    },
    "lab": {
        "label": "연구/산업(실험·공정)",
        "weekday": [(0, 24)], "weekend": [(0, 24)], "holiday": [(0, 24)],
        "heat_setback": 18.0, "cool_setback": 28.0,
    },
    "assembly": {
        "label": "집회/체육/공연",
        "weekday": [(9, 22)], "weekend": [(9, 22)], "holiday": [(9, 22)],
        "heat_setback": 16.0, "cool_setback": 30.0,
    },
    "auxiliary": {
        "label": "보조공간(복도·창고·화장실·기계실)",
        # 상시 최소 난방만, 적극 냉난방 없음
        "weekday": [], "weekend": [], "holiday": [],
        "heat_setback": 15.0, "cool_setback": 32.0,
    },
}

DEFAULT_ARCHETYPE = "office"

# ── 용도명 키워드 → 아키타입 (위에서부터 먼저 맞는 것 채택) ─────────────────────
_KEYWORD_RULES = [
    (["domestic", "en suite", "bedroom", "lounge", "dwelling", "living", "bathroom", "washing"], "residential"),
    (["hotel", "guest", "dormitory", "기숙"], "lodging"),
    (["sales area", "shop", "retail", "store unit", "판매"], "retail"),
    (["food preparation", "eating", "drinking", "restaurant", "kitchen", "음식", "식당"], "restaurant"),
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
_NAME_TO_ACTIVITY = [
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
    """ActivityIdList.txt(#ID #Name) → {activity_id(int): name(str)}."""
    names = {}
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


def _segments_for_day(periods, occ_val, setback_val):
    """하루치 'Until:' 세그먼트 생성. periods=[(s,e)...], 운영=occ_val, 그 외=setback_val."""
    if not periods:
        return f"Until: 24:00, {setback_val}"
    segs = []
    cursor = 0
    for (s, e) in sorted(periods):
        s = max(0, min(24, int(s)))
        e = max(0, min(24, int(e)))
        if s > cursor:
            segs.append(f"Until: {s:02d}:00, {setback_val}")
        segs.append(f"Until: {e:02d}:00, {occ_val}")
        cursor = e
    if cursor < 24:
        segs.append(f"Until: 24:00, {setback_val}")
    return ", ".join(segs)


def _compact_text(arch, occ_val_map):
    """요일유형별로 Schedule:Compact 본문 생성. occ_val_map={'occ':..,'setback':..}."""
    occ, setback = occ_val_map["occ"], occ_val_map["setback"]
    parts = ["Through: 12/31"]
    for daytype, for_kw in _DAYTYPE_FOR.items():
        seg = _segments_for_day(arch.get(daytype, []), occ, setback)
        parts.append(f"For: {for_kw}, {seg}")
    # 명시되지 않은 날(설계일 등)은 비운영 처리
    parts.append(f"For: AllOtherDays, Until: 24:00, {setback}")
    return ", ".join(parts)


def build_schedules(archetype_key: str, heat_set: float, cool_set: float) -> dict:
    """아키타입 + 존 설정온도로 운영/난방/냉방 Schedule:Compact 본문을 만든다.

    반환: {op, heating, cooling} (각각 Schedule:Compact body 문자열)
      op      : 재실/조명/기기 가동률 (운영=1.0, 비운영=0.0)
      heating : 운영=heat_set, 비운영=heat_setback
      cooling : 운영=cool_set, 비운영=cool_setback
    """
    arch = ARCHETYPES.get(archetype_key, ARCHETYPES[DEFAULT_ARCHETYPE])
    return {
        "op": _compact_text(arch, {"occ": 1.0, "setback": 0.0}),
        "heating": _compact_text(arch, {"occ": heat_set, "setback": arch["heat_setback"]}),
        "cooling": _compact_text(arch, {"occ": cool_set, "setback": arch["cool_setback"]}),
    }
