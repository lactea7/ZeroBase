# 태양광 발전량 산정 — 문헌 조사 요약 (2026-08-02)

우리 코드는 `pvCapacity(kW) × 1,300 kWh/kW` 로 연간 발전량을 잡는다.
"명판 용량만큼 나온다"는 가정이 현실과 얼마나 벌어지는지, 기울기·방위가
얼마나 영향을 주는지 문헌으로 확인한 결과다.

> ⚠️ 아래 수치는 웹 검색으로 수집한 것이라 **원문 대조를 거치지 않은 항목이 섞여 있다.**
> 코드에 반영하기 전에 출처 원문에서 조건(위도·기상·손실 가정)을 확인할 것.

---

## 1. 명판 용량 ≠ 실제 발전 — 손실 항목

### PVWatts 기본 시스템 손실 14%
개별 손실을 **곱셈으로 결합**한 값이다(합이 아니다).

| 항목 | 기본값 |
|---|---|
| 오염(soiling) | 2% |
| 음영(shading) | 3% |
| 눈(snow) | 0% |
| 미스매치 | 2% |
| 배선 | 2% |
| 접속부 | 0.5% |
| 광유도열화(LID) | 1.5% |
| 명판 정격 오차 | 1% |
| 노후 | 0% |
| 가용률(availability) | 3% |

### 온도 손실 — 우리 코드에 아예 없다
- 25℃ 초과 시 **℃당 0.3~0.4%** 출력 감소
- 실제 모듈 온도는 여름에 55~65℃ 도달 → 첨두 대비 **8~12% 손실**
- 한 실측에서 셀 온도 64℃일 때 일평균 효율 12.0% 저하, 출력 9.6% 감소

### 성능비(PR) — 종합 지표
- 독일 100개 시스템 실측: **70~90%, 중앙값 84%**
- PR 0.82 = STC 이론값의 82%만 계통에 전달

### 열화 — 20년 LCC 인데 우리는 0% 가정
- NREL 다수 시스템 분석 **중앙값 연 0.5%** → 25년 후 초기 대비 약 88%
- 프리미엄 단결정은 연 0.25~0.3%
- 우리 20년 LCC 기준으로 정확히 쓰면:
  - **20년차 순간 출력**은 초기 대비 약 **9%** 낮다
  - **20년 누적 발전량**은 무열화 대비 약 **4.6%** 낮다 (평균계수 ≈ 0.954)
  - 즉 "20년 누적 10% 과대"가 아니라 "20년차 9% / 누적 4~5% 과대"가 맞다
    (내가 처음 쓴 10% 는 순간 출력과 누적을 혼동한 것 — codex 검토에서 정정)

### 오염
- 단기 최대 30%, 월 최대 약 20%
- 표면의 0.5%만 가려도 9% 출력 손실 사례 (불균일 오염은 미스매치까지 유발)

---

## 2. 기울기·방위 민감도

### 방위(azimuth) — 생각보다 관대하다
| 최적 대비 편차 | 연간 손실 |
|---|---|
| ±15° | **1% 미만** |
| ±30° | **4% 미만** (마드리드 3.03% / 베를린 3.57%) |

### 경사(tilt)
| 최적 대비 편차 | 연간 수확량 |
|---|---|
| ±10° | 99% 유지 |
| ±15° | 2.5~3.0% 손실 |
| ±30° | 97% |
| ±60° | **88~89%** |

### 결합
경사 ±15° + 방위 ±30° 까지는 **5% 미만** 손실. 실무 시공 오차 범위는 관대하다.

### 수직 설치(BIPV 파사드) — 여기서 크게 벌어진다
- 최적 경사 지붕 대비 **20~35% 감소** (연구에 따라 50~70% 감소 보고도 있음 — 편차가 크다)
- 중부유럽(위도 ~50°) 남향 수직 = 최적 경사 지붕의 **약 60~70%**
- 위도 35~50°N 상업건물: 남향 불투명 BIPV 파사드 **120~180 kWh/㎡·년**
  vs 최적 경사 지붕 **180~250 kWh/㎡·년**
- 원인은 주로 입사각 코사인 손실

---

## 3. 한국 특이값

### 최적 배치 (80개 지점 × 약 260만 회 시뮬레이션)
- **최적 방위 176~184°** (거의 정남)
- **최적 경사 30~36°**
- 최적 경사와 위도·경도 사이에 강한 양의 상관

### 설비이용률
- 한국 일반 고정식: **연 1,200~1,400시간, 이용률 14~16%**
- 1kW 시스템 연간 약 1,000~1,500 kWh

### 우리 코드의 1,300 은?
**최적 배치 기준 한국 평균으로는 타당한 값이다.** 문제는 그것을 **배치와 무관하게**
적용한다는 점이다. 위 민감도를 곱하면:

| 배치 | 1,300 기준 현실적 값(추정) |
|---|---|
| 남향 30° 지붕 (최적) | ~1,300 |
| 남향 15° 또는 45° | ~1,260~1,270 |
| 동/서향 경사 | ~1,000~1,170 |
| **남향 수직 파사드** | **~780~1,040** |
| **북향 수직** | 문헌 범위 밖 — 현재 코드는 **50% 이상 과대 가능** |

