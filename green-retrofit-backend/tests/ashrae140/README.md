# ASHRAE 140 (BESTEST) 벤치마크

우리 시뮬레이션 결과가 맞는지 판정할 **외부 기준**이다.
지금까지는 결과가 이상해 보일 때마다 후보를 손으로 하나씩 지워왔고
(면적 기준 → 지면 열손실 → 내부발열 → 기상 파일), 다 지우면 남는 게 없었다.
그 상태를 끝내려고 붙인다.

---

## 두 층으로 나뉜다

| | 무엇을 돌리나 | 우리 코드를 타나 | 무엇을 알 수 있나 |
|---|---|---|---|
| **Tier A** | 표준 케이스 IDF → EnergyPlus | **아니오** | 우리 EnergyPlus 설치·버전·기상 처리가 정상인가 |
| **Tier B** | 케이스를 우리 payload 로 → `generate_idf_and_simulate()` | 예 | 우리 gbXML→IDF 번역이 맞는가 |

**Tier A 는 Tier B 의 대조군이다.** Tier A 가 통과하는데 Tier B 가 실패하면
결함은 우리 번역 계층에 있다는 게 확정된다. 지금은 Tier A 만 구현돼 있다.

현재 구현: `test_tier_a_engine.py` (케이스 600, 연간 난방·냉방)

---

## 출처와 라이선스

