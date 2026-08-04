"""EnergyPlus 출력(CSV) → 도메인 시계열 계약.

**여기서 끝나는 것**: 열 이름 찾기, 단위 환산, HVAC 모드별 요구량/소비량 산출.
**여기 오면 안 되는 것**: 요금·자본비·권고. 그건 economics 의 몫이다.

`cost_analyzer.calculate()` 743줄 안에 섞여 있던 것을 옮겼다. 순수 이동이며,
계산식은 한 줄도 바꾸지 않았다 — 다만 결과를 dict/지역변수가 아니라
`EnergyTimeSeries` 계약으로 돌려준다.
"""
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from src.domain.models import (
    ConsumptionBasis,
    ConversionStep,
    EnergyCategory,
    EnergyConversionContext,
    EnergyTimeSeries,
    J_TO_KWH,
    TimeResolution,
)

# ── 설비 효율 ──
# ⚠️ **요금표가 아니라 엔진 변환 계수다.** economics 가 아니라 여기 있어야 한다 —
# 요구량을 소비량으로 바꾸는 물리 변환이고, 요금 개정과 무관하게 유지된다.
HEATING_EFF_DB: Dict[int, Dict[int, float]] = {   # {hvacSystemId: {열원id: 효율·COP}}
    1: {1: 0.85, 2: 2.50, 4: 0.80, 11: 0.95},
    2: {2: 3.50, 11: 1.00},
    3: {1: 0.82, 2: 3.00, 11: 0.95},
    5: {1: 0.80, 2: 2.80, 4: 0.75},
}
COOLING_EFF_DB: Dict[int, float] = {1: 3.50, 2: 4.20, 3: 3.20, 5: 2.80}

DEFAULT_HEAT_SOURCE = 11          # 미지정 시 지역난방
DEFAULT_COOLING_COP = 2.80
GEOTHERMAL_COPS = (4.5, 5.0)      # (난방, 냉방)

# 미터가 없을 때 쓰는 보수적 대표 COP·효율
FALLBACK_PTHP_HEATING_COP = 3.5
FALLBACK_PTHP_COOLING_COP = 4.2
FALLBACK_DX_COOLING_COP = 3.3

# 외기 처리 에너지 (kWh/m³). 환기 체적을 에너지로 바꾸는 계수.
VENT_ENERGY_PER_M3 = 0.8
AIR_DENSITY_KG_M3 = 1.2
MONTHLY_HOURS = 730.0             # 월별 CSV 일 때 시간 환산


@dataclass
class ParsedEnergyPlusOutputs:
    """CSV 한 번 읽어 뽑아낸 것 전부.

    시계열과 표면 결과를 함께 담는 이유: 따로 뽑으면 표면 쪽이 계속 원본
    DataFrame 에 매달려 파싱 계층이 분리되지 않는다.
    `dataframe` 은 아직 남은 계산(요금·PV·월별 집계)이 쓰고 있어 과도기적으로
    노출한다 — 그 계산들이 계약 위로 옮겨오면 제거한다.
    """
    timeseries: EnergyTimeSeries
    surface_thermal: Dict[str, Any]
    surface_airflow: Dict[str, Any]
    dataframe: Any = None


def _cols(df, *needles: str) -> List[str]:
    """모든 조각을 포함하는 열 이름."""
    return [c for c in df.columns if all(n in c for n in needles)]


def _first_col(df, *needles: str) -> Optional[str]:
    found = _cols(df, *needles)
    return found[0] if found else None


def _sum_kwh(df, cols, n_rows, np_mod):
    """열들을 합쳐 J → kWh. 열이 없으면 0 배열."""
    if not cols:
        return np_mod.zeros(n_rows)
    return df[cols].sum(axis=1).values / J_TO_KWH


