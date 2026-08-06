# src/cost_analyzer.py
try:
    import pandas as pd
except ImportError:
    pd = None

# 비거주 구역 판별 키워드 — LED 공사 면적 축소·설비(냉방기) 설치 제외 등에 공용.
# (ep_simulator도 import: 계단실 등엔 WindowAC를 설치하지 않아 냉방부하 0 → 사이징 실패 방지)
from src.domain.models import BaselineSource, TariffResult
from src.economics import tariffs as _tariffs
from src.economics.baseline import resolve_baseline, savings_pct
from src.economics.capital_cost import estimate_capital_cost
from src.economics.cashflow import irr, simple_payback_years
from src.economics.cost_db import CostDatabase
from src.economics.recommendations import build_recommendations

NON_HABITABLE_KEYWORDS = [
    'stair', 'chase', 'shaft', 'lift', 'elevator', 'store', 'storage',
    'parking', 'garage', 'vent', 'mechanical', 'duct', 'pipe',
    '계단', '엘리베이터', '창고', '주차', '기계', '덕트'
]


def is_non_habitable(zone: dict) -> bool:
    """존 용도명(파서는 id에 담음)으로 비거주 구역 여부 판별."""
    z_name = (zone.get('name') or zone.get('id') or '').lower()
    return any(kw in z_name for kw in NON_HABITABLE_KEYWORDS)


