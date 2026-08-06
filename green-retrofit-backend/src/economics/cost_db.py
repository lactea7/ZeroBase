"""공사비 단가 DB — 파일 I/O·정제·등급 분류·단가 매칭.

`LCCAnalyzer` 에 섞여 있던 것을 옮겼다. 순수 이동이며 계산식을 바꾸지 않았다.

여기 오면 안 되는 것: 에너지 계산, 현금흐름, 권고. 이 모듈은 **"자재가 얼마인가"**
하나만 답한다.

⚠️ DB 값이 상식 범위를 벗어나면 클램프하고 `load_warnings` 에 남긴다.
조용히 보정하면 오매핑이 재발해도 아무도 모른다.
"""
import os
import re
import statistics

try:
    import pandas as pd
except ImportError:      # pandas 없이도 import 는 되게 (calculate 에서 명확히 실패시킨다)
    pd = None


class CostDatabase:
    """공사비 단가 조회. 생성 시 CSV 를 읽어 등급별 단가를 준비한다."""

    # 공종별 단가 타당성 범위 (원). DB 추출값이 벗어나면 클램프 + 경고 → 오매핑 재발 방지.
    PRICE_BOUNDS = {
        "window_m2":     (50_000, 600_000),   # 창호(창세트) ₩/㎡
        "insulation_m2":  (3_000, 120_000),   # 단열재 ₩/㎡ (EPS 100mm 실거래 ~4천원대)
        "led_ea":        (20_000, 500_000),   # LED 등기구 ₩/개
    }

    # 두께당(T=1㎜) 단가로 등재된 단열재의 ㎡ 환산 기준 두께.
    # (EPS류가 '비드법 2종 1호(T=1㎜) 109원/㎡'식으로 등재됨 → ×100mm = 10,900원/㎡)
    STD_INSUL_THICKNESS_MM = 100

    def __init__(self, db_dir: str):
        self.db_dir = db_dir
        # DB 로드 중 품질 이슈(가드 발동 등) — 소비자가 사용자 경고로 노출한다
        self.load_warnings = []
        self.cost_db = self._load_cost_db()

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

