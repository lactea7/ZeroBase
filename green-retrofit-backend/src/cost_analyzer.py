# src/cost_analyzer.py
import os
import re

try:
    import pandas as pd
except ImportError:
    pd = None

class LCCAnalyzer:
    """
    Building Energy Modeling (BEM) 경제성 및 요금(LCC) 분석 오픈소스 모듈
    EnergyPlus 결과와 독립적으로 계산을 수행합니다.
    """
    ELEC_RATE_SUMMER = (183.6 + 128.9 + 98.1) / 3   # 6~8월 가중평균
    ELEC_RATE_WINTER = (138.5 + 112.2 + 98.1) / 3   # 11~2월 가중평균
    ELEC_RATE_SPRING = (121.7 + 103.9 + 98.1) / 3   # 3~5, 9~10월 가중평균
    ELEC_BASE_CHARGE = 4910    # 기본요금 (원/kW)
    HEAT_RATE_MCAL = 145.82    
    HEAT_RATE_KWH = HEAT_RATE_MCAL * 0.8604

    HEATING_EFF_DB = { 
        1: {1: 0.85, 2: 2.50, 4: 0.80, 11: 0.95}, 
        2: {2: 3.50, 11: 1.00}, 
        3: {1: 0.82, 2: 3.00, 11: 0.95}, 
        5: {1: 0.80, 2: 2.80, 4: 0.75} 
    }

    COOLING_EFF_DB = { 
        1: 3.50, 
        2: 4.20, 
        3: 3.20, 
        5: 2.80 
    }

    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        self.cost_db = self._load_cost_db()

    @staticmethod
    def _clean_price(price_str):
        if pd.isna(price_str): 
            return 0.0
        cleaned = re.sub(r'[^\d.]', '', str(price_str))
        if cleaned:
            return float(cleaned)
        else:
            return 0.0

    @staticmethod
    def _safe_read_csv(filepath):
        encodings_to_try = ['utf-8', 'cp949', 'euc-kr', 'utf-8-sig']
        skips_to_try = [0, 1, 2]
        
        for enc in encodings_to_try:
            for skip in skips_to_try:
                try:
                    df = pd.read_csv(filepath, skiprows=skip, encoding=enc)
                    df.columns = [re.sub(r'\s+', '', str(c)) for c in df.columns]
                    if '공급가격' in df.columns or '적용단가' in df.columns or '재료비' in df.columns or '거래가격' in df.columns or '품명' in df.columns:
                        return df
                except Exception:
                    continue
        return None

    def _load_cost_db(self):
        cost_db_dict = {
            "status": {"eco_loaded": False, "nara_loaded": False, "items": 0},
            "avg_prices": {
                "window": 250000,
                "insulation": 45000,
                "led": 120000,
                "hvac_kw": 200000
            },
            "window_db": []
        }
        
        if os.path.exists(self.db_dir) and pd is not None:
            for f_name in os.listdir(self.db_dir):
                f_path = os.path.join(self.db_dir, f_name)
                if not os.path.isfile(f_path): 
                    continue
                f_lower = f_name.lower()
                
                if f_lower.endswith('.csv'):
                    try:
                        df = self._safe_read_csv(f_path)
                        if df is None or df.empty:
                            continue
                        
                        if '공급가격' in df.columns:
                            df['price_num'] = df['공급가격'].apply(self._clean_price)
                            row_texts = df.fillna('').astype(str).apply(lambda x: ' '.join(x), axis=1)
                            
                            window_items = df[row_texts.str.contains('창호|유리|복층|로이', na=False, case=False)]
                            for idx, row in window_items.iterrows():
                                price = row.get('price_num', 0)
                                if price > 0:
                                    text_chunk = row_texts[idx]
                                    u_match = re.search(r'U[-]?value.*?([\d.]+)', text_chunk, re.IGNORECASE)
                                    shgc_match = re.search(r'SHGC.*?([\d.]+)', text_chunk, re.IGNORECASE)
                                    
                                    u_val = float(u_match.group(1)) if u_match else None
                                    shgc_val = float(shgc_match.group(1)) if shgc_match else None
                                    
                                    if len(row) > 10:
                                        name_val = str(row.iloc[10])
                                    else:
                                        name_val = "친환경 창호"
                                    
                                    cost_db_dict["window_db"].append({
                                        "name": name_val, "u": u_val, "shgc": shgc_val, "price": price
                                    })
                            
                            led_items = df[row_texts.str.contains('LED', na=False, case=False)]
                            if not led_items.empty: 
                                cost_db_dict["avg_prices"]["led"] = led_items['price_num'].mean()
                                
                            cost_db_dict["status"]["eco_loaded"] = True
                            cost_db_dict["status"]["items"] += len(df)
                        
                        elif any(col in df.columns for col in ['적용단가', '단위', '재료비', '거래가격']):
                            cost_db_dict["status"]["nara_loaded"] = True
                            cost_db_dict["status"]["items"] += len(df)
                            
                    except Exception as e:
                        print(f"Cost DB Error ({f_name}): {e}")
        return cost_db_dict

    def match_window_price(self, target_u: float, target_shgc: float) -> tuple:
        target_window_price = self.cost_db["avg_prices"]["window"]
        mapped_window_name = "기본 단가 반영 (DB 미매칭)"
        
        if self.cost_db["window_db"] and target_u is not None:
            best_match = None
            min_diff = float('inf')
            
            for w_item in self.cost_db["window_db"]:
                if w_item["u"] is not None:
                    diff = abs(w_item["u"] - target_u)
                    if w_item["shgc"] is not None and target_shgc is not None:
                        diff += abs(w_item["shgc"] - target_shgc)
                        
                    if diff < min_diff:
                        min_diff = diff
                        best_match = w_item
                        
            if best_match and min_diff < 1.5:
                target_window_price = best_match["price"]
                mapped_window_name = best_match["name"]
                
        return target_window_price, mapped_window_name

    def calculate(self, eplus_csv_path: str, zones: list, total_area: float, 
                  total_window_area: float, total_wall_area: float, 
                  target_u: float, target_shgc: float, pv_capacity_kw: float, 
                  is_geothermal: bool, act_main: int):
        
        if pd is None:
            return self._fallback_data()

        try:
            df = pd.read_csv(eplus_csv_path).fillna(0)
            df.columns = [c.strip() for c in df.columns]
            
            h_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Heating' in c and '[J]' in c]
            c_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Cooling' in c and '[J]' in c]
            l_cols = [c for c in df.columns if 'Lights' in c and 'Electricity' in c and '[J]' in c]
            e_cols = [c for c in df.columns if 'Electric Equipment' in c and 'Electricity' in c and '[J]' in c]

            monthly_data = []
            a_h_req = a_c_req = a_h_con = a_c_con = a_l_con = a_e_con = 0.0
            annual_elec_bill = annual_heat_bill = peak_elec_kwh = 0
            
            for m in range(min(12, len(df))):
                m_h_req = m_c_req = m_h_con = m_c_con = m_l_con = m_e_con = 0.0
                
                for z in zones:
                    z_id = z['id'].replace(" ", "_").upper()
                    
                    zh_kwh = sum(float(df.iloc[m][c]) for c in h_cols if z_id in c.upper()) / 3600000.0
                    zc_kwh = sum(float(df.iloc[m][c]) for c in c_cols if z_id in c.upper()) / 3600000.0
                    zl_kwh = sum(float(df.iloc[m][c]) for c in l_cols if z_id in c.upper()) / 3600000.0
                    ze_kwh = sum(float(df.iloc[m][c]) for c in e_cols if z_id in c.upper()) / 3600000.0
                    
                    m_h_req += zh_kwh
                    m_c_req += zc_kwh
                    m_l_con += zl_kwh
                    m_e_con += ze_kwh
                    
                    if not z.get("isConditioned", True): 
                        continue
                        
                    hvac_sys = z.get('hvacSystemId', 5)
                    fuel_type = z.get('heatingFuelId', 2)
                    
                    if is_geothermal: 
                        h_cop = 4.5
                        c_cop = 5.0
                    else:
                        c_cop = self.COOLING_EFF_DB.get(hvac_sys, 2.8)
                        h_cop = self.HEATING_EFF_DB.get(hvac_sys, {}).get(fuel_type, 1.0)
                        
                    m_h_con += zh_kwh / h_cop
                    m_c_con += zc_kwh / c_cop
                
                a_h_req += m_h_req
                a_c_req += m_c_req
                a_h_con += m_h_con
                a_c_con += m_c_con
                a_l_con += m_l_con
                a_e_con += m_e_con
                
                month_num = m + 1
                month_elec_kwh = m_c_con + m_l_con + m_e_con
                month_heat_kwh = m_h_con
                
                if month_elec_kwh > peak_elec_kwh: 
                    peak_elec_kwh = month_elec_kwh
                
                if month_num in [6, 7, 8]: 
                    elec_rate = self.ELEC_RATE_SUMMER
                elif month_num in [11, 12, 1, 2]: 
                    elec_rate = self.ELEC_RATE_WINTER
                else: 
                    elec_rate = self.ELEC_RATE_SPRING
                
                annual_elec_bill += month_elec_kwh * elec_rate
                annual_heat_bill += month_heat_kwh * self.HEAT_RATE_KWH
                
                monthly_data.append({
                    "name": f"{month_num}월", 
                    "heating": round(m_h_con / total_area, 1) if total_area > 0 else 0, 
                    "cooling": round(m_c_con / total_area, 1) if total_area > 0 else 0
                })

            pv_gen = ((pv_capacity_kw * 1300) / total_area) if pv_capacity_kw and total_area > 0 else 0.0
                
            if act_main in [1440, 1114]: hw_base = 25.0
            elif act_main in [1108, 1109]: hw_base = 15.0
            else: hw_base = 5.0
                
            if act_main in [1447, 1448]: vent_base = 12.0
            else: vent_base = 8.0
                
            annual_elec_bill += (vent_base * total_area) * self.ELEC_RATE_SPRING
            annual_heat_bill += ((hw_base * 1.1) * total_area) * self.HEAT_RATE_KWH
            
            peak_kw_estimate = peak_elec_kwh / 200 if peak_elec_kwh else total_area * 0.1
            annual_elec_bill += peak_kw_estimate * self.ELEC_BASE_CHARGE * 12
            
            target_window_price, mapped_window_name = self.match_window_price(target_u, target_shgc)
            
            window_cost = total_window_area * target_window_price
            insulation_cost = total_wall_area * self.cost_db["avg_prices"]["insulation"]
            led_cost = total_area * self.cost_db["avg_prices"]["led"]
            hvac_cost = peak_kw_estimate * self.cost_db["avg_prices"]["hvac_kw"]
            
            total_capital_cost = window_cost + insulation_cost + led_cost + hvac_cost

            matrix = {
                "heating": {"req": round(a_h_req/total_area, 1), "con": round(a_h_con/total_area, 1)},
                "cooling": {"req": round(a_c_req/total_area, 1), "con": round(a_c_con/total_area, 1)},
                "hotwater": {"req": hw_base, "con": hw_base * 1.1},
                "lighting": {"req": round(a_l_con/total_area, 1), "con": round(a_l_con/total_area, 1)},
                "ventilation": {"req": vent_base, "con": vent_base},
                "renewable": {"req": -round(pv_gen, 1), "con": -round(pv_gen, 1)}
            }
            
            total_con = sum(v["con"] for k,v in matrix.items() if k != "renewable")
            independence_val = min(100, (abs(matrix["renewable"]["con"]) / total_con * 100)) if total_con > 0 else 0
            
            summary = {
                "demand_per_m2": sum(v["req"] for k,v in matrix.items() if k != "renewable"), 
                "consume_per_m2": total_con, 
                "primary_per_m2": total_con * 2.75, 
                "co2_per_m2": total_con * 0.466, 
                "independence": independence_val
            }
            
            financial = {
                "annual_elec_bill": int(annual_elec_bill),
                "annual_heat_bill": int(annual_heat_bill),
                "total_energy_bill": int(annual_elec_bill + annual_heat_bill),
                "capital_cost": int(total_capital_cost),
                "cost_details": {
                    "window": int(window_cost), 
                    "insulation": int(insulation_cost), 
                    "led": int(led_cost), 
                    "hvac": int(hvac_cost)
                },
                "mapped_window_name": mapped_window_name,
                "csv_db_loaded": self.cost_db["status"]
            }
            
            final_data = { 
                "summary": summary, 
                "monthly": monthly_data, 
                "matrix": matrix, 
                "financial": financial 
            }
            
            return { **final_data, "result": final_data }
            
        except Exception as e:
            print(f"⚠️ LCC Analyzer 파싱 에러: {e}")
            return self._fallback_data()

    def _fallback_data(self):
        fallback_data = {
            "summary": {"demand_per_m2": 50, "consume_per_m2": 30, "primary_per_m2": 80, "co2_per_m2": 15, "independence": 10}, 
            "monthly": [{"name": f"{i}월", "heating": 5, "cooling": 5} for i in range(1, 13)], 
            "matrix": {},
            "financial": {
                "mapped_window_name": "기본 단가 반영 (DB 미매칭)", 
                "annual_elec_bill": 0, 
                "annual_heat_bill": 0, 
                "capital_cost": 0, 
                "cost_details": {"window": 0, "insulation": 0, "led": 0, "hvac": 0},
                "csv_db_loaded": {"eco_loaded": False, "nara_loaded": False, "items": 0}
            }
        }
        return { **fallback_data, "result": fallback_data }