def detect_resolution(df) -> TimeResolution:
    """해상도를 판정한다.

    ⚠️ **행 수로 추정하면 안 된다.** 예전 코드(그리고 내가 처음 옮긴 판본)는
    `len(df) > 365` 를 썼는데, 그것은 데이터가 무엇인지가 아니라 얼마나 많은지를
    본 것이다. 365행 이하의 정상적인 시간별 부분 실행(설계일·부분 기간)이
    월별로 오판되고, 그러면 환기에 730배가 붙어 결과가 통째로 틀어진다.

    EnergyPlus 는 **모든 열 이름 끝에 보고주기를 적는다**
    (`...Lights Electricity Energy [J](Hourly)`). 그것을 1순위로 쓴다.
    없으면 타임스탬프 간격을 보고, 그래도 모르면 마지막으로 행 수를 쓴다.
    """
    names = " ".join(str(c) for c in df.columns)
    hourly_tags = names.count("(Hourly)") + names.count("(TimeStep)")
    monthly_tags = names.count("(Monthly)")
    if hourly_tags or monthly_tags:
        return TimeResolution.HOURLY if hourly_tags >= monthly_tags else TimeResolution.MONTHLY

    # 2순위: 타임스탬프에 시각이 붙어 있고 서로 다른 시각이 나오면 시간별이다.
    first = df.iloc[:, 0].astype(str)
    hours = first.str.extract(r"\s+(\d{1,2}):")[0].dropna()
    if len(hours) > 1 and hours.nunique() > 1:
        return TimeResolution.HOURLY

    # 3순위(호환 폴백): 행 수. 여기까지 오면 판정 근거가 약하다.
    return TimeResolution.HOURLY if len(df) > 365 else TimeResolution.MONTHLY


def extract_time_axis(df, np_mod) -> Tuple[TimeResolution, Any, Any]:
    """해상도와 월·시각 축을 뽑는다."""
    total_rows = len(df)
    resolution = detect_resolution(df)
    first = df.iloc[:, 0].astype(str)
    has_stamp = first.str.contains(r"\d{1,2}/\d{1,2}", regex=True).any()

    if resolution is TimeResolution.HOURLY and has_stamp:
        months = first.str.extract(r"(\d{1,2})/\d{1,2}")[0].fillna(1).astype(int).values
        hours = first.str.extract(r"\s+(\d{1,2}):")[0].fillna(12).astype(int).values
        return resolution, months, hours

    # 월별(또는 타임스탬프가 없는 경우): 1월부터 순서대로 매긴다.
    months = np_mod.arange(1, min(13, total_rows + 1))
    if len(months) < total_rows:                     # 방어: 13행 이상인 월별 파일
        months = np_mod.resize(months, total_rows)
    return resolution, months, np_mod.full(total_rows, 12)


