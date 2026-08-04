"""에너지 요금 — **소비량을 값으로 바꾸는 것만** 담당한다.

여기 오면 안 되는 것: 물리 집계(얼마를 썼나), 자본비, 현금흐름, 권고.

⚠️ 요율은 **여기가 단일 소스**다. 요금 개정 시 이 파일만 고치면 된다.
"""
from dataclasses import dataclass
from typing import Dict, List, Sequence, Tuple

from src.domain.models import EnergyTimeSeries

# ── 전기요금: 2026.4.16 시행 '일반용(갑) 저압' 계절 요금 (원/kWh) ──
# (한전 요금표 종합 — 일반 비주거. 저압은 시간대별 차등 없이 계절 평탄)
ELEC_RATE_SUMMER = 123.6   # 6~8월
ELEC_RATE_WINTER = 110.8   # 11~2월
ELEC_RATE_SPRING = 86.4    # 3~5, 9~10월
ELEC_BASE_CHARGE = 5230    # 일반용 저압 기본요금 (원/kW)

# ── 시간대별(TOU) 요율: 일반용(을) 고압A 선택Ⅱ (원/kWh) ──
# 시간별 출력이 있으면 TOU, 월별 출력뿐이면 위 계절 평탄 요율을 쓴다.
# (엄밀히는 계약 종별을 따라야 하나 현재는 출력 주기 기준 근사)
TOU_RATES = {
    "summer": {"peak": 147.3, "mid": 109.0, "off": 56.1},   # 6~8월
    "winter": {"peak": 137.9, "mid": 109.0, "off": 61.6},   # 11~2월
    "spring": {"peak": 65.5,  "mid": 65.5,  "off": 56.1},   # 3~5, 9~10월 (피크 없음)
}

SUMMER_MONTHS = (6, 7, 8)
WINTER_MONTHS = (11, 12, 1, 2)

# 지역난방: KDHC 열요금표(2024.7.1, 부가세 별도) 주택용 난방 단일요금
#   1 Mcal = 1.163 kWh
HEAT_RATE_MCAL = 112.32
HEAT_RATE_KWH = HEAT_RATE_MCAL / 1.163      # ≈ 96.6 원/kWh

# ── 난방 열원별 {요금, 1차에너지계수, CO2계수} ──
# 열원에 따라 요금·1차·CO2 가 모두 달라진다. 지열/히트펌프는 전기로 본다.
HEAT_SOURCE_DB: Dict[int, Dict[str, object]] = {
    1:  {"label": "가스보일러",     "rate": 78.12,            "primary": 1.10,  "co2": 0.232},
    2:  {"label": "전기(히트펌프)", "rate": ELEC_RATE_WINTER, "primary": 2.75,  "co2": 0.466},
    4:  {"label": "등유보일러",     "rate": 141.92,           "primary": 1.10,  "co2": 0.260},
    11: {"label": "지역난방",       "rate": HEAT_RATE_KWH,    "primary": 0.728, "co2": 0.200},
}
DEFAULT_HEAT_SOURCE = 11

# ── PV ──
# ⚠️ 이 상수는 배치·방위·기울기를 반영하지 않는 개략 추정이다.
# 문헌 조사 결과 북향 수직 설치에서는 50% 이상 과대할 수 있다
# (docs/pv-literature-summary.md). PVWatts 전환 시 제거 대상.
PV_YIELD_KWH_PER_KW = 1300.0
PV_DAY_START_HOUR = 9
PV_DAY_END_HOUR = 17


def tou_rate(month: int, hour: int) -> float:
    """시간대별 요율. 계절·시간 구간은 한전 요금표를 따른다."""
    if month in SUMMER_MONTHS:
        r = TOU_RATES["summer"]
        if 13 <= hour < 17:
            return r["peak"]
        if (9 <= hour < 13) or (17 <= hour < 23):
            return r["mid"]
        return r["off"]
    if month in WINTER_MONTHS:
        r = TOU_RATES["winter"]
        if (9 <= hour < 12) or (16 <= hour < 19):
            return r["peak"]
        if (12 <= hour < 16) or (19 <= hour < 23):
            return r["mid"]
        return r["off"]
    r = TOU_RATES["spring"]
    return r["mid"] if 9 <= hour < 23 else r["off"]


