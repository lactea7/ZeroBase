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

    # ── 성능 등급 기반 창호 가격 보간 시스템 ──
    # eco_materials.csv 규격 텍스트에서 키워드를 파싱하여 4단계 성능 등급으로 분류
    WINDOW_TIERS = {
        "premium": {
            "label": "고성능 Low-E+Ar 복층",
            "u_range": (0.0, 1.8),
            "default_price": 350000,
            "keywords_must": ["low-e", "로이"],
            "keywords_boost": ["ar", "아르곤", "삼중", "trp", "triple", "krypton"]
        },
        "high": {
            "label": "중성능 Low-E 복층",
            "u_range": (1.8, 2.5),
            "default_price": 250000,
            "keywords_must": ["low-e", "로이"],
            "keywords_boost": []
        },
        "standard": {
            "label": "일반 복층유리",
            "u_range": (2.5, 4.0),
            "default_price": 180000,
            "keywords_must": ["복층", "pair", "이중", "dbl"],
            "keywords_boost": []
        },
        "basic": {
            "label": "단층/일반유리",
            "u_range": (4.0, 99.0),
            "default_price": 120000,
            "keywords_must": [],
            "keywords_boost": []
        }
    }

    @staticmethod
    def _classify_window_tier(spec_text: str) -> str:
        """규격 텍스트에서 키워드를 분석하여 성능 등급을 분류합니다."""
        text = spec_text.lower()
        has_lowe = any(kw in text for kw in ['low-e', 'loe', '로이', 'low_e'])
        # 아르곤은 정확한 패턴만 매칭 (한글 '자재' 등에 ar이 포함되는 오탐 방지)
        has_argon = bool(re.search(r'\bar\b|아르곤|argon|krypton|크립톤|\d+mm\s*ar\s*\+|\+\s*\d+mm\s*ar', text))
        has_double = any(kw in text for kw in ['복층', 'pair', '이중', '22mm', '24mm', '26mm', '창세트'])
        has_triple = any(kw in text for kw in ['삼중', 'triple', '3중'])

        if has_lowe and (has_argon or has_triple):
            return "premium"
        elif has_lowe:
            return "high"
        elif has_double:
            return "standard"
        else:
            return "basic"

    def _load_cost_db(self):
        cost_db_dict = {
            "status": {"eco_loaded": False, "nara_loaded": False, "items": 0},
            "avg_prices": {
                "window": 250000,
                "insulation": 45000,
                "led": 30000,
                "hvac_kw": 2000000
            },
            "window_db": [],
            "window_tiers": {}  # 성능 등급별 {prices: [], avg: 0, count: 0}
        }

        # 등급별 가격 수집용 임시 딕셔너리
        tier_prices = {tier: [] for tier in self.WINDOW_TIERS}
        
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
                            
                            # 창호 및 유리공사 분류 아이템 필터링
                            window_mask = row_texts.str.contains('창호 및 유리공사|창호|유리|복층|로이', na=False, case=False)
                            window_items = df[window_mask]
                            
                            for idx, row in window_items.iterrows():
                                price = row.get('price_num', 0)
                                # ㎡ 단위 창호만 (접착제, 실링재 등 제외)
                                unit_col = None
                                for c in df.columns:
                                    if '단위' in c:
                                        unit_col = c
                                        break
                                
                                item_unit = str(row.get(unit_col, '')) if unit_col else ''
                                text_chunk = row_texts[idx]
                                
                                # 접착제, 실링재 등 비창호 자재 제외
                                if any(excl in text_chunk for excl in ['접착제', '실링재', '코킹', '테이프', '부자재']):
                                    continue
                                
                                if price > 10000 and '㎡' in item_unit:
                                    tier = self._classify_window_tier(text_chunk)
                                    tier_prices[tier].append(price)
                                    
                                    # 제품명 추출
                                    name_val = "친환경 창호"
                                    for col_name in ['인증제품명', '품명']:
                                        if col_name in df.columns:
                                            candidate = str(row.get(col_name, ''))
                                            if candidate and candidate != 'nan':
                                                name_val = candidate
                                                break
                                    
                                    cost_db_dict["window_db"].append({
                                        "name": name_val, 
                                        "tier": tier,
                                        "price": price
                                    })
                            
                            # LED 단가 수집
                            led_items = df[row_texts.str.contains('LED', na=False, case=False)]
                            if not led_items.empty: 
                                led_valid = led_items[led_items['price_num'] > 0]
                                if not led_valid.empty:
                                    cost_db_dict["avg_prices"]["led"] = led_valid['price_num'].mean()
                                
                            cost_db_dict["status"]["eco_loaded"] = True
                            cost_db_dict["status"]["items"] += len(df)
                        
                        elif any(col in df.columns for col in ['적용단가', '단위', '재료비', '거래가격']):
                            cost_db_dict["status"]["nara_loaded"] = True
                            cost_db_dict["status"]["items"] += len(df)
                            
                    except Exception as e:
                        print(f"Cost DB Error ({f_name}): {e}")

        # 등급별 평균 단가 최종 산출
        for tier_key, tier_info in self.WINDOW_TIERS.items():
            prices = tier_prices[tier_key]
            if prices:
                avg_price = sum(prices) / len(prices)
                cost_db_dict["window_tiers"][tier_key] = {
                    "avg": int(avg_price),
                    "count": len(prices),
                    "label": tier_info["label"]
                }
                print(f"  📊 창호 [{tier_info['label']}] 등급: {len(prices)}건 → 평균 ₩{int(avg_price):,}/㎡")
            else:
                cost_db_dict["window_tiers"][tier_key] = {
                    "avg": tier_info["default_price"],
                    "count": 0,
                    "label": tier_info["label"]
                }

        total_window_items = sum(len(tier_prices[t]) for t in tier_prices)
        if total_window_items > 0:
            print(f"  ✅ 창호 성능 등급별 단가 매핑 완료! (총 {total_window_items}건 분류)")

        return cost_db_dict

    def match_window_price(self, target_u: float, target_shgc: float) -> tuple:
        """U-Value를 기반으로 가장 적합한 성능 등급의 평균 단가를 보간하여 반환합니다."""
        # 기본값
        target_window_price = self.cost_db["avg_prices"]["window"]
        mapped_window_name = "기본 단가 반영 (DB 미매칭)"
        
        if not self.cost_db.get("window_tiers") or target_u is None:
            return target_window_price, mapped_window_name

        tiers = self.cost_db["window_tiers"]
        
        # U-Value 기반으로 성능 등급 판별
        matched_tier = None
        for tier_key, tier_info in self.WINDOW_TIERS.items():
            u_min, u_max = tier_info["u_range"]
            if u_min <= target_u < u_max:
                matched_tier = tier_key
                break
        
        if not matched_tier:
            matched_tier = "basic"

        tier_data = tiers.get(matched_tier, {})
        if tier_data:
            target_window_price = tier_data["avg"]
            count = tier_data["count"]
            label = tier_data["label"]
            
            if count > 0:
                mapped_window_name = f"{label} (친환경DB {count}건 평균단가)"
            else:
                mapped_window_name = f"{label} (기본 추정단가)"
                
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