def parse_outputs(df, zones: List[dict], *, np_mod,
                  hvac_mode: str = "ideal",
                  heating_fuel: Optional[str] = None,
                  heating_fuel_eff: float = 0.9,
                  heat_source: int = DEFAULT_HEAT_SOURCE,
                  is_geothermal: bool = False) -> EnergyTimeSeries:
    """EnergyPlus DataFrame → `EnergyTimeSeries`.

    HVAC 모드에 따라 소비량 산출 방식이 다르다:
      - `pthp`/`fuel`: EnergyPlus **미터 실측**을 그대로 쓴다(COP 나눗셈 근사 제거)
      - `ideal`: 존별 요구량을 COP·효율로 나눈다
        ⚠️ **이상부하에서도 요구량 ≠ 소비량이다.** 어느 쪽인지는 `context` 가 기록한다.
    """
    n = len(df)
    resolution, months, hours = extract_time_axis(df, np_mod)

    h_cols = _cols(df, "Ideal Loads", "Heating Energy", "[J]")
    c_cols = _cols(df, "Ideal Loads", "Cooling Energy", "[J]")
    h_rate_cols = _cols(df, "Ideal Loads", "Heating Rate", "[W]")
    c_rate_cols = _cols(df, "Ideal Loads", "Cooling Rate", "[W]")
    l_cols = _cols(df, "Lights", "Electricity Energy", "[J]")
    e_cols = _cols(df, "Electric Equipment", "Electricity Energy", "[J]")
    # ⚠️ 급탕은 존마다 열이 따로 있으므로 **전부 합산**한다(예전 next() 는 1개만 잡아 과소).
    dhw_cols = _cols(df, "Water Use Equipment Heating Energy")
    vent_cols = _cols(df, "Mechanical Ventilation Mass Flow Rate", "[kg/s]")

    h_req = np_mod.zeros(n)
    c_req = np_mod.zeros(n)
    h_con = np_mod.zeros(n)
    c_con = np_mod.zeros(n)
    h_rate = np_mod.zeros(n)
    c_rate = np_mod.zeros(n)
    fan_kwh = np_mod.zeros(n)
    steps: List[ConversionStep] = []

    if hvac_mode in ("pthp", "fuel"):
        h_req = _sum_kwh(df, _cols(df, "Zone Air System Sensible Heating Energy"), n, np_mod)
        c_req = _sum_kwh(df, _cols(df, "Zone Air System Sensible Cooling Energy"), n, np_mod)
        ce_col = _first_col(df, "Cooling:Electricity", "[J]")
        fe_col = _first_col(df, "Fans:Electricity", "[J]")

        if hvac_mode == "pthp":
            he_col = _first_col(df, "Heating:Electricity", "[J]")
            if he_col:
                h_con = df[he_col].values / J_TO_KWH
                steps.append(ConversionStep(EnergyCategory.HEATING, ConsumptionBasis.METERED,
                                            source_name=he_col))
            else:
                h_con = h_req / FALLBACK_PTHP_HEATING_COP
                steps.append(ConversionStep(
                    EnergyCategory.HEATING, ConsumptionBasis.DERIVED_FROM_COP,
                    factor=FALLBACK_PTHP_HEATING_COP, source_name="Heating:Electricity",
                    note=f"실기기 미터가 없어 난방 요구량÷대표COP {FALLBACK_PTHP_HEATING_COP} 로 "
                         f"추정했습니다 — 실소비가 아닌 근사치입니다"))
            cool_fallback_cop = FALLBACK_PTHP_COOLING_COP
        else:
            hf_col = _first_col(df, f"Heating:{heating_fuel}", "[J]") if heating_fuel else None
            if hf_col:
                h_con = df[hf_col].values / J_TO_KWH
                steps.append(ConversionStep(EnergyCategory.HEATING, ConsumptionBasis.METERED,
                                            source_name=hf_col))
            else:
                h_con = h_req / heating_fuel_eff
                steps.append(ConversionStep(
                    EnergyCategory.HEATING, ConsumptionBasis.DERIVED_FROM_COP,
                    factor=heating_fuel_eff, source_name=f"Heating:{heating_fuel}",
                    note=f"실기기 미터(Heating:{heating_fuel})가 시뮬레이션 출력에 없어 "
                         f"난방 요구량÷효율 {heating_fuel_eff} 로 추정했습니다 — "
                         f"실소비가 아닌 근사치입니다"))
            cool_fallback_cop = FALLBACK_DX_COOLING_COP

        if ce_col:
            c_con = df[ce_col].values / J_TO_KWH
            steps.append(ConversionStep(EnergyCategory.COOLING, ConsumptionBasis.METERED,
                                        source_name=ce_col))
        else:
            c_con = c_req / cool_fallback_cop
            steps.append(ConversionStep(
                EnergyCategory.COOLING, ConsumptionBasis.DERIVED_FROM_COP,
                factor=cool_fallback_cop, source_name="Cooling:Electricity",
                note=f"실기기 미터(Cooling:Electricity)가 시뮬레이션 출력에 없어 "
                     f"냉방 요구량÷대표COP 로 추정했습니다 — 실소비가 아닌 근사치입니다"))

        if fe_col:
            fan_kwh = df[fe_col].values / J_TO_KWH
    else:
        # 이상부하: 존별 요구량을 COP·효율로 나눈다.
        for z in zones:
            # 열 이름은 "{존ID}_IDEAL:Zone Ideal Loads ..." → **접두 정확 매칭**.
            # 부분문자열 매칭은 'HEATING' 이라는 존이 모든 존의 Heating 열과 매칭돼
            # 난방이 통째로 이중집계되고, '1 TOILET' 이 '1 TOILET / ACCESSIBLE' 에도
            # 매칭돼 중복 합산되는 버그가 있었다.
            z_key = z["id"].replace(" ", "_").upper() + "_IDEAL:"
            zh = [c for c in h_cols if c.upper().startswith(z_key)]
            zc = [c for c in c_cols if c.upper().startswith(z_key)]
            zrh = [c for c in h_rate_cols if c.upper().startswith(z_key)]
            zrc = [c for c in c_rate_cols if c.upper().startswith(z_key)]

            zh_kwh = df[zh].sum(axis=1).values / J_TO_KWH if zh else 0.0
            zc_kwh = df[zc].sum(axis=1).values / J_TO_KWH if zc else 0.0
            zh_rate = df[zrh].sum(axis=1).values if zrh else 0.0
            zc_rate = df[zrc].sum(axis=1).values if zrc else 0.0

            if not z.get("isConditioned", True):
                continue

            hvac_sys = z.get("hvacSystemId", 5)
            # ⚠️ 난방 연료는 **프로젝트 열원**으로 결정한다. 존 heatingFuelId(기본=전기)를
            # 쓰면 지역난방(11)에도 전기 히트펌프 COP(~3.5)가 적용돼 난방이 ~3배 과소산정된다.
            fuel_type = heat_source

            if is_geothermal:
                h_cop, c_cop = GEOTHERMAL_COPS
            else:
                c_cop = COOLING_EFF_DB.get(hvac_sys, DEFAULT_COOLING_COP)
                # 지역난방(11)은 효율 ~1.0(열량 전달 손실 거의 없음). DB 에 없으면 0.95 폴백.
                h_default = 0.95 if fuel_type == 11 else 1.0
                h_cop = HEATING_EFF_DB.get(hvac_sys, {}).get(fuel_type, h_default)

            h_req = h_req + zh_kwh
            c_req = c_req + zc_kwh
            h_con = h_con + zh_kwh / h_cop
            c_con = c_con + zc_kwh / c_cop
            h_rate = h_rate + zh_rate / h_cop
            c_rate = c_rate + zc_rate / c_cop

        steps.append(ConversionStep(EnergyCategory.HEATING, ConsumptionBasis.DERIVED_FROM_COP,
                                    source_name="존별 HEATING_EFF_DB",
                                    note="이상부하 모드: 요구량을 설비 효율로 나눠 소비량을 산출"))
        steps.append(ConversionStep(EnergyCategory.COOLING, ConsumptionBasis.DERIVED_FROM_COP,
                                    source_name="존별 COOLING_EFF_DB"))

    l_kwh = _sum_kwh(df, l_cols, n, np_mod)
    e_kwh = _sum_kwh(df, e_cols, n, np_mod)
    # 급탕은 배관 손실 10% 를 더한다
    dhw_kwh = _sum_kwh(df, dhw_cols, n, np_mod) * 1.1
    v_flow = df[vent_cols].sum(axis=1).values if vent_cols else np_mod.zeros(n)

    context = EnergyConversionContext(
        hvac_mode=hvac_mode,
        heat_source_id=heat_source,
        heating_fuel=heating_fuel,
        heating_efficiency=heating_fuel_eff if hvac_mode == "fuel" else None,
        steps=tuple(steps),
    )

    return EnergyTimeSeries.build(
        resolution, months, hours, context=context,
        heating_requirement_kwh=h_req, cooling_requirement_kwh=c_req,
        heating_consumption_kwh=h_con, cooling_consumption_kwh=c_con,
        heating_rate_w=h_rate, cooling_rate_w=c_rate,
        lighting_kwh=l_kwh, equipment_kwh=e_kwh, dhw_kwh=dhw_kwh,
        fan_kwh=fan_kwh, ventilation_kg_s=v_flow,
    )


def ventilation_energy_kwh(series: EnergyTimeSeries, np_mod):
    """환기 처리 에너지 + 팬 전력.

    ⚠️ 요구량과 소비량이 **반드시 같은 계수를 거쳐야 한다.** 예전에는 요구량 쪽에만
    이 계수가 빠져 체적(m³)이 kWh 합계에 그대로 섞여 들어갔다.
    """
    multiplier = 1.0 if series.resolution is TimeResolution.HOURLY else MONTHLY_HOURS
    flow = np_mod.array(series.ventilation_kg_s)
    volume_m3 = (flow / AIR_DENSITY_KG_M3) * multiplier
    return volume_m3 * VENT_ENERGY_PER_M3 + np_mod.array(series.fan_kwh)
