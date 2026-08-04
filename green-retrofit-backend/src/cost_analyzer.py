# src/cost_analyzer.py
import os
import re
import statistics

try:
    import pandas as pd
except ImportError:
    pd = None

# 비거주 구역 판별 키워드 — LED 공사 면적 축소·설비(냉방기) 설치 제외 등에 공용.
# (ep_simulator도 import: 계단실 등엔 WindowAC를 설치하지 않아 냉방부하 0 → 사이징 실패 방지)
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
    # ── 전기요금: 2026.4.16 시행 '일반용(갑) 저압' 계절 요금 (원/kWh) ──
    # (한전 전기요금표 종합 기준 — 일반 비주거 건물 적용. 저압은 시간대별 차등 없이 계절 평탄)
    ELEC_RATE_SUMMER = 123.6   # 여름철 6~8월
    ELEC_RATE_WINTER = 110.8   # 겨울철 11~2월
    ELEC_RATE_SPRING = 86.4    # 봄·가을철 3~5, 9~10월
    ELEC_BASE_CHARGE = 5230    # 일반용 저압 기본요금 (원/kW)

    # ── 시간대별(TOU) 요율: 일반용(을) 고압A 선택Ⅱ 기준 (원/kWh) ──
    # ⚠️ 요금 개정 시 위 계절 요율과 함께 이 테이블만 수정하면 된다 (요율의 단일 소스).
    #    시간별 출력(hourly)이 있으면 TOU, 월별 출력뿐이면 위 계절 평탄 요율을 적용한다.
    #    (엄밀히는 요금제 선택은 건물 계약 종별을 따라야 하나, 현재는 출력 주기 기준 근사)
    TOU_RATES = {
        "summer": {"peak": 147.3, "mid": 109.0, "off": 56.1},   # 6~8월
        "winter": {"peak": 137.9, "mid": 109.0, "off": 61.6},   # 11~2월
        "spring": {"peak": 65.5,  "mid": 65.5,  "off": 56.1},   # 3~5, 9~10월 (피크 구간 없음)
    }
    # 지역난방: KDHC 공식 열요금표(2024.7.1, 부가세 별도) — 주택용 난방 사용요금
    #   단일요금 112.32원/Mcal 적용. (참고: 업무용 145.82 / 공공용 127.34 원/Mcal)
    #   1 Mcal = 1.163 kWh → 원/kWh = 원/Mcal ÷ 1.163 (≈ ×0.8598)
    HEAT_RATE_MCAL = 112.32     # 주택용 난방 단일요금
    HEAT_RATE_KWH = HEAT_RATE_MCAL / 1.163   # ≈ 96.6원/kWh

    # ── 난방 열원별 {요금(원/kWh), 1차에너지계수, CO2계수(kgCO2/kWh)} ──
    # 열원에 따라 요금·1차·CO2가 모두 달라진다. 지열/히트펌프는 전기로 본다.
    # 전기=한전 공식, 지역난방=KDHC 공식. (가스·등유는 미사용으로 제외)
    HEAT_SOURCE_DB = {
        # 가스/등유 단가는 GR_Simulator(Site2Cost) 검증값 — 지역난방(94.98)이 당사 96.6과
        # 일치해 상호 신뢰 확인됨. CO2는 연료 연소 배출계수.
        1:  {"label": "가스보일러",     "rate": 78.12,            "primary": 1.10,  "co2": 0.232},
        2:  {"label": "전기(히트펌프)", "rate": ELEC_RATE_WINTER, "primary": 2.75,  "co2": 0.466},
        4:  {"label": "등유보일러",     "rate": 141.92,           "primary": 1.10,  "co2": 0.260},
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
    # 환기 외기 처리 에너지 원단위 (kWh per m³). 요구량·소요량 양쪽에 동일하게 적용해야
    # 차원이 맞는다. 이 계수가 req 에서 빠져 있어 체적(m³)이 kWh 합계에 더해지고 있었다.
    VENT_ENERGY_PER_M3 = 0.8
    CO2_FACTOR_HEAT = 0.232      # 가스(LNG) 연소 배출계수 (kgCO2/kWh)

    # LED 조명: 단가는 '개당(EA)' 기준이므로 면적은 등기구 개수로 환산해 적용한다.
    LED_FIXTURE_AREA_M2 = 10.0   # 등기구 1개가 담당하는 바닥면적 (㎡/개)

    # 공종별 단가 타당성 범위 (원). DB 추출값이 벗어나면 클램프 + 경고 → 오매핑 재발 방지.
    PRICE_BOUNDS = {
        "window_m2":     (50_000, 600_000),   # 창호(창세트) ₩/㎡
        "insulation_m2":  (3_000, 120_000),   # 단열재 ₩/㎡ (EPS 100mm 실거래 ~4천원대)
        "led_ea":        (20_000, 500_000),   # LED 등기구 ₩/개
    }

    # 두께당(T=1㎜) 단가로 등재된 단열재의 ㎡ 환산 기준 두께.
    # (EPS류가 '비드법 2종 1호(T=1㎜) 109원/㎡'식으로 등재됨 → ×100mm = 10,900원/㎡)
    STD_INSUL_THICKNESS_MM = 100

    def _clamp_price(self, value, key, label=""):
        """DB에서 뽑은 단가가 상식 범위를 벗어나면 경계값으로 보정하고 경고를 남긴다.
        발동 내역은 load_warnings에 쌓아 calculate()가 사용자 경고로 노출한다."""
        lo, hi = self.PRICE_BOUNDS[key]
        v = min(max(value, lo), hi)
        if v != value:
            msg = f"단가 가드 발동: {label or key} DB값 ₩{int(value):,} → ₩{int(v):,} 보정 (해당 단가는 실DB가 아닌 보정값)"
            print(f"  ⚠️ {msg}")
            self.load_warnings.append(msg)
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
        self.load_warnings = []   # DB 로드 중 품질 이슈(가드 발동 등) — calculate()가 노출
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

                                # 창호 '완제품(창세트)'만 등급 단가에 반영.
                                # 기존 키워드 필터는 '복층 비닐 타일'(바닥재), '발포유리보드'(단열재)
                                # 같은 오염 행이 섞여 standard 등급 중앙값이 27,486원(바닥재값)으로
                                # 붕괴됐었다. 리트로핏 시나리오도 창세트 교체이므로 완제품이 맞다.
                                if not ('창세트' in text_chunk or '창 세트' in text_chunk):
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
                                
                                m2_valid = m2_insul[m2_insul['price_num'] > 0].copy()
                                if not m2_valid.empty:
                                    # 두께당 단가(T=1㎜) 행 환산: EPS류는 'T=1㎜' ㎡·mm 단가로
                                    # 등재돼 있어(예: 109원) 그대로 쓰면 중앙값이 ₩106으로 붕괴.
                                    # 표준 시공 두께(100mm)를 곱해 다른 ㎡ 단가와 정합시킨다.
                                    # 표기 2종: '(T=1㎜)' 그리고 '900×1800㎜×1T'(1T=두께 1mm)
                                    spec_col = next((c for c in df.columns if '규격' in str(c)), None)
                                    if spec_col is not None:
                                        per_mm = m2_valid[spec_col].astype(str).str.contains(
                                            r'T\s*=\s*1\s*(?:㎜|mm)|[×xX]\s*1\s*T\b', na=False, regex=True)
                                        m2_valid.loc[per_mm, 'price_num'] *= self.STD_INSUL_THICKNESS_MM
                                        if per_mm.any():
                                            print(f"  🔧 두께당(T=1㎜) 단가 {per_mm.sum()}건 → {self.STD_INSUL_THICKNESS_MM}mm 환산")

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

        # 등급 단조성 보정 — 절감액(상위-하위 차액) 왜곡 방지
        _order = ["basic", "standard", "high", "premium"]
        self._enforce_tier_order(cost_db_dict["window_tiers"], _order, "창호")
        self._enforce_tier_order(cost_db_dict["insulation_tiers"], _order, "단열재")

        return cost_db_dict

    def _enforce_tier_order(self, tiers: dict, order: list, kind: str):
        """등급 단가가 성능 순서(basic≤standard≤high≤premium)를 지키도록 보정.

        1) 실데이터(count>0) 등급 간 역전 → 하위 등급 값으로 끌어올리고 경고
           (역전 = DB가 등급을 구분하지 못한다는 신호. 차액 기반 절감액이 왜곡되지 않게 함)
        2) 데이터 없는 등급의 기본값은 이웃 실데이터 범위 안으로 클램프
           (예: 저성능 기본값 8,000원이 실측 일반 등급 4,500원보다 비싼 역전 방지)
        """
        prev = None
        for tk in order:
            cur = tiers.get(tk)
            if not cur or cur.get("count", 0) == 0:
                continue
            if prev is not None and cur["avg"] < prev["avg"]:
                self.load_warnings.append(
                    f"{kind} DB 등급 역전: {cur['label']}({cur['avg']:,}원) < {prev['label']}({prev['avg']:,}원) — 하위 등급 단가로 보정"
                )
                cur["avg"] = prev["avg"]
            prev = cur

        reals = [(i, tiers[tk]["avg"]) for i, tk in enumerate(order)
                 if tiers.get(tk, {}).get("count", 0) > 0]
        for i, tk in enumerate(order):
            cur = tiers.get(tk)
            if not cur or cur.get("count", 0) > 0:
                continue
            lower = max((avg for j, avg in reals if j < i), default=None)
            upper = min((avg for j, avg in reals if j > i), default=None)
            v = cur["avg"]
            if lower is not None:
                v = max(v, lower)
            if upper is not None:
                v = min(v, upper)
            cur["avg"] = v

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
            raise RuntimeError("pandas가 설치되지 않아 비용 분석을 수행할 수 없습니다. (pip install pandas)")

        try:
            df = pd.read_csv(eplus_csv_path).fillna(0)
            df.columns = [c.strip() for c in df.columns]
            
            import numpy as np
            from src.energyplus.outputs import parse_outputs, ventilation_energy_kwh

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
            df['month'] = np.array(series.months)
            df['hour'] = np.array(series.hours)
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

            # 미터가 없어 추정으로 대체한 항목 — 조용한 추정을 막기 위해 사용자에게 노출
            _meter_fallback_notes = [s.note for s in series.context.fallback_steps if s.note]

            if use_pthp:
                # 히트펌프 난방=전기 → 난방 소비도 전기요금으로 (열 요금엔 급탕만)
                df['total_elec_kwh'] = total_c_con_kwh + total_h_con_kwh + l_kwh + e_kwh + vent_kwh
                df['total_heat_kwh'] = dhw_kwh
            else:
                df['total_elec_kwh'] = total_c_con_kwh + l_kwh + e_kwh + vent_kwh
                df['total_heat_kwh'] = total_h_con_kwh + dhw_kwh

            # TOU Rate calculation (시간대별 차등 요금제 — 요율은 self.TOU_RATES 단일 소스)
            def get_tou_rate(row):
                m, h = row['month'], row['hour']
                if m in [6, 7, 8]:
                    r = self.TOU_RATES["summer"]
                    if 13 <= h < 17: return r["peak"]
                    if (9 <= h < 13) or (17 <= h < 23): return r["mid"]
                    return r["off"]
                elif m in [11, 12, 1, 2]:
                    r = self.TOU_RATES["winter"]
                    if (9 <= h < 12) or (16 <= h < 19): return r["peak"]
                    if (12 <= h < 16) or (19 <= h < 23): return r["mid"]
                    return r["off"]
                else:
                    r = self.TOU_RATES["spring"]
                    if 9 <= h < 23: return r["mid"]
                    return r["off"]
                    
            if is_hourly:
                df['elec_rate'] = df.apply(get_tou_rate, axis=1)
            else:
                df['elec_rate'] = df['month'].apply(lambda m: self.ELEC_RATE_SUMMER if m in [6,7,8] else (self.ELEC_RATE_WINTER if m in [11,12,1,2] else self.ELEC_RATE_SPRING))

            # ── 태양광(PV) 자가소비 차감 ──
            # 연간 발전량(설치kW × 1300kWh/kW·년)을 주간(9~17시)에 균등 분배해 시간별
            # 소비에서 차감. TOU와 상호작용해 '비싼 낮 요금'을 깎는 실제 효과가 반영된다.
            # 잉여 발전(소비 초과분)은 버림 — 역송 보상(상계거래) 미반영, 보수적 추정.
            # (기존엔 PV가 ZEB 자립률 표시에만 쓰이고 요금에서 빠지지 않는 버그가 있었음)
            if pv_capacity_kw and pv_capacity_kw > 0:
                _day_mask = ((df['hour'] >= 9) & (df['hour'] < 17)).values
                _n_day = int(_day_mask.sum())
                if _n_day > 0:
                    _gen_per_step = (pv_capacity_kw * 1300.0) / _n_day
                    _gen_series = np.where(_day_mask, _gen_per_step, 0.0)
                    df['total_elec_kwh'] = np.maximum(df['total_elec_kwh'].values - _gen_series, 0.0)

            df['elec_cost'] = df['total_elec_kwh'] * df['elec_rate']
            # 난방 열원 결정: 지열/히트펌프면 전기(2), 아니면 프로젝트 선택값(기본 지역난방)
            heat_source_id = 2 if is_geothermal else kwargs.get("heat_source", self.DEFAULT_HEAT_SOURCE)
            heat_src = self.HEAT_SOURCE_DB.get(heat_source_id, self.HEAT_SOURCE_DB[self.DEFAULT_HEAT_SOURCE])
            df['heat_cost'] = df['total_heat_kwh'] * heat_src["rate"]

            annual_elec_bill = df['elec_cost'].sum()
            annual_heat_bill = df['heat_cost'].sum()

            a_h_req = np.sum(total_h_req_kwh)
            a_c_req = np.sum(total_c_req_kwh)
            # dhw_kwh 에는 배관손실 1.1 이 곱해져 있으므로 요구량은 되돌린다
            a_dhw_req = np.sum(dhw_kwh) / 1.1
            # 환기 요구량도 에너지(kWh)여야 한다. 팬 전력은 소요량 쪽에만 더한다.
            a_vent_req = np.sum(vent_kwh - fan_kwh)
            
            a_h_con = np.sum(total_h_con_kwh)
            a_c_con = np.sum(total_c_con_kwh)
            a_l_con = np.sum(l_kwh)
            a_e_con = np.sum(e_kwh)
            a_dhw_con = np.sum(dhw_kwh)
            a_vent_con = np.sum(vent_kwh)

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
            
            def _monthly_sum(series, mask):
                """시계열이 스칼라(해당 부하 없음)일 수 있어 안전하게 월합산."""
                if isinstance(series, np.ndarray):
                    return float(np.sum(series[mask]))
                return 0.0

            for m in range(1, 13):
                mask_m = (df['month'] == m).values
                # 난방은 '공간 난방'만 (급탕 DHW는 연중 발생하므로 제외 → 냉방과 대칭)
                # 기존엔 total_heat_kwh(=공간난방+급탕)를 써서 여름에도 급탕만큼 난방값이 떠 보였음
                _a = total_area if total_area > 0 else 1.0
                monthly_data.append({
                    "name": f"{m}월",
                    "heating": round(_monthly_sum(total_h_con_kwh, mask_m) / _a, 1),
                    "cooling": round(_monthly_sum(total_c_con_kwh, mask_m) / _a, 1),
                    "lighting": round(_monthly_sum(l_kwh, mask_m) / _a, 1),
                    "equipment": round(_monthly_sum(e_kwh, mask_m) / _a, 1),
                    "hotwater": round(_monthly_sum(dhw_kwh, mask_m) / _a, 1),
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
            habitable_area = 0.0
            non_habitable_area = 0.0
            for z in zones:
                # gbXML 파서는 존 용도명을 'id'에 담는다('name' 미발급) → is_non_habitable이 폴백 처리
                z_area = z.get('area', 0)
                if not z_area:
                    z_area = total_area / max(len(zones), 1)
                if is_non_habitable(z):
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

            # 추천 카드에 표시할 LED 절감액은 '적용 시 실제 차액'으로 계산한다.
            # (기존 led_cost×0.3은 비거주 면적의 30% 몫만 빠지는 실제 효과를 ~3배 과대표시했음)
            if led_fixture_count > 0:
                led_saving = led_cost * 0.5   # 수량 50% 축소 → 비용도 정확히 50% 감소
            elif not led_reduction_active:
                reduced_area = habitable_area if habitable_area >= 1.0 else total_area * 0.5
                led_cost_if_reduced = (reduced_area / self.LED_FIXTURE_AREA_M2) * led_per_ea
                led_saving = max(led_cost - led_cost_if_reduced, 0.0)
            else:
                led_saving = 0.0
            
            hvac_upgrade_active = kwargs.get("hvac_upgrade_active", False)
            
            main_hvac_sys = 5
            for z in zones:
                if z.get("isConditioned", True):
                    main_hvac_sys = z.get('hvacSystemId', 5)
                    break
            
            hvac_unit_cost = self.cost_db["avg_prices"]["hvac_kw_system"].get(main_hvac_sys, self.cost_db["avg_prices"]["hvac_kw_default"])
            # 지열(GSHP)은 천공·지중 열교환기 비용으로 일반 시스템보다 고가 → 프리미엄(×2.2) 반영
            if is_geothermal:
                hvac_unit_cost = int(hvac_unit_cost * 2.2)

            # 설비비는 항상 표시한다(건물에는 냉난방 설비가 필수). 토글 게이팅 제거 →
            # 실제 산정된 설비 용량(hvac_capacity_kw) × 시스템 단가로 일관 산출.
            hvac_cost = hvac_capacity_kw * hvac_unit_cost

            # 비거주 구역(계단실·창고·기계실 등) 설비 제외 옵션: 냉난방 용량은 공조 대상
            # 바닥면적에 대략 비례하므로, 비거주 면적 비율만큼 설비 규모(비용)를 축소한다.
            _total_zone_area = habitable_area + non_habitable_area
            non_hab_share = (non_habitable_area / _total_zone_area) if _total_zone_area > 0 else 0.0
            hvac_exclude_non_habitable = kwargs.get("hvac_exclude_non_habitable", False)
            if hvac_exclude_non_habitable and non_hab_share > 0:
                hvac_cost *= (1.0 - non_hab_share)
            
            total_capital_cost = window_cost + insulation_cost + led_cost + hvac_cost

            # 공사비 비중 새너티 점검: 단가/물량 오매핑으로 한 공종이 비정상 지배하면 경고
            # (설비는 전면교체 시 정상적으로 클 수 있어 임계 제외)
            # DB 품질 이슈(가드 발동 등) + 미터 폴백을 사용자에게 노출
            cost_warnings = list(self.load_warnings) + _meter_fallback_notes
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

            # ── 항목별 1차에너지·CO2를 matrix 에 실어 내린다 ──────────────────────
            # 프런트가 모든 항목에 전기계수(2.75/0.466)를 곱하던 탓에, 지역난방·가스를
            # 고르면 상세 표 합계와 요약 카드가 서로 달랐다. 계수 적용은 백엔드에서만
            # 하고 프런트는 받은 값을 그대로 표시한다.
            #   primary      : 원별 1차계수 적용 (기기 포함 — 정보용 총량)
            #   gradePrimary : 등급 산정용. 기기·신재생 제외 → 합계가 summary.primary_per_m2
            #   co2          : 원별 배출계수 적용. 신재생 제외 → 합계가 summary.co2_per_m2
            _heat_cats = ("heating", "hotwater")
            for _cat, _v in matrix.items():
                _con = _v["con"]
                if _cat in _heat_cats:
                    _pf, _cf = heat_src["primary"], heat_src["co2"]
                else:
                    _pf, _cf = self.PRIMARY_FACTOR_ELEC, self.CO2_FACTOR_ELEC
                _v["primary"] = round(_con * _pf, 1)
                _v["co2"] = 0.0 if _cat == "renewable" else round(_con * _cf, 2)
                _v["gradePrimary"] = (
                    0.0 if _cat in ("equipment", "renewable") else round(_con * _pf, 1)
                )

            summary = {
                "demand_per_m2": sum(v["req"] for k,v in matrix.items() if k != "renewable"),
                "consume_per_m2": total_con_actual,
                "primary_per_m2": round(primary_per_m2, 1),
                "co2_per_m2": round(co2_per_m2, 2),
                "independence": independence_val
            }
            
            recommendations = self._build_recommendations(
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
            # 우선순위: ① 실측 요금 → ② 실측 사용량(공식 단가 환산)
            #          → ③ 개선 전 건물 물리 시뮬레이션(전/후 비교) → ④ 1.6배 추정(fallback)
            #   어떤 기준을 썼는지 baseline_source로 내려보내 UI가 명시 고지한다.
            act_elec_bill = kwargs.get("actual_elec_bill")
            act_heat_bill = kwargs.get("actual_heat_bill")
            act_elec_kwh  = kwargs.get("actual_elec_kwh")
            act_heat_kwh  = kwargs.get("actual_heat_kwh")
            sim_base_elec = kwargs.get("sim_base_elec_bill")
            sim_base_heat = kwargs.get("sim_base_heat_bill")
            avg_elec_rate = (self.ELEC_RATE_SUMMER + self.ELEC_RATE_WINTER + self.ELEC_RATE_SPRING) / 3.0

            if act_elec_bill or act_heat_bill:
                base_running_cost = (act_elec_bill or 0.0) + (act_heat_bill or 0.0)
                baseline_source = "actual_bill"          # 실측(요금)
            elif act_elec_kwh or act_heat_kwh:
                base_running_cost = (act_elec_kwh or 0.0) * avg_elec_rate + (act_heat_kwh or 0.0) * heat_src["rate"]
                baseline_source = "actual_usage"         # 실측(사용량 환산)
            elif (sim_base_elec or 0) > 0 or (sim_base_heat or 0) > 0:
                base_running_cost = (sim_base_elec or 0.0) + (sim_base_heat or 0.0)
                baseline_source = "simulated"            # 개선 전 건물 시뮬레이션(전/후 비교)
            elif kwargs.get("sim_base_same"):
                # 개선 전후 모델이 동일 (편집 없음) → 절감 0이 정직한 답.
                # ×1.6 추정으로 가짜 절감이 표시되는 것을 막는다.
                base_running_cost = retrofit_running_cost
                baseline_source = "simulated"
                cost_warnings.append(
                    "개선 전후 모델이 동일합니다 — 창호·단열·설비 등을 편집하지 않아 절감액이 0으로 계산됩니다"
                )
            else:
                base_running_cost = retrofit_running_cost * self.BASELINE_RUNNING_COST_MULTIPLIER
                baseline_source = "estimate"             # 추정(1.6배)

            if baseline_source != "estimate" and base_running_cost <= retrofit_running_cost:
                cost_warnings.append(
                    "기존 건물 운영비(실측 또는 개선 전 시뮬레이션)가 리모델링 후 운영비보다 낮거나 같습니다 — "
                    "절감액이 음수가 될 수 있으니 입력값 또는 개선 항목을 확인하세요"
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
                "npv_sensitivity": npv_sensitivity,
                "hvac_capacity_kw": round(hvac_capacity_kw, 1),  # 공사비 산정 기준 용량 (UI 각주용)
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
                                 f"실측 요금 미입력 시 개선 후 운영비의 {self.BASELINE_RUNNING_COST_MULTIPLIER}배를 기존 건물로 가정합니다. 실측 요금을 입력하면 정확도가 올라갑니다.")
                    },
                    {
                        "label": "NPV·IRR",
                        "note": f"할인율 {discount_rate*100:.1f}%, 물가상승 {inflation_rate*100:.1f}%, 요금상승 {utility_inflation*100:.1f}%, 분석기간 {years}년 가정의 결과입니다."
                    },
                ]
            }
            
            surface_thermal, surface_airflow = self._surface_outputs(df, surfaces)

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

    def _build_recommendations(self, *, mapped_window_name, window_cost, total_window_area,
                               detailed_insulation_costs, is_geothermal, hvac_cost,
                               hvac_capacity_kw, hvac_unit_cost, hvac_exclude_non_habitable,
                               non_hab_share, led_cost, led_saving, led_fixture_count,
                               led_reduction_active, cooling_grade="grade3",
                               heating_age="new", hvac_upgraded=False):
        """개선 대안 추천 목록 생성 — 양방향. 예산 입력 여부와 무관하게 항상 생성한다.

        · 하향(direction 없음): 공사비 절감 — 예산 초과 대응. saved_cost = 적용 시 실제 차액.
        · 상향(direction="upgrade"): kWh/운영비 절감 — 노후 설비 교체·단열/창호 상향.
          정량 효과(에너지·실공사비·회수기간)는 ep_simulator의 대안 재시뮬레이션(impact)이 산출.
        예산 초과 여부에 따른 강조는 프론트가 target_budget/capital_cost로 판단한다.
        각 대안은 이미 적용된 상태면 반복 제시하지 않는다.
        """
        recommendations = []

        if '고성능' in mapped_window_name or 'premium' in mapped_window_name.lower():
            std_price = self.cost_db.get("window_tiers", {}).get("standard", {}).get("avg", 180000)
            saved_cost = window_cost - (total_window_area * std_price)
            if saved_cost > 0:
                recommendations.append({
                    "type": "window",
                    "title": "창호 등급 하향 (Premium → Standard)",
                    "description": "최상급 창호 대신 일반 복층 유리로 변경하면 공사비를 크게 절감할 수 있습니다.",
                    "saved_cost": int(saved_cost),
                    "performance_note": "창호 U값 상승으로 냉난방 부하·운영비가 증가합니다 — 적용 전 재시뮬레이션 권장"
                })
        elif '중성능' in mapped_window_name or 'high' in mapped_window_name.lower():
            std_price = self.cost_db.get("window_tiers", {}).get("standard", {}).get("avg", 180000)
            saved_cost = window_cost - (total_window_area * std_price)
            if saved_cost > 0:
                recommendations.append({
                    "type": "window",
                    "title": "창호 등급 하향 (High → Standard)",
                    "description": "로이 복층유리 대신 일반 복층 유리로 변경하여 예산을 아낄 수 있습니다.",
                    "saved_cost": int(saved_cost),
                    "performance_note": "창호 U값 상승으로 냉난방 부하·운영비가 증가합니다 — 적용 전 재시뮬레이션 권장"
                })

        high_tier_insul_cost = 0
        std_insul_price = self.cost_db.get("insulation_tiers", {}).get("standard", {}).get("avg", 15000)
        std_insul_cost_sum = 0
        for d in detailed_insulation_costs or []:
            if '고성능' in d["tier"] or 'premium' in d["tier"].lower() or '중성능' in d["tier"] or 'high' in d["tier"].lower():
                high_tier_insul_cost += d["cost"]
                std_insul_cost_sum += d["area"] * std_insul_price

        if high_tier_insul_cost > std_insul_cost_sum:
            recommendations.append({
                "type": "insulation",
                "title": "단열재 사양 하향 (일반 등급 EPS)",
                "description": "고성능 단열재 대신 일반 등급 EPS(비드법 1종 1호, λ0.036)로 변경해 초기 비용을 줄입니다.",
                "saved_cost": int(high_tier_insul_cost - std_insul_cost_sum),
                "performance_note": "외피 열관류율 상승으로 난방 요구량·CO₂가 증가합니다 — 적용 전 재시뮬레이션 권장"
            })

        if is_geothermal:
            # 지열 해제 시 절감액 = 지열 프리미엄(×2.2)분. 일반 시스템(×1.0)으로 환원되므로
            # saved = hvac_cost × (1.2/2.2). 설비비는 그대로 남고 프리미엄만 빠진다.
            recommendations.append({
                "type": "hvac",
                "title": "지열 난방 시스템 해제",
                "description": "초기 설치비가 높은 지열(GSHP) 시스템을 일반 시스템으로 변경하여 천공·지중 열교환기 비용을 절감합니다.",
                "saved_cost": int(hvac_cost * (1.2 / 2.2)),
                "performance_note": "열원 COP 하락(5.0→일반)으로 난방 운영비가 증가합니다 — 적용 전 재시뮬레이션 권장"
            })
        else:
            # 비지열: 고효율 설비(EHP·FCU·AHU)를 표준 개별 냉난방기(Generic, id 5)로 하향.
            # 설비비가 capital의 대부분을 차지하는 경우가 많아, 이 추천이 없으면 다른 항목을
            # 모두 적용해도 총액이 거의 안 줄던 문제를 해소한다. (이미 표준이면 절감 0 → 미표시)
            std_hvac_unit = self.cost_db["avg_prices"]["hvac_kw_system"].get(5, 1500000)
            if hvac_capacity_kw > 0 and hvac_unit_cost > std_hvac_unit:
                saved_hvac = hvac_capacity_kw * (hvac_unit_cost - std_hvac_unit)
                if saved_hvac > 0:
                    recommendations.append({
                        "type": "hvac",
                        "title": "고효율 냉난방 설비 → 표준 설비로 변경",
                        "description": "고가의 개별 히트펌프(EHP)·팬코일(FCU) 대신 표준 개별 냉난방기로 변경하여 설비 공사비를 절감합니다.",
                        "saved_cost": int(saved_hvac),
                        "performance_note": "설비 효율(COP) 하락으로 냉난방 운영비가 증가할 수 있습니다"
                    })

        # 이미 표준 설비여도 쓸 수 있는 대안: 비거주 구역(계단실·창고·기계실 등)을
        # 설비 범위에서 제외해 용량을 줄인다. 비거주 면적이 유의미할 때(3% 이상)만 제시.
        if (not is_geothermal and not hvac_exclude_non_habitable
                and non_hab_share >= 0.03 and hvac_cost > 0):
            recommendations.append({
                "type": "hvac_scope",
                "title": "비거주 구역 냉난방 설비 제외",
                "description": f"계단실·창고·기계실 등 비거주 구역(전체 면적의 약 {non_hab_share*100:.0f}%)을 설비 설치 범위에서 제외해 설비 용량과 공사비를 줄입니다.",
                "saved_cost": int(hvac_cost * non_hab_share),
                "performance_note": "해당 구역의 냉난방이 제공되지 않아 동파 방지 등 최소 온도 유지가 필요하면 부적합합니다"
            })

        # 절감액은 '적용 시 실제 차액'(led_saving)만 제시. 이미 적용됐거나 효과가 0이면 미표시.
        if led_cost > 0 and led_saving > 0:
            if led_fixture_count > 0:
                recommendations.append({
                    "type": "led",
                    "title": "LED 조명 교체 수량 축소 (50%)",
                    "description": "직접 입력한 LED 교체 수량을 50% 축소하여 필수 구역만 우선 교체합니다.",
                    "saved_cost": int(led_saving),
                    "performance_note": "미교체 구역의 조명 전력 절감 효과가 사라져 운영비 절감액이 줄어듭니다"
                })
            elif not led_reduction_active:
                recommendations.append({
                    "type": "led",
                    "title": "LED 조명 부분 교체 (공용구역 제외)",
                    "description": "계단실, 복도, 창고 등 공용 구역을 제외하고 주요 거주 구역 위주로 부분 교체합니다.",
                    "saved_cost": int(led_saving),
                    "performance_note": "공용 구역의 조명 전력 절감 효과는 제외되어 운영비 절감액이 줄어듭니다"
                })

        # ── 상향(성능 개선) 대안: kWh·운영비를 낮추는 방향 ──────────────────
        # 냉난방 설비 1등급 교체 (COP 향상). 이미 1등급 신형이 아니면 3등급(기본)도 제안 —
        # 3등급→1등급만으로 냉방 COP 3.3→4.0 (~20% 절감). 효과·회수기간은 재시뮬로 산출.
        is_old = cooling_grade in ("grade5", "old10", "old15") or heating_age in ("mid", "old")
        if (not hvac_upgraded) and (cooling_grade != "grade1" or heating_age != "new"):
            recommendations.append({
                "type": "hvac_upgrade",
                "direction": "upgrade",
                "title": ("노후 냉난방 설비 → 1등급 신형 교체" if is_old
                          else "냉난방 설비 1등급 고효율 교체"),
                "description": "현재 설비보다 효율(COP)이 높은 1등급 신형으로 교체해 냉난방 에너지를 줄입니다. "
                               "설비 교체비는 공사비에 이미 계상되어 있어(단가는 등급 무관 평균), "
                               "운영비 절감이 그대로 순이득이 됩니다.",
                "saved_cost": 0,
            })

        # 창호 상향: 일반/단층 → 고성능 Low-E 복층 (U≈1.3)
        if ('일반' in mapped_window_name or '단층' in mapped_window_name) and total_window_area > 0:
            prem_price = self.cost_db.get("window_tiers", {}).get("premium", {}).get("avg", 172610)
            added = int(total_window_area * prem_price - window_cost)
            recommendations.append({
                "type": "window_upgrade",
                "direction": "upgrade",
                "title": "창호 상향 (일반 → 고성능 Low-E 복층)",
                "description": "일반 복층유리를 고성능 Low-E+아르곤 복층(U≈1.3)으로 상향해 냉난방 손실을 줄입니다.",
                "saved_cost": 0,
                "added_cost": max(added, 0),   # 자재 단가 차액 추정 — 실공사비 변화는 impact가 대체
            })

        # 단열 상향: 일반/저성능 단열 부위 → 중성능(high, λ0.035)
        up_targets = [d for d in (detailed_insulation_costs or [])
                      if ('일반' in d["tier"] or '저성능' in d["tier"]
                          or 'standard' in d["tier"].lower() or 'basic' in d["tier"].lower())]
        if up_targets:
            high_price = self.cost_db.get("insulation_tiers", {}).get("high", {}).get("avg", 27000)
            added = sum(d["area"] * max(high_price - d["price"], 0) for d in up_targets)
            recommendations.append({
                "type": "insulation_upgrade",
                "direction": "upgrade",
                "title": "단열재 상향 (일반 → 중성능 등급)",
                "description": f"일반 등급 단열 부위 {len(up_targets)}곳을 중성능 단열재(λ 0.035)로 상향해 난방 손실을 줄입니다.",
                "saved_cost": 0,
                "added_cost": int(added),
            })

        return recommendations

    def _surface_outputs(self, df, surfaces):
        """면별 외피 온도/일사량과 창호 기류(월별 12개) 시계열 추출 — 3D 뷰어 오버레이용."""
        surface_thermal = {}
        surface_airflow = {}
        for s in surfaces or []:
            s_id = s['id'].upper()
            temp_col = rad_col = None
            win_id = f"WIN_{s['id']}".upper()
            flow1_col = flow2_col = None
            for col in df.columns:
                col_upper = col.upper()
                if col_upper.startswith(s_id + ":") or col_upper.startswith(s_id + "_MIRROR:"):
                    if 'SURFACE OUTSIDE FACE TEMPERATURE' in col_upper:
                        temp_col = col
                    elif 'SURFACE OUTSIDE FACE INCIDENT SOLAR' in col_upper:
                        rad_col = col
                elif col_upper.startswith(win_id + ":"):
                    if 'NODE 1 TO NODE 2 VOLUME FLOW RATE' in col_upper:
                        flow1_col = col
                    elif 'NODE 2 TO NODE 1 VOLUME FLOW RATE' in col_upper:
                        flow2_col = col

            temp_months, rad_months = [], []
            inflow_months, outflow_months = [], []
            for m in range(min(12, len(df))):
                temp_months.append(round(float(df.iloc[m][temp_col]) if temp_col else 20.0, 2))
                rad_months.append(round(float(df.iloc[m][rad_col]) if rad_col else 100.0, 2))
                inflow_months.append(round((float(df.iloc[m][flow1_col]) if flow1_col else 0.0) * 1000.0, 2))
                outflow_months.append(round((float(df.iloc[m][flow2_col]) if flow2_col else 0.0) * 1000.0, 2))

            surface_thermal[s['id']] = {"temperature": temp_months, "radiation": rad_months}
            surface_airflow[s['id']] = {"inflow": inflow_months, "outflow": outflow_months}

        return surface_thermal, surface_airflow