class LCCAnalyzer:
    """
    Building Energy Modeling (BEM) 경제성 및 요금(LCC) 분석 오픈소스 모듈
    EnergyPlus 결과와 독립적으로 계산을 수행합니다.
    """
    # ── 요율은 economics/tariffs.py 가 **단일 소스**다 ──
    # ⚠️ 예전엔 여기에도 같은 값이 있었고 실제 계산은 이쪽을 썼다.
    # 두 곳에 두면 한쪽만 갱신했을 때 결과가 조용히 갈라진다.
    # 하위 호환을 위해 이름만 남기고 값은 tariffs 에서 가져온다.
    ELEC_RATE_SUMMER = _tariffs.ELEC_RATE_SUMMER
    ELEC_RATE_WINTER = _tariffs.ELEC_RATE_WINTER
    ELEC_RATE_SPRING = _tariffs.ELEC_RATE_SPRING
    ELEC_BASE_CHARGE = _tariffs.ELEC_BASE_CHARGE
    TOU_RATES = _tariffs.TOU_RATES
    HEAT_RATE_KWH = _tariffs.HEAT_RATE_KWH
    HEAT_SOURCE_DB = _tariffs.HEAT_SOURCE_DB
    DEFAULT_HEAT_SOURCE = _tariffs.DEFAULT_HEAT_SOURCE

    # 기준선 가정은 economics/baseline.py 가 소유한다.

    # ⚠️ 1차에너지·CO2 계수는 domain/energy_metrics.py 가, 환기 변환 계수는
    # energyplus/outputs.py 가 소유한다. 여기 별칭을 두면 두 번째 접근 경로가
    # 영구화되므로 두지 않는다.

    # LED 조명: 단가는 '개당(EA)' 기준이므로 면적은 등기구 개수로 환산해 적용한다.
    LED_FIXTURE_AREA_M2 = 10.0   # 등기구 1개가 담당하는 바닥면적 (㎡/개)


    def __init__(self, db_dir: str):
        # 단가 DB 는 economics/cost_db.py 가 소유한다. 여기서는 조회만 위임한다.
        self.db_dir = db_dir
        self._cost_db_source = CostDatabase(db_dir)

    # ── 단가 DB 위임 ──
    # 기존 호출부·시험이 analyzer 를 통해 접근하므로 이름을 유지한다.
    @property
    def cost_db(self):
        return self._cost_db_source.cost_db

    @property
    def load_warnings(self):
        return self._cost_db_source.load_warnings

    def match_window_price(self, target_u, target_shgc):
        return self._cost_db_source.match_window_price(target_u, target_shgc)

    def match_insulation_price(self, conductivity, explicit_tier=None):
        return self._cost_db_source.match_insulation_price(conductivity, explicit_tier)

    def calculate(self, eplus_csv_path: str, zones: list, total_area: float,
                  total_window_area: float, total_wall_area: float,
                  target_u: float, target_shgc: float, pv_capacity_kw: float,
                  is_geothermal: bool, act_main: int, surfaces: list,
                  materials: dict, target_budget: float, led_fixture_count: int,
                  led_reduction_active: bool, **kwargs) -> dict:
        
        construction_overrides = kwargs.get("construction_overrides", {})
        
        if pd is None:
            raise RuntimeError("pandas가 설치되지 않아 비용 분석을 수행할 수 없습니다. (pip install pandas)")

        try:
            df = pd.read_csv(eplus_csv_path).fillna(0)
            df.columns = [c.strip() for c in df.columns]
            
            import numpy as np
            from src.energyplus.outputs import parse_outputs, ventilation_energy_kwh
            from src.domain.energy_aggregation import annual_summary, monthly_breakdown
            from src.domain.energy_metrics import build_metrics
            from src.economics.tariffs import (apply_pv_self_consumption, electricity_rates,
                                                annual_bills, heat_source_entry,
                                                split_by_carrier)
            from src.energyplus.surfaces import extract_surface_outputs

            total_rows = len(df)

            # ── EnergyPlus 출력 파싱 ──
            # 열 탐색·단위 환산·HVAC 모드별 요구량/소비량 산출은 energyplus/outputs.py 로
            # 옮겼다. 여기서는 계약(EnergyTimeSeries)을 받아 기존 지역변수에 풀어놓는다.
            # (아래 요금·PV·월별 집계가 아직 이 변수들과 원본 df 를 쓰고 있어 과도기적이다)
            series = parse_outputs(
                df, zones, np_mod=np,
                hvac_mode=kwargs.get("hvac_mode") or ("pthp" if kwargs.get("use_pthp") else "ideal"),
                heating_fuel=kwargs.get("heating_fuel"),
                heating_fuel_eff=kwargs.get("heating_fuel_eff") or 0.9,
                heat_source=kwargs.get("heat_source", self.DEFAULT_HEAT_SOURCE),
                is_geothermal=is_geothermal,
            )

            use_pthp = kwargs.get("use_pthp", False)
            monthly_data = []
            is_hourly = series.resolution.value == "hourly"

            total_h_req_kwh = np.array(series.heating_requirement_kwh)
            total_c_req_kwh = np.array(series.cooling_requirement_kwh)
            total_h_con_kwh = np.array(series.heating_consumption_kwh)
            total_c_con_kwh = np.array(series.cooling_consumption_kwh)
            total_h_rate_w = np.array(series.heating_rate_w)
            total_c_rate_w = np.array(series.cooling_rate_w)
            l_kwh = np.array(series.lighting_kwh)
            e_kwh = np.array(series.equipment_kwh)
            dhw_kwh = np.array(series.dhw_kwh)
            fan_kwh = np.array(series.fan_kwh)
            vent_kwh = ventilation_energy_kwh(series, np)
            v_flow = np.array(series.ventilation_kg_s)
            annual = annual_summary(series, vent_kwh)

            # 미터가 없어 추정으로 대체한 항목 — 조용한 추정을 막기 위해 사용자에게 노출
            _meter_fallback_notes = [s.note for s in series.context.fallback_steps if s.note]

            # ── 요금 (economics/tariffs.py) ──
            # ⚠️ DataFrame 에 파생 열을 붙이지 않는다. 예전엔 total_elec_kwh/elec_rate/
            # elec_cost/heat_cost 를 df 에 실어 계산했는데, 그러면 요금 로직이 엔진 출력
            # 자료구조에 묶여 계층 분리가 되지 않는다.
            split = split_by_carrier(series, vent_kwh, use_pthp=use_pthp)
            elec_rates = electricity_rates(series)
            elec_kwh = apply_pv_self_consumption(
                split.electricity_kwh, series.hours, pv_capacity_kw)
            heat_kwh_series = split.heat_kwh
            # 난방 열원 결정: 지열/히트펌프면 전기(2), 아니면 프로젝트 선택값(기본 지역난방)
            heat_source_id = 2 if is_geothermal else kwargs.get("heat_source", self.DEFAULT_HEAT_SOURCE)
            heat_src = heat_source_entry(heat_source_id, is_geothermal=is_geothermal)

            annual_elec_bill, annual_heat_bill = annual_bills(
                elec_kwh, heat_kwh_series, elec_rates, heat_src["rate"])

            # 연간 집계는 domain/energy_aggregation.py 의 계약에서 받는다.
            # (환기 요구량 = 소비 − 팬, 급탕 요구량 = 소비 ÷ 배관손실 — 그쪽에 명시돼 있다)
            a_h_req = annual.heating_requirement_kwh
            a_c_req = annual.cooling_requirement_kwh
            a_dhw_req = annual.dhw_requirement_kwh
            a_vent_req = annual.ventilation_requirement_kwh

            a_h_con = annual.heating_consumption_kwh
            a_c_con = annual.cooling_consumption_kwh
            a_l_con = annual.lighting_kwh
            a_e_con = annual.equipment_kwh
            a_dhw_con = annual.dhw_consumption_kwh
            a_vent_con = annual.ventilation_consumption_kwh

            demand_col = next((c for c in df.columns
                               if 'Facility Total Electric Demand Rate' in c), None)
            base_demand = df[demand_col].values if demand_col else np.zeros(total_rows)
            peak_kw_series = (base_demand + total_c_rate_w + total_h_rate_w + (v_flow / 1.2 * 0.8 * 1000.0)) / 1000.0
            
            # 동시사용률(Diversity Factor) 0.8 적용하여 피크 과대평가 방지
            peak_elec_kw = peak_kw_series.max() * 0.8 if len(peak_kw_series) > 0 else 0
            peak_kw_estimate = peak_elec_kw if peak_elec_kw > 0 else total_area * 0.05
            annual_elec_bill += peak_kw_estimate * self.ELEC_BASE_CHARGE * 12

            # 냉난방 설비 용량(kW) — 설비비 산정용.
            # 시간당 현열부하(kWh/h ≈ kW)의 99퍼센타일로 산정한다. 이상부하의 순간 .max()는
            # 셋백 복귀 시 용량제한 없이 치솟아(예: 228 W/㎡) 설비비를 과대평가하므로 백분위로 완화하고,
            # PTHP·이상부하 양 경로가 같은 현열부하 시계열을 써 시스템 선택과 무관하게 일관되게 한다.
            if len(total_h_req_kwh) > 0:
                heat_peak_kw = float(np.percentile(total_h_req_kwh, 99))
                cool_peak_kw = float(np.percentile(total_c_req_kwh, 99))
            else:
                heat_peak_kw = cool_peak_kw = 0.0
            hvac_capacity_kw = max(heat_peak_kw, cool_peak_kw)
            # 현실 설계부하 범위로 클램프: 40~100 W/㎡.
            # 일부 gbXML 모델(폐합 갭·과대 침기 등)은 현열부하가 200 W/㎡까지 치솟지만 실제 설비는
            # 그렇게 사이징하지 않는다. 단열 좋은 건물은 하한 미만이라 설비비가 싸진다(정상).
            hvac_capacity_kw = min(max(hvac_capacity_kw, total_area * 0.04), total_area * 0.10)
            
            # 월별 집계는 domain/energy_aggregation.py 로 옮겼다 (순수 합산).
            monthly_data = monthly_breakdown(series, total_area)

            pv_gen = ((pv_capacity_kw * 1300) / total_area) if pv_capacity_kw and total_area > 0 else 0.0
            
            # 공사비 산정은 economics/capital_cost.py 로 옮겼다.
            _cap = estimate_capital_cost(
                cost_db=self._cost_db_source, surfaces=surfaces, zones=zones,
                materials=materials, total_area=total_area,
                total_window_area=total_window_area, total_wall_area=total_wall_area,
                target_u=target_u, target_shgc=target_shgc,
                led_fixture_count=led_fixture_count,
                led_reduction_active=led_reduction_active,
                is_geothermal=is_geothermal, hvac_capacity_kw=hvac_capacity_kw,
                hvac_exclude_non_habitable=kwargs.get("hvac_exclude_non_habitable", False),
                hvac_upgrade_active=kwargs.get("hvac_upgrade_active", False),
                construction_overrides=construction_overrides,
                meter_fallback_notes=_meter_fallback_notes,
                target_budget=target_budget,
            )
            window_cost = _cap.result.by_item["window"]
            insulation_cost = _cap.result.by_item["insulation"]
            led_cost = _cap.result.by_item["led"]
            hvac_cost = _cap.result.by_item["hvac"]
            total_capital_cost = _cap.result.total_won
            mapped_window_name = _cap.mapped_window_name
            target_window_price = _cap.window_unit_price
            detailed_insulation_costs = _cap.insulation_details
            cost_warnings = _cap.warnings
            hvac_unit_cost = _cap.hvac_unit_cost
            non_hab_share = _cap.non_habitable_share
            led_saving = _cap.led_saving
            hvac_exclude_non_habitable = kwargs.get("hvac_exclude_non_habitable", False)

            # 생애주기비용(LCC) 현금흐름 계산 (할인 현금흐름 방식)
            discount_rate = kwargs.get("discount_rate", 0.05)
            inflation_rate = kwargs.get("inflation_rate", 0.03)
            utility_inflation = kwargs.get("utility_inflation", 0.04)
            years = kwargs.get("lifecycle_years", 20)

            # 창호·단열재·PV의 통상 내구연한(20~30년)보다 짧은 분석 기간은
            # 투자 회수 전에 분석이 끝나 NPV·IRR이 구조적으로 불리하게 나온다.
            if years < 15:
                cost_warnings.append(
                    f"LCC 분석 기간 {years}년은 창호·단열재·태양광의 통상 내구연한(20~30년)보다 짧습니다 — "
                    "투자 회수 전에 분석이 끝나 NPV·IRR이 불리하게 산출될 수 있으니 20년 이상 설정을 권장합니다"
                )

            # 누적 생애주기비용(LCC) 곡선: 초기투자비 + 연차별 할인 운영/유지/교체비
            # (순절감액이 아닌 '총 소유비용'의 현재가치 누적 → 손익분기 차트용)
            cumulative_lcc_30y = []
            lcc_pv = total_capital_cost

            for y in range(1, years + 1):
                yearly_op_cost = (annual_elec_bill + annual_heat_bill) * ((1 + utility_inflation) ** y)
                maint_cost = ((hvac_cost * 0.02) + (led_cost * 0.01)) * ((1 + inflation_rate) ** y)

                replacement_cost = 0
                if y % 15 == 0:
                    # 15년차 설비 전면 교체가 아닌 핵심기기(50%) 부분 교체 반영
                    replacement_cost += (hvac_cost * 0.5) * ((1 + inflation_rate) ** y)
                if y % 10 == 0:
                    replacement_cost += (led_cost * 0.4) * ((1 + inflation_rate) ** y)

                total_year_cost = yearly_op_cost + maint_cost + replacement_cost

                # 해당 연도 비용을 현재가치로 할인하여 누적
                discounted_cost = total_year_cost / ((1 + discount_rate) ** y)
                lcc_pv += discounted_cost
                cumulative_lcc_30y.append(int(lcc_pv))

            # 매트릭스·1차에너지·CO2·자립률은 domain/energy_metrics.py 로 옮겼다.
            metrics = build_metrics(
                annual, floor_area_m2=total_area, pv_generation_kwh_m2=pv_gen,
                heat_primary_factor=heat_src["primary"], heat_co2_factor=heat_src["co2"])
            matrix = metrics.as_response_dict()
            independence_val = metrics.renewable_independence_pct
            total_con_actual = metrics.consumption_kwh_m2
            primary_per_m2 = metrics.primary_energy_kwh_m2
            co2_per_m2 = metrics.co2_kg_m2

            summary = {
                "demand_per_m2": sum(v["req"] for k,v in matrix.items() if k != "renewable"),
                "consume_per_m2": total_con_actual,
                "primary_per_m2": round(primary_per_m2, 1),
                "co2_per_m2": round(co2_per_m2, 2),
                "independence": independence_val
            }
            
            recommendations = build_recommendations(
                cost_db=self.cost_db,
                mapped_window_name=mapped_window_name,
                window_cost=window_cost,
                total_window_area=total_window_area,
                detailed_insulation_costs=detailed_insulation_costs,
                is_geothermal=is_geothermal,
                hvac_cost=hvac_cost,
                hvac_capacity_kw=hvac_capacity_kw,
                hvac_unit_cost=hvac_unit_cost,
                hvac_exclude_non_habitable=hvac_exclude_non_habitable,
                non_hab_share=non_hab_share,
                led_cost=led_cost,
                led_saving=led_saving,
                led_fixture_count=led_fixture_count,
                led_reduction_active=led_reduction_active,
                cooling_grade=kwargs.get("cooling_grade", "grade3"),
                heating_age=kwargs.get("heating_age", "new"),
                hvac_upgraded=kwargs.get("hvac_upgraded", False),
            )

            # 단순 IRR (내부수익률) 계산기 (Bisection method)
            # 상한을 5.0(500%)까지 넓혀 인위적으로 100%에 고정되지 않게 한다.
            # 현금흐름 배열 (Year 0 = -초기투자비, Year 1~N = 기존 노후 건물 대비 절감액)
            # ⚠️ 기준 건물 운영비 = 리모델링 후 운영비 × 배수 (단일·투명 가정).
            #    프론트 LCC 차트와 동일한 모델을 사용해 NPV/IRR과 차트가 일관되게 한다.
            retrofit_running_cost = annual_elec_bill + annual_heat_bill

            # 기준선 산정은 economics/baseline.py 로 옮겼다.
            _baseline = resolve_baseline(
                retrofit_running_cost=retrofit_running_cost,
                actual_elec_bill=kwargs.get("actual_elec_bill"),
                actual_heat_bill=kwargs.get("actual_heat_bill"),
                actual_elec_kwh=kwargs.get("actual_elec_kwh"),
                actual_heat_kwh=kwargs.get("actual_heat_kwh"),
                sim_base_elec_bill=kwargs.get("sim_base_elec_bill"),
                sim_base_heat_bill=kwargs.get("sim_base_heat_bill"),
                sim_base_same=bool(kwargs.get("sim_base_same")),
                avg_elec_rate=(self.ELEC_RATE_SUMMER + self.ELEC_RATE_WINTER
                               + self.ELEC_RATE_SPRING) / 3.0,
                heat_rate=heat_src["rate"],
            )
            base_running_cost = _baseline.running_cost_won
            baseline_source = _baseline.source.value
            cost_warnings.extend(_baseline.warnings)

            # ── 요금 계약 생성 ──
            # 정의만 해두고 안 쓰면 계약이 아니다. 실제 경로에서 만들어
            # 이후 계층(현금흐름·응답 조립)이 dict 대신 이것을 받게 한다.
            tariff = TariffResult(
                electricity_won=float(annual_elec_bill),
                heating_won=float(annual_heat_bill),
                heating_fuel=str(heat_src.get("label", "")),
                baseline_total_won=float(base_running_cost),
                baseline_source=BaselineSource(baseline_source),
            )


            def _build_cash_flows(ui):
                """요금상승률 ui 가정의 연차별 순절감액 현금흐름 (민감도 재계산에도 사용)."""
                flows = [-total_capital_cost]
                for y in range(1, years + 1):
                    base_cost_y = base_running_cost * ((1 + ui) ** y)
                    yearly_op_cost_y = (annual_elec_bill + annual_heat_bill) * ((1 + ui) ** y)
                    maint_cost_y = ((hvac_cost * 0.02) + (led_cost * 0.01)) * ((1 + inflation_rate) ** y)

                    rep_cost_y = 0
                    # NPV 누적 계산(cumulative_lcc_30y)과 동일한 교체 가정 사용:
                    #   15년차 핵심기기 50% 부분 교체, 10년차 LED 40% 교체
                    if y % 15 == 0: rep_cost_y += (hvac_cost * 0.5) * ((1 + inflation_rate) ** y)
                    if y % 10 == 0: rep_cost_y += (led_cost * 0.4) * ((1 + inflation_rate) ** y)

                    # 절감액 = (기존 건물 운영비) - (리모델링 후 운영비 + 유지보수 + 교체비)
                    flows.append(base_cost_y - (yearly_op_cost_y + maint_cost_y + rep_cost_y))
                return flows

            def _npv_of(flows, dr):
                return sum(cf / ((1 + dr) ** t) for t, cf in enumerate(flows))

            cash_flows = _build_cash_flows(utility_inflation)
            _irr_rate = irr(cash_flows)
            # ⚠️ 회수기간은 **백엔드가 산출한다.** 프런트가 자체 계산하면 할인율·
            # 요금상승·유지비·10년 LED/15년 HVAC 교체가 빠져 다른 답이 나온다.
            payback_years = simple_payback_years(cash_flows)
            irr_val = None if _irr_rate is None else _irr_rate * 100

            # 비현실적으로 높은 IRR은 (초기투자비 대비 절감액 과다) 가정 민감도 경고
            if irr_val is not None and irr_val > 100:
                cost_warnings.append(
                    f"IRR이 {irr_val:.0f}%로 비정상적으로 높습니다 — 초기투자비가 작거나 기준 건물 가정이 절감액을 과대평가했을 수 있어 참고용으로만 보세요"
                )
                print(f"  ⚠️ IRR 점검: {irr_val:.0f}% (가정 민감도 높음)")

            # 순현재가치(NPV) = 순절감액 현금흐름을 할인율로 할인한 현재가치의 합
            #   (cash_flows[0] = -초기투자비 이므로 자본비가 이미 반영됨)
            #   IRR과 동일한 현금흐름을 사용 → 두 지표가 일관됨. 0 이상이면 투자 타당.
            npv_real = _npv_of(cash_flows, discount_rate)

            # NPV 민감도 — 재시뮬레이션 없이 동일 현금흐름 로직으로
            # 할인율 ±2%p, 요금상승률 ±1%p 가정만 바꿔 재할인 (결과 견고성 판단용)
            dr_lo, dr_hi = max(discount_rate - 0.02, 0.0), discount_rate + 0.02
            ui_lo, ui_hi = max(utility_inflation - 0.01, 0.0), utility_inflation + 0.01
            npv_sensitivity = [
                {
                    "param": "할인율",
                    "low_label": f"{dr_lo*100:.1f}%", "low": int(_npv_of(cash_flows, dr_lo)),
                    "base_label": f"{discount_rate*100:.1f}%", "base": int(npv_real),
                    "high_label": f"{dr_hi*100:.1f}%", "high": int(_npv_of(cash_flows, dr_hi)),
                },
                {
                    "param": "요금상승률",
                    "low_label": f"{ui_lo*100:.1f}%", "low": int(_npv_of(_build_cash_flows(ui_lo), discount_rate)),
                    "base_label": f"{utility_inflation*100:.1f}%", "base": int(npv_real),
                    "high_label": f"{ui_hi*100:.1f}%", "high": int(_npv_of(_build_cash_flows(ui_hi), discount_rate)),
                },
            ]

            financial = {
                "annual_elec_bill": int(annual_elec_bill),
                "annual_heat_bill": int(annual_heat_bill),
                "total_energy_bill": int(annual_elec_bill + annual_heat_bill),
                "capital_cost": int(total_capital_cost),
                "target_budget": int(target_budget),
                "cost_details": {
                    "window": int(window_cost), 
                    "insulation": int(insulation_cost), 
                    "led": int(led_cost), 
                    "hvac": int(hvac_cost)
                },
                "mapped_window_name": mapped_window_name,
                # 창호 산정 근거 상세 — UI에 '어떤 유리를 얼마에 계상했는지' 명시용
                "window_details": {
                    "u_value": round(target_u, 2),          # 창 면적가중 대표 U (W/㎡K)
                    "shgc": round(target_shgc, 2),
                    "unit_price": int(target_window_price),  # 등급 중앙값 단가 (원/㎡)
                    "area_m2": round(total_window_area, 1),
                },
                "insulation_details": detailed_insulation_costs if 'detailed_insulation_costs' in locals() else [],
                "recommendations": recommendations,
                "csv_db_loaded": self.cost_db["status"],
                "cumulative_lcc_30y": cumulative_lcc_30y,
                "lcc_parameters": {
                    "discount_rate": discount_rate * 100,
                    "inflation_rate": inflation_rate * 100,
                    "utility_inflation": utility_inflation * 100,
                    "lifecycle_years": years
                },
                "npv": int(npv_real),
                # None = 분석기간 내 미회수. **0 으로 바꾸면 '즉시 회수'가 된다.**
                "simple_payback_years": (None if payback_years is None
                                         else round(payback_years, 1)),
                "npv_sensitivity": npv_sensitivity,
                "hvac_capacity_kw": round(hvac_capacity_kw, 1),  # 공사비 산정 기준 용량 (UI 각주용)
                "total_lcc": int(lcc_pv),
                "irr": None if irr_val is None else round(irr_val, 2),
                "cost_warnings": cost_warnings,
                "heat_source": heat_src["label"],   # 적용된 난방 열원 (UI 표기용)
                # NPV/IRR/절감액이 비교한 '기존 건물' 기준 (UI 명시 고지용)
                "baseline_assumptions": {
                    "source": baseline_source,                       # actual_bill | actual_usage | estimate
                    "base_running_cost": int(base_running_cost),      # 적용된 기존 건물 연간 운영비
                    "running_cost_multiplier": _baseline.multiplier,
                    "savings_pct": savings_pct(base_running_cost, retrofit_running_cost)
                },
                # 수치가 전제하는 추정 가정 — UI 고지용. 정밀해 보이는 숫자에 대한 과신 방지.
                "estimate_notes": [
                    {
                        "label": "공사비 단가",
                        "note": "친환경건설자재 DB의 등급별 중앙값 단가입니다. 브랜드·시공 조건에 따라 실제 견적과 차이가 날 수 있습니다."
                    },
                    {
                        "label": "설비(HVAC) 비용",
                        "note": f"시뮬레이션 피크부하로 추정한 용량 {hvac_capacity_kw:.0f}kW × 시스템 단가(kW당 {int(hvac_unit_cost):,}원)입니다. 실측 견적이 아닌 추정치입니다."
                    },
                    {
                        "label": "LED 공사비",
                        "note": ("직접 입력한 등기구 수량 × 개당 중앙값 단가로 계산했습니다."
                                 if led_fixture_count > 0 else
                                 f"바닥면적 약 {self.LED_FIXTURE_AREA_M2:.0f}㎡당 등기구 1개로 환산한 추정 수량 기준입니다.")
                    },
                    {
                        "label": "에너지 요금",
                        "note": "2026년 KEPCO 일반용·지역난방 요금표 기준이며, 실제 계약 종별에 따라 달라질 수 있습니다. "
                                "주거 건물의 세대별 주택용 누진제는 반영되지 않습니다."
                    },
                    {
                        "label": "냉방기간",
                        "note": "냉방은 5월 1일~10월 31일에만 가동하는 것으로 가정합니다. 동절기에는 일사·내부발열로 "
                                "실내온도가 올라도 냉방을 돌리지 않습니다(실제 운영 관행 반영)."
                    },
                    {
                        "label": "기존 건물 기준선",
                        "note": ("입력하신 실측 요금/사용량을 기준으로 절감액을 계산했습니다."
                                 if baseline_source in ("actual_bill", "actual_usage") else
                                 "업로드하신 원본 건물(개선 전)을 별도 시뮬레이션한 운영비를 기준으로 절감액을 계산했습니다."
                                 if baseline_source == "simulated" else
                                 f"실측 요금 미입력 시 개선 후 운영비의 {_baseline.multiplier}배를 기존 건물로 가정합니다. 실측 요금을 입력하면 정확도가 올라갑니다.")
                    },
                    {
                        "label": "NPV·IRR",
                        "note": f"할인율 {discount_rate*100:.1f}%, 물가상승 {inflation_rate*100:.1f}%, 요금상승 {utility_inflation*100:.1f}%, 분석기간 {years}년 가정의 결과입니다."
                    },
                ]
            }
            
            surface_thermal, surface_airflow = extract_surface_outputs(df, surfaces)

            final_data = {
                "summary": summary, 
                "monthly": monthly_data, 
                "matrix": matrix, 
                "financial": financial,
                "surfaceThermal": surface_thermal,
                "surfaceAirflow": surface_airflow
            }
            
            return { **final_data, "result": final_data }
            
        except Exception as e:
            # 실패 시 가짜(fallback) 수치를 내보내지 않고 명시적으로 실패시킨다.
            # 가짜 데이터가 정상 결과처럼 화면에 그려지는 것을 막기 위함.
            print(f"❌ LCC Analyzer 계산 실패: {e}")
            raise RuntimeError(f"비용 분석 실패: {e}") from e