여기에 열화(20년 평균 약 5% 추가 손실)와 온도·오염을 이미 1,300 에 포함된 것으로 볼지
별도로 뺄지는 **1,300 의 출처 정의를 확인해야** 결정할 수 있다. 지금 코드에는 그 정의가 없다.

---

## 4. 코드에 시사하는 것

1. **1,300 을 상수로 쓰는 한 배치 비교가 불가능하다.** 남향 30°와 북향 수직이 같은 값을 낸다.
2. **명시적 손실 모델이 없다.** ("손실이 하나도 없다"는 부정확하다 — 1,300 이 순 AC
   발전량 경험계수라면 손실이 암묵적으로 들어 있을 수 있다. 그래서 **1,300 의 출처를
   확정하기 전에는 14% 나 온도 8~12% 를 추가로 곱하면 안 된다** — 이중계산이다.)
3. **20년 LCC 인데 열화가 0%다.** 연 0.5% 면 20년차 9% / 20년 누적 4~5% 과대다.
   평균계수 한 번 곱하기가 아니라 `gen_y(t) = gen_1(t)·(1-d)^(y-1)` 로 **연차별** 적용해야
   할인 가중·자가소비 경계·요금상승과 맞물린다.
4. **범주 차이가 미세조정보다 크다.** 남향 주변 ±15~30° 편차는 작지만 남/북 범주 차이는
   경사 미세오차보다 훨씬 크다. UI 는 ① 설치형태(평지붕랙·경사지붕·벽면) ② 방위 범주
   (남/동서/북) ③ 경사 프리셋 순으로 받고, 정확한 각도는 고급 설정에 둔다.
5. **PVWatts 기본 14% 에는 온도와 인버터가 안 들어 있다.** 온도는 모듈온도 모델이,
   인버터는 `ElectricLoadCenter:Inverter:PVWatts` 가 따로 계산한다. 14% 는 모델이 명시적으로
   계산하지 않는 항목만 곱셈 결합한 값(정확히는 약 14.08%)이다. age loss 는 0% 로 두고
   열화는 LCC 에서만 적용한다.
6. **PV 공사비·점검/세척·인버터 교체비가 LCC 에 아예 없다.** 현재 자본비는 창호·단열·
   LED·HVAC 만 합산한다. 열화율보다 이쪽이 더 큰 오류다 — 이 상태로 PV 투자회수기간을
   표시하면 안 된다.
7. `pdfReport.js:436` 의 `(연 … kWh 자가소비)` 표기가 틀렸다. `pvCapacity * 1300` 은
   **잠재 총발전량**이고 자가소비량은 시간별 `min(부하, 발전)` 의 합이다. 지금은 잉여를
   버리면서 전량을 "자가소비"로 표시한다.

---

## 출처

- [European Photovoltaic Atlas: Technology-Specific Yield Analysis by Tilt and Azimuth (MDPI Buildings 2026)](https://www.mdpi.com/2075-5309/16/3/553)
- [The effect of orientation and tilt angle on PV system energy production in Hungary (Discover Sustainability 2025)](https://link.springer.com/article/10.1007/s43621-025-02082-z)
- [World estimates of PV optimal tilt angles (Jacobson & Jadhav, Stanford)](https://web.stanford.edu/group/efmh/jacobson/Articles/I/TiltAngles.pdf)
- [An experimental study on determination of optimal tilt and orientation angles in photovoltaic systems (ScienceDirect)](https://www.sciencedirect.com/science/article/pii/S2307187724002086)
- [Optimal Photovoltaic Panel Direction and Tilt Angle Prediction Using Stacking Ensemble Learning (Frontiers in Energy Research 2022)](https://www.frontiersin.org/journals/energy-research/articles/10.3389/fenrg.2022.865413/full)
- [한국신재생에너지학회 논문 (journalksnre.com)](https://journalksnre.com/_common/do.php?a=full&b=12&bidx=1386&aidx=14258)
- [PVWatts Version 5 Manual (NREL)](https://pvwatts.nrel.gov/downloads/pvwattsv5.pdf)
- [Perspective: Performance Loss Rate in Photovoltaic Systems (NREL 2023)](https://docs.nrel.gov/docs/fy23osti/85463.pdf)
- [Experimental analysis of elevated temperature and soiling loss on rooftop PV modules (Scientific Reports 2025)](https://www.nature.com/articles/s41598-025-25846-z)
- [Comprehensive analysis of energy and visual performance of BIPV in all ASHRAE climate zones (ScienceDirect)](https://www.sciencedirect.com/science/article/abs/pii/S0378778824004857)
- [Understanding Solar Photovoltaic System Performance (US DOE)](https://www.energy.gov/sites/default/files/2022-02/understanding-solar-photo-voltaic-system-performance.pdf)
- [신재생에너지센터 지역별 발전량 통계 (한국에너지공단)](https://www.knrec.or.kr/biz/statistics/supply/supply02_02_list.do)
