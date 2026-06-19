# src/cost_analyzer.py
import os
import re
import statistics

try:
    import pandas as pd
except ImportError:
    pd = None

class LCCAnalyzer:
    """
    Building Energy Modeling (BEM) 경제성 및 요금(LCC) 분석 오픈소스 모듈
    EnergyPlus 결과와 독립적으로 계산을 수행합니다.
    """
    # ── 전기요금: 2026.4.16 시행 '일반용(갑) 저압' 계절 요금 (원/kWh) ──
    # (한전 전기요금표 종합 기준 — 일반 비주거 건물 적용. 저압은 시간대별 차등 없이 계절 평탄)
    ELEC_RATE_SUMMER = 123.6   # 여름철 6~8월
    ELEC_RATE_WINTER = 110.8   # 겨울철 11~2월
    ELEC_RATE_SPRING = 86.4    # 봄·가을철 3~5, 9~10월
    ELEC_BASE_CHARGE = 5230    # 일반용 저압 기본요금 (원/kW)
    # 지역난방: KDHC 공식 열요금표(2024.7.1, 부가세 별도) — 주택용 난방 사용요금
    #   단일요금 112.32원/Mcal 적용. (참고: 업무용 145.82 / 공공용 127.34 원/Mcal)
    #   1 Mcal = 1.163 kWh → 원/kWh = 원/Mcal ÷ 1.163 (≈ ×0.8598)
    HEAT_RATE_MCAL = 112.32     # 주택용 난방 단일요금
    HEAT_RATE_KWH = HEAT_RATE_MCAL / 1.163   # ≈ 96.6원/kWh

    # ── 난방 열원별 {요금(원/kWh), 1차에너지계수, CO2계수(kgCO2/kWh)} ──
    # 열원에 따라 요금·1차·CO2가 모두 달라진다. 지열/히트펌프는 전기로 본다.
    # 전기=한전 공식, 지역난방=KDHC 공식. (가스·등유는 미사용으로 제외)
    HEAT_SOURCE_DB = {
        2:  {"label": "전기(히트펌프)", "rate": ELEC_RATE_WINTER, "primary": 2.75,  "co2": 0.466},
        11: {"label": "지역난방",       "rate": HEAT_RATE_KWH,    "primary": 0.728, "co2": 0.200},
    }
    DEFAULT_HEAT_SOURCE = 11   # 미지정 시 지역난방(기존 동작과 동일)

    # ── 비교 기준이 되는 '기존 노후 건물' 운영비 추정 ──
    # ⚠️ 실측 데이터가 없으므로 단일·투명·보수적 가정을 쓴다.
    #    기존 건물 운영비 = 리모델링 후 운영비 × 배수. (절감률 = (배수-1)/배수)
    #    NPV/IRR/절감액은 전적으로 이 가정 대비 차이이므로 UI에 '추정 기준'으로 표기한다.
    #    1.6 → 기존이 60% 더 비쌈 ≈ 절감률 37.5%
    BASELINE_RUNNING_COST_MULTIPLIER = 1.6

    # ── 에너지원별 1차에너지 환산계수 / CO2 배출계수 ──
    # 전기는 발전·송배전 손실로 계수가 높고, 열(난방·급탕)은 낮다.
    # ⚠️ 열원이 가스가 아닌 지역난방이면 PRIMARY_FACTOR_HEAT=0.728로 조정.
    PRIMARY_FACTOR_ELEC = 2.75   # 전력 1차에너지 환산계수 (건축물 에너지효율등급 기준)
    PRIMARY_FACTOR_HEAT = 1.10   # 연료(가스) 기준 (지역난방 0.728)
    CO2_FACTOR_ELEC = 0.466      # 전력 배출계수 (kgCO2/kWh)
    CO2_FACTOR_HEAT = 0.232      # 가스(LNG) 연소 배출계수 (kgCO2/kWh)

    # LED 조명: 단가는 '개당(EA)' 기준이므로 면적은 등기구 개수로 환산해 적용한다.
    LED_FIXTURE_AREA_M2 = 10.0   # 등기구 1개가 담당하는 바닥면적 (㎡/개)

    # 공종별 단가 타당성 범위 (원). DB 추출값이 벗어나면 클램프 + 경고 → 오매핑 재발 방지.
    PRICE_BOUNDS = {
        "window_m2":     (50_000, 600_000),   # 창호 ₩/㎡
        "insulation_m2":  (5_000, 120_000),   # 단열재 ₩/㎡
        "led_ea":        (20_000, 500_000),   # LED 등기구 ₩/개
    }

    def _clamp_price(self, value, key, label=""):
        """DB에서 뽑은 단가가 상식 범위를 벗어나면 경계값으로 보정하고 경고를 남긴다."""
        lo, hi = self.PRICE_BOUNDS[key]
        v = min(max(value, lo), hi)
        if v != value:
            print(f"  ⚠️ 단가 가드: {label or key} ₩{int(value):,} → ₩{int(v):,} (정상범위 {lo:,}~{hi:,})")
        return v

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

    # ── 열전도율 기반 단열재 성능 등급 분류 시스템 ──
    # gbXML Material의 conductivity(λ) 값으로 4단계 등급 판별
    INSULATION_TIERS = {
        "premium": {
            "label": "고성능 (경질우레탄, 진공단열)",
            "lambda_range": (0.0, 0.030),
            "default_price": 50000,
            "keywords": ["우레탄", "진공", "PIR", "PUR", "phenol", "페놀"]
        },
        "high": {
            "label": "중성능 (XPS, 글라스울)",
            "lambda_range": (0.030, 0.040),
            "default_price": 25000,
            "keywords": ["압출", "XPS", "글라스울", "glass wool"]
        },
        "standard": {
            "label": "일반 (EPS, 미네랄울)",
            "lambda_range": (0.040, 0.070),
            "default_price": 15000,
            "keywords": ["비드", "EPS", "미네랄울", "mineral", "광물"]
        },
        "basic": {
            "label": "저성능 (펄라이트, 셀룰로오스)",
            "lambda_range": (0.070, 0.200),
            "default_price": 8000,
            "keywords": ["펄라이트", "셀룰로", "perlite", "cellulose"]
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
                "led_per_ea": 85000,   # LED 등기구 개당 단가(원/개) — DB에서 보정
                "hvac_kw_system": {
                    1: 1800000, # AHU
                    2: 2500000, # VRF/EHP
                    3: 2200000, # FCU
                    5: 1500000  # Generic
                },
                "hvac_kw_default": 2000000
            },
            "window_db": [],
            "window_tiers": {},  # 성능 등급별 {prices: [], avg: 0, count: 0}
            "insulation_tiers": {}  # 단열재 등급별 {avg: 0, count: 0, label: ""}
        }

        # 등급별 가격 수집용 임시 딕셔너리
        tier_prices = {tier: [] for tier in self.WINDOW_TIERS}
        insul_tier_prices = {tier: [] for tier in self.INSULATION_TIERS}
        
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
                            
                            # LED 조명 등기구 단가 수집 (개당/EA 기준)
                            # ⚠️ 'LED' 행에는 전광판·모니터·센서 등 비조명 품목과 EA 외 단위가 섞여 있어
                            #    조명 키워드 + EA 단위만 남기고 산업용 고가 이상치를 제외한 '중앙값'을 사용한다.
                            led_light_kw = '등|조명|램프|다운라이트|평판|직부|매입|벽등|투광|형광|전구|라이트'
                            led_noise_kw = '전광판|모니터|TV|스크린|표시기|센서|신호|가로등|보안등|디스플레이|패널|감시|카메라|광고|사이니지'
                            unit_col_led = next((c for c in df.columns if '단위' in str(c)), None)
                            led_mask = (
                                row_texts.str.contains('LED', na=False, case=False)
                                & row_texts.str.contains(led_light_kw, na=False)
                                & ~row_texts.str.contains(led_noise_kw, na=False, case=False)
                                & (df['price_num'] > 0)
                                & (df['price_num'] <= 1_000_000)   # 산업용 고가 이상치 제외
                            )
                            if unit_col_led is not None:
                                led_mask = led_mask & df[unit_col_led].astype(str).str.contains('EA|개', na=False, case=False)
                            led_valid = df[led_mask]
                            if not led_valid.empty:
                                led_med = int(self._clamp_price(led_valid['price_num'].median(), "led_ea", "LED 등기구"))
                                cost_db_dict["avg_prices"]["led_per_ea"] = led_med
                                print(f"  📊 LED 조명 DB: {len(led_valid)}건, 등기구 개당 중앙값 ₩{led_med:,}")
                            
                            # 단열재 단가 수집 (EL243.보온·단열재 카테고리)
                            insul_mask = row_texts.str.contains('EL243|보온.*단열재', na=False, case=False)
                            insul_items = df[insul_mask]
                            if not insul_items.empty:
                                # 단위 컬럼 찾기 (㎡ 단위만 필터)
                                unit_col = None
                                for c in df.columns:
                                    if '단위' in str(c):
                                        unit_col = c
                                        break
                                if unit_col is None:
                                    # Unnamed 컬럼 중 '㎡', '포', '대' 등이 포함된 컬럼 탐색
                                    for c in df.columns:
                                        sample = df[c].astype(str).head(20)
                                        if sample.str.contains('㎡|포|매', na=False).any():
                                            unit_col = c
                                            break
                                
                                if unit_col:
                                    m2_insul = insul_items[insul_items[unit_col].astype(str).str.contains('㎡', na=False)]
                                else:
                                    m2_insul = insul_items
                                
                                m2_valid = m2_insul[m2_insul['price_num'] > 0]
                                if not m2_valid.empty:
                                    # 등급별 단가와 동일하게 중앙값 + 타당성 클램프 (평균은 이상치에 민감)
                                    insul_fallback = int(self._clamp_price(m2_valid['price_num'].median(), "insulation_m2", "단열 폴백"))
                                    cost_db_dict["avg_prices"]["insulation"] = insul_fallback
                                    # 키워드 기반 등급 분류
                                    for _, row in m2_valid.iterrows():
                                        text_chunk = ' '.join(str(v) for v in row.values if str(v) != 'nan')
                                        price = row.get('price_num', 0)
                                        if price <= 0:
                                            continue
                                        for tier_key, tier_info in self.INSULATION_TIERS.items():
                                            if any(kw.lower() in text_chunk.lower() for kw in tier_info["keywords"]):
                                                insul_tier_prices[tier_key].append(price)
                                                break
                                    
                                    print(f"  📊 단열재 DB: ㎡ 단위 {len(m2_valid)}건, 중앙값 ₩{insul_fallback:,}/㎡")
                            
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
                # 이상치에 강한 중앙값 + 타당성 클램프
                avg_price = self._clamp_price(statistics.median(prices), "window_m2", f"창호 {tier_info['label']}")
                cost_db_dict["window_tiers"][tier_key] = {
                    "avg": int(avg_price),
                    "count": len(prices),
                    "label": tier_info["label"]
                }
                print(f"  📊 창호 [{tier_info['label']}] 등급: {len(prices)}건 → 중앙값 ₩{int(avg_price):,}/㎡")
            else:
                cost_db_dict["window_tiers"][tier_key] = {
                    "avg": tier_info["default_price"],
                    "count": 0,
                    "label": tier_info["label"]
                }

        total_window_items = sum(len(tier_prices[t]) for t in tier_prices)
        if total_window_items > 0:
            print(f"  ✅ 창호 성능 등급별 단가 매핑 완료! (총 {total_window_items}건 분류)")

        # 단열재 등급별 평균 단가 최종 산출
        for tier_key, tier_info in self.INSULATION_TIERS.items():
            prices = insul_tier_prices[tier_key]
            if prices:
                avg_price = self._clamp_price(statistics.median(prices), "insulation_m2", f"단열 {tier_info['label']}")
                cost_db_dict["insulation_tiers"][tier_key] = {
                    "avg": int(avg_price),
                    "count": len(prices),
                    "label": tier_info["label"]
                }
            else:
                cost_db_dict["insulation_tiers"][tier_key] = {
                    "avg": tier_info["default_price"],
                    "count": 0,
                    "label": tier_info["label"]
                }

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

    def match_insulation_price(self, conductivity: float, explicit_tier: str = None) -> tuple:
        """열전도율(conductivity)을 기반으로 가장 적합한 단열재 등급의 평균 단가를 반환합니다."""
        target_price = self.cost_db["avg_prices"]["insulation"]
        mapped_name = "기본 단열재 단가 (DB 미매칭)"
        
        if not self.cost_db.get("insulation_tiers") or (conductivity is None and explicit_tier is None):
            return target_price, mapped_name
            
        matched_tier = explicit_tier
        if not matched_tier and conductivity is not None:
            for tier_key, tier_info in self.INSULATION_TIERS.items():
                l_min, l_max = tier_info["lambda_range"]
                if l_min <= conductivity < l_max:
                    matched_tier = tier_key
                    break
                    
            if not matched_tier:
                # fallback
                if conductivity <= 0.030: matched_tier = "premium"
                elif conductivity <= 0.040: matched_tier = "high"
                elif conductivity <= 0.070: matched_tier = "standard"
                else: matched_tier = "basic"
            
        tier_data = self.cost_db["insulation_tiers"].get(matched_tier, {})
        if tier_data:
            target_price = tier_data["avg"]
            count = tier_data["count"]
            label = tier_data["label"]
            if count > 0:
                mapped_name = f"{label} (친환경DB {count}건 평균단가)"
            else:
                mapped_name = f"{label} (기본 추정단가)"
                
        return target_price, mapped_name

    def calculate(self, eplus_csv_path: str, zones: list, total_area: float,
                  total_window_area: float, total_wall_area: float,
                  target_u: float, target_shgc: float, pv_capacity_kw: float,
                  is_geothermal: bool, act_main: int, surfaces: list,
                  materials: dict, target_budget: float, led_fixture_count: int,
                  led_reduction_active: bool, **kwargs) -> dict:
        
        construction_overrides = kwargs.get("construction_overrides", {})
        
        if pd is None:
            return self._fallback_data()

        try:
            df = pd.read_csv(eplus_csv_path).fillna(0)
            df.columns = [c.strip() for c in df.columns]
            
            h_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Heating Energy' in c and '[J]' in c]
            c_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Cooling Energy' in c and '[J]' in c]
            h_rate_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Heating Rate' in c and '[W]' in c]
            c_rate_cols = [c for c in df.columns if 'Ideal Loads' in c and 'Cooling Rate' in c and '[W]' in c]
            l_cols = [c for c in df.columns if 'Lights' in c and 'Electricity Energy' in c and '[J]' in c]
            e_cols = [c for c in df.columns if 'Electric Equipment' in c and 'Electricity Energy' in c and '[J]' in c]
            # ⚠️ 급탕은 존마다 컬럼이 따로 있으므로 전부 합산 (기존 next()는 1개 존만 잡아 과소)
            dhw_cols = [c for c in df.columns if 'Water Use Equipment Heating Energy' in c]
            vent_cols = [c for c in df.columns if 'Mechanical Ventilation Mass Flow Rate' in c and '[kg/s]' in c]
            demand_col = next((c for c in df.columns if 'Facility Total Electric Demand Rate' in c), None)

            import numpy as np

            monthly_data = []
            
            total_rows = len(df)
            is_hourly = total_rows > 365
            
            if is_hourly:
                dt_str = df.iloc[:, 0].astype(str)
                # EnergyPlus format: ' 01/01  01:00:00'
                df['month'] = dt_str.str.extract(r'(\d{2})/\d{2}')[0].fillna(1).astype(int)
                df['hour'] = dt_str.str.extract(r'\s+(\d{2}):')[0].fillna(12).astype(int)
            else:
                df['month'] = np.arange(1, min(13, total_rows + 1))
                df['hour'] = 12

            total_c_con_kwh = np.zeros(total_rows)
            total_h_con_kwh = np.zeros(total_rows)
            total_c_req_kwh = np.zeros(total_rows)
            total_h_req_kwh = np.zeros(total_rows)
            total_c_rate_w = np.zeros(total_rows)
            total_h_rate_w = np.zeros(total_rows)

            for z in zones:
                z_id = z['id'].replace(" ", "_").upper()
                zh_cols = [c for c in h_cols if z_id in c.upper()]
                zc_cols = [c for c in c_cols if z_id in c.upper()]
                zr_h_cols = [c for c in h_rate_cols if z_id in c.upper()]
                zr_c_cols = [c for c in c_rate_cols if z_id in c.upper()]
                
                zh_kwh = df[zh_cols].sum(axis=1).values / 3600000.0 if zh_cols else 0.0
                zc_kwh = df[zc_cols].sum(axis=1).values / 3600000.0 if zc_cols else 0.0
                zh_rate = df[zr_h_cols].sum(axis=1).values if zr_h_cols else 0.0
                zc_rate = df[zr_c_cols].sum(axis=1).values if zr_c_cols else 0.0
                
                if not z.get("isConditioned", True):
                    continue
                    
                hvac_sys = z.get('hvacSystemId', 5)
                fuel_type = z.get('heatingFuelId', 2)
                
                if is_geothermal: 
                    h_cop, c_cop = 4.5, 5.0
                else:
                    c_cop = self.COOLING_EFF_DB.get(hvac_sys, 2.8)
                    h_cop = self.HEATING_EFF_DB.get(hvac_sys, {}).get(fuel_type, 1.0)
                    
                total_h_req_kwh += zh_kwh
                total_c_req_kwh += zc_kwh
                total_h_con_kwh += zh_kwh / h_cop
                total_c_con_kwh += zc_kwh / c_cop
                total_h_rate_w += zh_rate / h_cop
                total_c_rate_w += zc_rate / c_cop

            l_kwh = df[l_cols].sum(axis=1).values / 3600000.0 if l_cols else 0.0
            e_kwh = df[e_cols].sum(axis=1).values / 3600000.0 if e_cols else 0.0
            
            dhw_j = df[dhw_cols].sum(axis=1).values if dhw_cols else np.zeros(total_rows)
            dhw_kwh = (dhw_j / 3600000.0) * 1.1
            
            v_flow = df[vent_cols].sum(axis=1).values if vent_cols else np.zeros(total_rows)
            vent_multiplier = 1.0 if is_hourly else 730.0
            vent_kwh = (v_flow / 1.2) * 0.8 * vent_multiplier

            df['total_elec_kwh'] = total_c_con_kwh + l_kwh + e_kwh + vent_kwh
            df['total_heat_kwh'] = total_h_con_kwh + dhw_kwh

            # TOU Rate calculation (시간대별 차등 요금제 적용)
            def get_tou_rate(row):
                m, h = row['month'], row['hour']
                if m in [6, 7, 8]:
                    if 13 <= h < 17: return 147.3  # Peak
                    if (9 <= h < 13) or (17 <= h < 23): return 109.0  # Mid
                    return 56.1  # Off
                elif m in [11, 12, 1, 2]:
                    if (9 <= h < 12) or (16 <= h < 19): return 137.9
                    if (12 <= h < 16) or (19 <= h < 23): return 109.0
                    return 61.6
                else:
                    if 9 <= h < 23: return 65.5
                    return 56.1
                    
            if is_hourly:
                df['elec_rate'] = df.apply(get_tou_rate, axis=1)
            else:
                df['elec_rate'] = df['month'].apply(lambda m: self.ELEC_RATE_SUMMER if m in [6,7,8] else (self.ELEC_RATE_WINTER if m in [11,12,1,2] else self.ELEC_RATE_SPRING))

            df['elec_cost'] = df['total_elec_kwh'] * df['elec_rate']
            # 난방 열원 결정: 지열/히트펌프면 전기(2), 아니면 프로젝트 선택값(기본 지역난방)
            heat_source_id = 2 if is_geothermal else kwargs.get("heat_source", self.DEFAULT_HEAT_SOURCE)
            heat_src = self.HEAT_SOURCE_DB.get(heat_source_id, self.HEAT_SOURCE_DB[self.DEFAULT_HEAT_SOURCE])
            df['heat_cost'] = df['total_heat_kwh'] * heat_src["rate"]

            annual_elec_bill = df['elec_cost'].sum()
            annual_heat_bill = df['heat_cost'].sum()

            a_h_req = np.sum(total_h_req_kwh)
            a_c_req = np.sum(total_c_req_kwh)
            a_dhw_req = np.sum(dhw_j / 3600000.0) if dhw_cols else 0.0
            a_vent_req = np.sum((v_flow / 1.2) * vent_multiplier)
            
            a_h_con = np.sum(total_h_con_kwh)
            a_c_con = np.sum(total_c_con_kwh)
            a_l_con = np.sum(l_kwh)
            a_e_con = np.sum(e_kwh)
            a_dhw_con = np.sum(dhw_kwh)
            a_vent_con = np.sum(vent_kwh)

            base_demand = df[demand_col].values if demand_col else np.zeros(total_rows)
            peak_kw_series = (base_demand + total_c_rate_w + total_h_rate_w + (v_flow / 1.2 * 0.8 * 1000.0)) / 1000.0
            
            # 동시사용률(Diversity Factor) 0.8 적용하여 피크 과대평가 방지
            peak_elec_kw = peak_kw_series.max() * 0.8 if len(peak_kw_series) > 0 else 0
            peak_kw_estimate = peak_elec_kw if peak_elec_kw > 0 else total_area * 0.05
            annual_elec_bill += peak_kw_estimate * self.ELEC_BASE_CHARGE * 12
            
            for m in range(1, 13):
                mask_m = (df['month'] == m).values
                # 난방은 '공간 난방'만 (급탕 DHW는 연중 발생하므로 제외 → 냉방과 대칭)
                # 기존엔 total_heat_kwh(=공간난방+급탕)를 써서 여름에도 급탕만큼 난방값이 떠 보였음
                monthly_data.append({
                    "name": f"{m}월",
                    "heating": round(np.sum(total_h_con_kwh[mask_m]) / total_area, 1) if total_area > 0 else 0,
                    "cooling": round(np.sum(total_c_con_kwh[mask_m]) / total_area, 1) if total_area > 0 else 0
                })

            pv_gen = ((pv_capacity_kw * 1300) / total_area) if pv_capacity_kw and total_area > 0 else 0.0
            
            target_window_price, mapped_window_name = self.match_window_price(target_u, target_shgc)
            
            window_cost = total_window_area * target_window_price
            
            # 단열 공사비 계산
            insulation_cost = 0.0
            detailed_insulation_costs = []
            
            for s in surfaces:
                s_id = s.get("id")
                s_area = s.get("area", 0.0)
                
                # 프론트엔드 캐시로 인해 area가 없을 경우 자체 계산 (긴급 패치)
                if s_area <= 0 and s.get("vertices"):
                    try:
                        from src.gbxml_parser import calculate_surface_area
                        s_area = round(calculate_surface_area(s["vertices"]), 2)
                    except Exception:
                        pass
                        
                s_type = s.get("type", s.get("surfaceType", ""))
                if s_area <= 0 or s_type in ["InteriorWall", "InteriorFloor", "Ceiling"]:
                    continue
                
                has_insulation = False
                conductivity = None
                
                override = construction_overrides.get(s_id)
                if override and (override.get("isCustom") or override.get("insulationId") is not None):
                    has_insulation = True
                    # ⚠️ 함수 파라미터 target_u를 덮어쓰지 않도록 지역변수 사용
                    surf_u = override.get("uValue", s.get("uValue", 0.4))

                    if override.get("isCustom"):
                        t_insul = override.get("insulThick", 100) / 1000.0
                    else:
                        t_insul = override.get("thickness", 100) / 1000.0

                    # 단열층 열전도율 추정: λ = 두께 / 단열저항
                    #   단열저항 ≈ 전체저항(1/U) − 표면열전달저항(0.17). 구조층은 보수적으로 무시.
                    #   (기존 t_insul×U는 단위는 맞지만 λ를 체계적으로 과소평가 → 등급 과대평가)
                    r_total = (1.0 / surf_u) if surf_u and surf_u > 0 else 0.0
                    r_insul = max(r_total - 0.17, 0.1)
                    conductivity = t_insul / r_insul if r_insul > 0 else 0.04
                else:
                    c_id = s.get("constructionRef") or s.get("constructionId")
                    if materials and "constructions" in materials:
                        c = next((c for c in materials["constructions"] if c["id"] == c_id), None)
                        if c:
                            for layer in c.get("layers", []):
                                if layer.get("isInsulation"):
                                    has_insulation = True
                                    conductivity = layer.get("conductivity", 0.04)
                                    break
                                    
                override_tier = override.get("tier") if override else None
                
                if has_insulation and (conductivity is not None or override_tier is not None):
                    price, tier_label = self.match_insulation_price(conductivity, explicit_tier=override_tier)
                    cost = s_area * price
                    insulation_cost += cost
                    detailed_insulation_costs.append({
                        "surfaceId": s_id,
                        "area": s_area,
                        "price": price,
                        "cost": int(cost),
                        "tier": tier_label
                    })
                    
            if insulation_cost == 0.0 and total_wall_area > 0:
                insulation_cost = total_wall_area * self.cost_db["avg_prices"]["insulation"]
            
            # LED 공사 면적 산출: 비거주 구역(계단실, 기계실, 창고, 엘리베이터 등)은
            # 조명 밀도가 낮으므로 해당 면적의 30%만 LED 공사 대상으로 반영
            NON_HABITABLE_KEYWORDS = [
                'stair', 'chase', 'shaft', 'lift', 'elevator', 'store', 'storage',
                'parking', 'garage', 'vent', 'mechanical', 'duct', 'pipe',
                '계단', '엘리베이터', '창고', '주차', '기계', '덕트'
            ]
            habitable_area = 0.0
            non_habitable_area = 0.0
            for z in zones:
                z_name = z.get('name', '').lower()
                z_area = z.get('area', 0)
                if not z_area:
                    z_area = total_area / max(len(zones), 1)
                if any(kw in z_name for kw in NON_HABITABLE_KEYWORDS):
                    non_habitable_area += z_area
                else:
                    habitable_area += z_area
            # LED 비용은 '등기구 개당(EA)' 단가로 통일 (면적 기준일 때도 개수로 환산)
            led_per_ea = self.cost_db["avg_prices"].get("led_per_ea", 85000)
            if led_fixture_count > 0:
                # 사용자가 직접 입력한 등기구 수량 기준
                led_cost = led_fixture_count * led_per_ea
            else:
                if led_reduction_active:
                    led_effective_area = habitable_area  # 공용구역 전체 제외
                else:
                    led_effective_area = habitable_area + (non_habitable_area * 0.3)
                # 안전장치: 면적이 0이면 전체 면적 비율을 조정하여 기본값으로 사용
                if led_effective_area < 1.0:
                    led_effective_area = total_area * (0.5 if led_reduction_active else 0.7)
                # 면적 → 등기구 개수 환산(약 LED_FIXTURE_AREA_M2 ㎡당 1개) 후 개당 단가 적용
                est_fixtures = led_effective_area / self.LED_FIXTURE_AREA_M2
                led_cost = est_fixtures * led_per_ea
            
            hvac_upgrade_active = kwargs.get("hvac_upgrade_active", False)
            
            main_hvac_sys = 5
            for z in zones:
                if z.get("isConditioned", True):
                    main_hvac_sys = z.get('hvacSystemId', 5)
                    break
            
            hvac_unit_cost = self.cost_db["avg_prices"]["hvac_kw_system"].get(main_hvac_sys, self.cost_db["avg_prices"]["hvac_kw_default"])
                    
            if is_geothermal or hvac_upgrade_active:
                hvac_cost = peak_kw_estimate * hvac_unit_cost
            else:
                hvac_cost = 0.0
            
            total_capital_cost = window_cost + insulation_cost + led_cost + hvac_cost

            # 공사비 비중 새너티 점검: 단가/물량 오매핑으로 한 공종이 비정상 지배하면 경고
            # (설비는 전면교체 시 정상적으로 클 수 있어 임계 제외)
            cost_warnings = []
            if total_capital_cost > 0:
                _shares = {"창호": window_cost, "단열": insulation_cost, "LED": led_cost}
                for _label, _val in _shares.items():
                    _share = _val / total_capital_cost
                    if _share > 0.6:
                        _msg = f"{_label} 공사비가 전체의 {_share*100:.0f}%로 과도합니다 — 단가/물량 매핑 점검 필요"
                        cost_warnings.append(_msg)
                        print(f"  ⚠️ 비중 점검: {_msg}")

            # 생애주기비용(LCC) 현금흐름 계산 (할인 현금흐름 방식)
            discount_rate = kwargs.get("discount_rate", 0.05)
            inflation_rate = kwargs.get("inflation_rate", 0.03)
            utility_inflation = kwargs.get("utility_inflation", 0.04)
            years = kwargs.get("lifecycle_years", 20)
            
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

            matrix = {
                "heating": {"req": round(a_h_req/total_area, 1), "con": round(a_h_con/total_area, 1)},
                "cooling": {"req": round(a_c_req/total_area, 1), "con": round(a_c_con/total_area, 1)},
                "hotwater": {"req": round(a_dhw_req/total_area, 1), "con": round(a_dhw_con/total_area, 1)},
                "lighting": {"req": round(a_l_con/total_area, 1), "con": round(a_l_con/total_area, 1)},
                "ventilation": {"req": round(a_vent_req/total_area, 1), "con": round(a_vent_con/total_area, 1)},
                "equipment": {"req": round(a_e_con/total_area, 1), "con": round(a_e_con/total_area, 1)},
                "renewable": {"req": -round(pv_gen, 1), "con": -round(pv_gen, 1)}
            }
            
            # ZEB 등급 평가용 5대 에너지 기준 소요량 (신재생, 기기부하 제외)
            total_con_zeb = sum(v["con"] for k,v in matrix.items() if k not in ["renewable", "equipment"])
            independence_val = min(100, (abs(matrix["renewable"]["con"]) / total_con_zeb * 100)) if total_con_zeb > 0 else 0
            
            # 실제 전체 에너지 소요량 (LCC 및 탄소배출, 요금제용)
            total_con_actual = sum(v["con"] for k,v in matrix.items() if k != "renewable")

            # ── 에너지원별 분리: 전기(냉방·조명·환기·기기) vs 열(난방·급탕) ──
            # 1차에너지/CO2를 단일 전기계수로 일괄 적용하던 것을 원별 계수로 분리
            elec_con_zeb = matrix["cooling"]["con"] + matrix["lighting"]["con"] + matrix["ventilation"]["con"]
            heat_con     = matrix["heating"]["con"] + matrix["hotwater"]["con"]
            elec_con_actual = elec_con_zeb + matrix["equipment"]["con"]

            primary_per_m2 = elec_con_zeb * self.PRIMARY_FACTOR_ELEC + heat_con * heat_src["primary"]
            co2_per_m2     = elec_con_actual * self.CO2_FACTOR_ELEC + heat_con * heat_src["co2"]

            summary = {
                "demand_per_m2": sum(v["req"] for k,v in matrix.items() if k != "renewable"),
                "consume_per_m2": total_con_actual,
                "primary_per_m2": round(primary_per_m2, 1),
                "co2_per_m2": round(co2_per_m2, 2),
                "independence": independence_val
            }
            
            recommendations = []
            if target_budget > 0 and total_capital_cost > target_budget:
                if '고성능' in mapped_window_name or 'premium' in mapped_window_name.lower():
                    std_price = self.cost_db.get("window_tiers", {}).get("standard", {}).get("avg", 180000)
                    saved_cost = window_cost - (total_window_area * std_price)
                    if saved_cost > 0:
                        recommendations.append({
                            "type": "window",
                            "title": "창호 등급 하향 (Premium → Standard)",
                            "description": "최상급 창호 대신 일반 복층 유리로 변경하면 공사비를 크게 절감할 수 있습니다.",
                            "saved_cost": int(saved_cost)
                        })
                elif '중성능' in mapped_window_name or 'high' in mapped_window_name.lower():
                    std_price = self.cost_db.get("window_tiers", {}).get("standard", {}).get("avg", 180000)
                    saved_cost = window_cost - (total_window_area * std_price)
                    if saved_cost > 0:
                        recommendations.append({
                            "type": "window",
                            "title": "창호 등급 하향 (High → Standard)",
                            "description": "로이 복층유리 대신 일반 복층 유리로 변경하여 예산을 아낄 수 있습니다.",
                            "saved_cost": int(saved_cost)
                        })
                        
                high_tier_insul_cost = 0
                std_insul_price = self.cost_db.get("insulation_tiers", {}).get("standard", {}).get("avg", 15000)
                std_insul_cost_sum = 0
                
                if 'detailed_insulation_costs' in locals() and detailed_insulation_costs:
                    for d in detailed_insulation_costs:
                        if '고성능' in d["tier"] or 'premium' in d["tier"].lower() or '중성능' in d["tier"] or 'high' in d["tier"].lower():
                            high_tier_insul_cost += d["cost"]
                            std_insul_cost_sum += d["area"] * std_insul_price

                if high_tier_insul_cost > std_insul_cost_sum:
                    saved_insul = high_tier_insul_cost - std_insul_cost_sum
                    recommendations.append({
                        "type": "insulation",
                        "title": "단열재 사양 하향 (일반 EPS/미네랄울 활용)",
                        "description": "고성능 단열재 대신 일반 단열재로 변경할 경우 초기 비용이 감소합니다.",
                        "saved_cost": int(saved_insul)
                    })
                    
                if is_geothermal:
                    saved_hvac = hvac_cost * 0.4
                    recommendations.append({
                        "type": "hvac",
                        "title": "지열 난방 시스템 해제",
                        "description": "초기 설치비가 높은 지열 시스템을 일반 시스템으로 변경하여 비용을 절감합니다.",
                        "saved_cost": int(saved_hvac)
                    })
                elif hvac_upgrade_active:
                    saved_hvac = hvac_cost
                    recommendations.append({
                        "type": "hvac",
                        "title": "설비 시스템 전면 교체 보류",
                        "description": "기존 냉난방 설비를 유지하여 막대한 초기 공사비를 대폭 절감합니다.",
                        "saved_cost": int(saved_hvac)
                    })

                if led_cost > 0:
                    if led_fixture_count > 0:
                        saved_led = led_cost * 0.5
                        desc = "직접 입력한 LED 교체 수량을 50% 축소하여 필수 구역만 우선 교체합니다."
                        title = "LED 조명 교체 수량 축소 (50%)"
                    else:
                        saved_led = led_cost * 0.3
                        desc = "계단실, 복도, 창고 등 공용 구역을 제외하고 주요 거주 구역 위주로 부분 교체합니다."
                        title = "LED 조명 부분 교체 (공용구역 제외)"
                    recommendations.append({
                        "type": "led",
                        "title": title,
                        "description": desc,
                        "saved_cost": int(saved_led)
                    })

            # 단순 IRR (내부수익률) 계산기 (Bisection method)
            # 상한을 5.0(500%)까지 넓혀 인위적으로 100%에 고정되지 않게 한다.
            def calculate_irr(cash_flows, max_iter=200):
                low, high = -0.99, 5.0
                for _ in range(max_iter):
                    rate = (low + high) / 2
                    npv_test = sum(cf / ((1 + rate) ** t) for t, cf in enumerate(cash_flows))
                    if abs(npv_test) < 1e-5: return rate
                    if npv_test > 0: low = rate
                    else: high = rate
                return rate
                
            # 현금흐름 배열 (Year 0 = -초기투자비, Year 1~N = 기존 노후 건물 대비 절감액)
            # ⚠️ 기준 건물 운영비 = 리모델링 후 운영비 × 배수 (단일·투명 가정).
            #    프론트 LCC 차트와 동일한 모델을 사용해 NPV/IRR과 차트가 일관되게 한다.
            retrofit_running_cost = annual_elec_bill + annual_heat_bill

            # ── 기준 건물(리모델링 전) 연간 운영비 산정 ──
            # 우선순위: ① 실측 요금 → ② 실측 사용량(공식 단가 환산) → ③ 1.6배 추정(fallback)
            #   어떤 기준을 썼는지 baseline_source로 내려보내 UI가 명시 고지한다.
            act_elec_bill = kwargs.get("actual_elec_bill")
            act_heat_bill = kwargs.get("actual_heat_bill")
            act_elec_kwh  = kwargs.get("actual_elec_kwh")
            act_heat_kwh  = kwargs.get("actual_heat_kwh")
            avg_elec_rate = (self.ELEC_RATE_SUMMER + self.ELEC_RATE_WINTER + self.ELEC_RATE_SPRING) / 3.0

            if act_elec_bill or act_heat_bill:
                base_running_cost = (act_elec_bill or 0.0) + (act_heat_bill or 0.0)
                baseline_source = "actual_bill"          # 실측(요금)
            elif act_elec_kwh or act_heat_kwh:
                base_running_cost = (act_elec_kwh or 0.0) * avg_elec_rate + (act_heat_kwh or 0.0) * heat_src["rate"]
                baseline_source = "actual_usage"         # 실측(사용량 환산)
            else:
                base_running_cost = retrofit_running_cost * self.BASELINE_RUNNING_COST_MULTIPLIER
                baseline_source = "estimate"             # 추정(1.6배)

            if baseline_source != "estimate" and base_running_cost <= retrofit_running_cost:
                cost_warnings.append(
                    "입력한 기존 건물 운영비가 리모델링 후 운영비보다 낮거나 같습니다 — 절감액이 음수가 될 수 있으니 입력값을 확인하세요"
                )

            cash_flows = [-total_capital_cost]
            for y in range(1, years + 1):
                base_cost_y = base_running_cost * ((1 + utility_inflation) ** y)
                yearly_op_cost_y = (annual_elec_bill + annual_heat_bill) * ((1 + utility_inflation) ** y)
                maint_cost_y = ((hvac_cost * 0.02) + (led_cost * 0.01)) * ((1 + inflation_rate) ** y)
                
                rep_cost_y = 0
                # NPV 누적 계산(cumulative_lcc_30y)과 동일한 교체 가정 사용:
                #   15년차 핵심기기 50% 부분 교체, 10년차 LED 40% 교체
                if y % 15 == 0: rep_cost_y += (hvac_cost * 0.5) * ((1 + inflation_rate) ** y)
                if y % 10 == 0: rep_cost_y += (led_cost * 0.4) * ((1 + inflation_rate) ** y)

                # 절감액 = (기존 건물 운영비) - (리모델링 후 운영비 + 유지보수 + 교체비)
                net_savings = base_cost_y - (yearly_op_cost_y + maint_cost_y + rep_cost_y)
                cash_flows.append(net_savings)

            irr_val = calculate_irr(cash_flows) * 100

            # 비현실적으로 높은 IRR은 (초기투자비 대비 절감액 과다) 가정 민감도 경고
            if irr_val > 100:
                cost_warnings.append(
                    f"IRR이 {irr_val:.0f}%로 비정상적으로 높습니다 — 초기투자비가 작거나 기준 건물 가정이 절감액을 과대평가했을 수 있어 참고용으로만 보세요"
                )
                print(f"  ⚠️ IRR 점검: {irr_val:.0f}% (가정 민감도 높음)")

            # 순현재가치(NPV) = 순절감액 현금흐름을 할인율로 할인한 현재가치의 합
            #   (cash_flows[0] = -초기투자비 이므로 자본비가 이미 반영됨)
            #   IRR과 동일한 현금흐름을 사용 → 두 지표가 일관됨. 0 이상이면 투자 타당.
            npv_real = sum(cf / ((1 + discount_rate) ** t) for t, cf in enumerate(cash_flows))

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
                "total_lcc": int(lcc_pv),
                "irr": round(irr_val, 2),
                "cost_warnings": cost_warnings,
                "heat_source": heat_src["label"],   # 적용된 난방 열원 (UI 표기용)
                # NPV/IRR/절감액이 비교한 '기존 건물' 기준 (UI 명시 고지용)
                "baseline_assumptions": {
                    "source": baseline_source,                       # actual_bill | actual_usage | estimate
                    "base_running_cost": int(base_running_cost),      # 적용된 기존 건물 연간 운영비
                    "running_cost_multiplier": self.BASELINE_RUNNING_COST_MULTIPLIER,
                    "savings_pct": round((1 - retrofit_running_cost / base_running_cost) * 100) if base_running_cost > 0 else 0
                }
            }
            
            surface_thermal = {}
            if surfaces:
                for s in surfaces:
                    s_id = s['id'].upper()
                    temp_col = None
                    rad_col = None
                    for col in df.columns:
                        col_upper = col.upper()
                        if col_upper.startswith(s_id + ":") or col_upper.startswith(s_id + "_MIRROR:"):
                            if 'SURFACE OUTSIDE FACE TEMPERATURE' in col_upper:
                                temp_col = col
                            elif 'SURFACE OUTSIDE FACE INCIDENT SOLAR' in col_upper:
                                rad_col = col
                    
                    temp_months = []
                    rad_months = []
                    for m in range(min(12, len(df))):
                        t_val = float(df.iloc[m][temp_col]) if temp_col else 20.0
                        r_val = float(df.iloc[m][rad_col]) if rad_col else 100.0
                        temp_months.append(round(t_val, 2))
                        rad_months.append(round(r_val, 2))
                        
                    surface_thermal[s['id']] = {
                        "temperature": temp_months,
                        "radiation": rad_months
                    }

            surface_airflow = {}
            if surfaces:
                for s in surfaces:
                    win_id = f"WIN_{s['id']}".upper()
                    flow1_col = None
                    flow2_col = None
                    for col in df.columns:
                        col_upper = col.upper()
                        if col_upper.startswith(win_id + ":"):
                            if 'NODE 1 TO NODE 2 VOLUME FLOW RATE' in col_upper:
                                flow1_col = col
                            elif 'NODE 2 TO NODE 1 VOLUME FLOW RATE' in col_upper:
                                flow2_col = col
                    
                    inflow_months = []
                    outflow_months = []
                    for m in range(min(12, len(df))):
                        f1_val = float(df.iloc[m][flow1_col]) if flow1_col else 0.0
                        f2_val = float(df.iloc[m][flow2_col]) if flow2_col else 0.0
                        inflow_months.append(round(f1_val * 1000.0, 2))
                        outflow_months.append(round(f2_val * 1000.0, 2))
                        
                    surface_airflow[s['id']] = {
                        "inflow": inflow_months,
                        "outflow": outflow_months
                    }

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
            print(f"⚠️ LCC Analyzer 파싱 에러: {e}")
            return self._fallback_data()

    def _fallback_data(self):
        fallback_data = {
            "summary": {"demand_per_m2": 50, "consume_per_m2": 30, "primary_per_m2": 80, "co2_per_m2": 15, "independence": 10}, 
            "monthly": [{"name": f"{i}월", "heating": 5, "cooling": 5} for i in range(1, 13)], 
            "matrix": {
                "heating": {"req": 10, "con": 8},
                "cooling": {"req": 12, "con": 10},
                "hotwater": {"req": 5, "con": 5.5},
                "lighting": {"req": 8, "con": 8},
                "ventilation": {"req": 5, "con": 5},
                "equipment": {"req": 10, "con": 10},
                "renewable": {"req": -5, "con": -5}
            },
            "financial": {
                "mapped_window_name": "기본 단가 반영 (DB 미매칭)", 
                "annual_elec_bill": 0, 
                "annual_heat_bill": 0, 
                "capital_cost": 0, 
                "cost_details": {"window": 0, "insulation": 0, "led": 0, "hvac": 0},
                "insulation_details": [],
                "csv_db_loaded": {"eco_loaded": False, "nara_loaded": False, "items": 0}
            },
            "surfaceThermal": {},
            "surfaceAirflow": {}
        }
        return { **fallback_data, "result": fallback_data }