| 파일 | 출처 |
|---|---|
| `stock_idf/case600.idf` | [NREL/BESTEST-GSR](https://github.com/NREL/BESTEST-GSR) `integration_testing/workflow/workflow_resources/case_en_600.idf` (v9.3) 를 25.2 로 버전 전이 |
| `weather/725650TYCST.epw` | 같은 저장소 `shared_resources/` — Denver-Stapleton, ASHRAE 140 5.2절 지정 기상 |
| `reference/std140_annual_loads.csv` | `results/resources/RESULTS5-2A.xlsx` 표 B8-1·B8-2 에서 추출 |
| `reference/nrel_energyplus_25_2.csv` | `results/historical/OpenStudio_3_11_0.csv` — **NREL 이 EnergyPlus 25.2.0 으로 낸 값** |
| `reference/BESTEST-GSR-LICENSE.md` | 재배포 조건 (BSD 계열, 저작권 고지 유지 의무) |

⚠️ **ASHRAE Standard 140 표준 본문은 유료다.** 여기 있는 건 NREL 이 공표한
입력파일과 결과값이지 표준 문서 내용이 아니다. 라이선스 조항 (4)에 따라
수정본을 원래 명칭으로 부르면 안 된다.

기준값 CSV 는 **커밋된 것이 정본**이다. 테스트가 xlsx 를 직접 읽지 않는 이유는
배포본이 갱신되면 기준값이 조용히 바뀌어 어제 통과하던 시험이 오늘 실패하기
때문이다. 재생성이 필요하면:

```bash
git clone --depth 1 https://github.com/NREL/BESTEST-GSR.git
python extract_reference.py <BESTEST-GSR 경로>
```

---

## 실행

```bash
cd green-retrofit-backend
../.venv/bin/python -m pytest tests/ashrae140/ -v      # 약 2초
../.venv/bin/python -m pytest -m "not slow"            # 벤치마크 제외
```

케이스 하나가 **약 1초**다(단일 존 연간). 느려서 뺄 이유는 없지만,
EnergyPlus 가 없는 환경에서는 자동 skip 된다.

---

## 결과 (2026-08-02, EnergyPlus 25.2.0, Timestep 4)

| 항목 | 우리 | 공표 범위 (6종) | EnergyPlus 제출값 | NREL 25.2.0 |
|---|---|---|---|---|
| 케이스 600 난방 | **4.2201 MWh** | 3.993 ~ 4.504 ✅ | 4.324 | 4.325 (−2.4%) |
| 케이스 600 냉방 | **6.2592 MWh** | 5.432 ~ 6.162 ❌ | 6.027 | 6.042 (+3.6%) |

---

## 알려진 편차 — 반드시 읽을 것

**케이스 600 냉방이 공표 상한을 약 1.6% 초과한다.** 시험에서 `xfail` 로 표시해
뒀다. 통과하도록 허용오차를 늘리지 않았다 — **통과하게 맞춘 벤치마크는 가치가
없기 때문이다.**

조사한 것:

- **케이스 사양은 전부 일치한다.** 내부발열 200 W(잠열 0 / 복사 0.6),
  침기 0.5 ACH, 설정온도 20/27℃, 지면온도 10℃ 상수,
  남향 창 3 m × 2 m 두 짝(12 ㎡), `FullInteriorAndExterior`.
- **타임스텝으로 설명되지 않는다.** 1·4·6·12·60 을 전부 돌려봤다:

  | Timestep | 난방 | 냉방 |
  |---|---|---|
  | 1 | 3.9415 | 5.9651 |
  | 4 | 4.2201 | 6.2592 |
  | 6 | 4.2448 | 6.2895 |
  | 12 | 4.2652 | 6.3147 |
  | 60 | 4.2821 | 6.3348 |

  NREL 의 난방 4.325 는 **우리 전 구간보다 높고**, 냉방 6.042 는 낮은 쪽에 있다.
  단조 관계가 아니라 타임스텝 하나로는 맞출 수 없다.

- **엔진은 같다(둘 다 25.2.0).** 따라서 차이는 **모델(IDF)에 있다.**
  우리 stock IDF 는 OpenStudio 9.3 세대 산출물을 버전 전이한 것이고,
  NREL 값은 OpenStudio 3.11 measure 가 OSM 에서 새로 생성한 모델이다.
  "더 많은 난방 + 더 적은 냉방"은 NREL 모델의 열손실이 더 크거나
  일사 취득이 더 작다는 뜻인데, 어느 쪽인지는 아직 특정하지 못했다.

**결론: 지금 Tier A 는 "엔진이 그럴듯하게 돈다"까지만 보증한다.**
엄격한 합격/불합격 관문으로 쓰려면 stock IDF 출처를 먼저 정리해야 한다.

### 해소 방법 (다음 작업)
OpenStudio CLI 를 설치하고 BESTEST-GSR measure 로 케이스를 **정식 생성**하면
버전 전이 경로가 통째로 사라져 NREL 값과 직접 대조할 수 있다.
비용은 OpenStudio CLI 의존성(약 1 GB)이다. 그 전까지는 공표 범위 대조만 유효하다.

---

## 이 벤치마크가 답해주지 않는 것

용호동 난방/냉방 비율(6.6~7.0 vs 19.9~20.7 kWh/㎡·년) 문제를 **직접 풀어주지는
않는다.** 5.2절은 외피 열전도·일사 취득·침기를 격리해서 볼 뿐이고,
케이스에는 현실적인 내부발열 스케줄도 PTHP 도 다중 존도 급탕도 없다.

다만 갈림길은 만들어 준다 — **통과하면 외피를 용의선상에서 지우고
내부부하·HVAC 로 넘어갈 수 있고, 실패하면 원인이 외피라는 게 확정된다.**
그것이 후보를 손으로 하나씩 지우는 것보다 낫다.

---

## 다음 단계

1. **stock IDF 출처 정리** — OpenStudio CLI 도입 여부 판단 (위 「해소 방법」)
2. **케이스 확장** — 610·620·630·640·650·900·910·920·930.
   기준값 CSV 에 92행이 이미 들어있어 IDF 만 확보하면 된다.
3. **케이스 간 델타 검사** — 600→900(열용량), 600→610(차양), 600→620(창 방위).
   델타는 기상·단위·절대 스케일에 둔감하고 **물리 번역만 직접 때리므로**
   우리한테는 절대값보다 예민한 지표다. 표준도 델타 범위를 공표한다.
4. **Tier B** — 케이스를 우리 payload 로 표현. 먼저 막힌 곳을 뚫어야 한다:
   - 🔴 `idf_builder.py:317` IdealLoads 가 `DesignSpecification:OutdoorAir` 를
     항상 물고 있다. **ASHRAE 140 은 기계환기 0, 침기만이다.**
     습도제어 필드도 비어 있어 `ConstantSensibleHeatRatio` 로 기본 적용된다(140 은 잠열 없음).
   - 🔴 `ep_simulator.py:188` `get_scaled_window_vertices()` 가 벽을 중앙 스케일해
     창을 만든다. 케이스 600 의 3 m × 2 m 두 짝을 정확히 표현할 수 없다.
   - 🔴 `idf_builder.py:94,164` `SolarDistribution` 이 `FullExterior` 고정인데
     **케이스 600 은 `FullInteriorAndExterior` 다.**
   - 🟡 `ep_simulator.py:1242` 가 `add_infiltration()` 을 인자 없이 부른다
     (기본 0.5 ACH 라 600·900 시리즈와 우연히 맞지만 케이스별 조정 불가).
   - 🟡 `ep_simulator.py:853~` 기상 파일이 자동 탐색이라 강제 지정 경로가 없다.
     **BESTEST EPW 를 `_data/weather/` 에 두면 안 된다** — 한국 프로젝트가
     Denver 를 집을 수 있다. 그래서 이 디렉터리 안에 따로 두었다.