def seasonal_rate(month: int) -> float:
    """월별 출력만 있을 때 쓰는 계절 평탄 요율."""
    if month in SUMMER_MONTHS:
        return ELEC_RATE_SUMMER
    if month in WINTER_MONTHS:
        return ELEC_RATE_WINTER
    return ELEC_RATE_SPRING


def electricity_rates(series: EnergyTimeSeries) -> List[float]:
    """행별 전기 요율. 시간별이면 TOU, 월별이면 계절 평탄."""
    if series.resolution.value == "hourly":
        return [tou_rate(m, h) for m, h in zip(series.months, series.hours)]
    return [seasonal_rate(m) for m in series.months]


@dataclass(frozen=True)
class CarrierSplit:
    """소비를 전기와 열로 나눈 결과.

    ⚠️ **히트펌프면 난방이 전기로 간다.** 그러면 열 요금에는 급탕만 남는다.
    이 배분을 틀리면 난방이 통째로 잘못된 요율을 맞는다.
    """
    electricity_kwh: Tuple[float, ...]
    heat_kwh: Tuple[float, ...]
    heating_is_electric: bool


def split_by_carrier(series: EnergyTimeSeries, ventilation_kwh: Sequence[float],
                     *, use_pthp: bool) -> CarrierSplit:
    """시간별 소비를 전기/열로 배분한다."""
    elec, heat = [], []
    for i in range(series.row_count):
        base_elec = (series.cooling_consumption_kwh[i] + series.lighting_kwh[i]
                     + series.equipment_kwh[i] + float(ventilation_kwh[i]))
        if use_pthp:
            elec.append(base_elec + series.heating_consumption_kwh[i])
            heat.append(series.dhw_kwh[i])
        else:
            elec.append(base_elec)
            heat.append(series.heating_consumption_kwh[i] + series.dhw_kwh[i])
    return CarrierSplit(tuple(elec), tuple(heat), heating_is_electric=use_pthp)


def apply_pv_self_consumption(electricity_kwh: Sequence[float], hours: Sequence[int],
                              pv_capacity_kw: float) -> Tuple[float, ...]:
    """PV 자가소비를 전기 소비에서 차감한다.

    연간 발전량을 주간(9~17시)에 균등 분배해 시간별 소비에서 뺀다.
    TOU 와 상호작용해 '비싼 낮 요금'을 깎는 실제 효과가 반영된다.

    ⚠️ **잉여 발전은 버린다** — 역송 보상(상계거래) 미반영, 보수적 추정.
    ⚠️ 배치·방위·기울기를 반영하지 않는 개략 추정이다(PV_YIELD_KWH_PER_KW 주석 참조).
    """
    if not pv_capacity_kw or pv_capacity_kw <= 0:
        return tuple(float(v) for v in electricity_kwh)

    day_mask = [PV_DAY_START_HOUR <= h < PV_DAY_END_HOUR for h in hours]
    day_steps = sum(day_mask)
    if day_steps == 0:
        return tuple(float(v) for v in electricity_kwh)

    gen_per_step = (pv_capacity_kw * PV_YIELD_KWH_PER_KW) / day_steps
    return tuple(max(float(v) - (gen_per_step if is_day else 0.0), 0.0)
                 for v, is_day in zip(electricity_kwh, day_mask))


def heat_source_entry(heat_source_id: int, *, is_geothermal: bool = False) -> Dict[str, object]:
    """열원 정보. 지열/히트펌프는 전기로 본다."""
    key = 2 if is_geothermal else heat_source_id
    return HEAT_SOURCE_DB.get(key, HEAT_SOURCE_DB[DEFAULT_HEAT_SOURCE])


def annual_bills(electricity_kwh: Sequence[float], heat_kwh: Sequence[float],
                 rates: Sequence[float], heat_rate_won_per_kwh: float) -> Tuple[float, float]:
    """연간 전기·열 요금(기본요금 제외)."""
    elec = sum(float(v) * float(r) for v, r in zip(electricity_kwh, rates))
    heat = sum(float(v) for v in heat_kwh) * heat_rate_won_per_kwh
    return elec, heat
