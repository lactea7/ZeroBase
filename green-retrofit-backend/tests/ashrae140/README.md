# ASHRAE 140 (BESTEST) 벤치마크

우리 시뮬레이션 결과가 맞는지 판정할 **외부 기준**이다.
지금까지는 결과가 이상해 보일 때마다 후보를 손으로 하나씩 지워왔고
(면적 기준 → 지면 열손실 → 내부발열 → 기상 파일), 다 지우면 남는 게 없었다.
그 상태를 끝내려고 붙인다.

---

## ⚠️ 먼저: 이것은 ASHRAE 140 합격시험이 아니다

여기 있는 건 **격리된 참조모델 진단**이다. 표 B8 의 6종 min~max 범위는 원래
비교·진단용이고, **140-2020 Addendum b 이후 판본은 별도의 통계적 acceptance
criteria 와 테스트 그룹별 최소 통과 규칙을 따로 둔다** — 그건 구현돼 있지 않다.
"범위 안에 들었다"를 "표준에 합격했다"로 읽으면 안 된다.

정식 관문을 주장하려면 적용 판본, Normative Annex 범위, 테스트 그룹과 최소 통과
개수를 구현해야 한다. ([ASHRAE Standard 140 리소스](https://data.ashrae.org/standard140/) ·
[140-2020 Addendum b](https://www.ashrae.org/file%20library/technical%20resources/standards%20and%20guidelines/standards%20addenda/140_2020_b_20230131.pdf))

---

## 두 층으로 나뉜다

| | 무엇을 돌리나 | 우리 코드를 타나 |
|---|---|---|
| **Tier A** | 표준 케이스 IDF → EnergyPlus | **아니오** |
| **Tier B** | 케이스를 우리 payload 로 → `generate_idf_and_simulate()` | 예 |

**Tier A 가 확인하는 것**
- 격리된 IDF/EPW 를 EnergyPlus 실행파일이 정상 실행하는가
- SQL 에서 연간 부하를 읽어낼 수 있는가
- 그 값이 과거 여러 프로그램 결과와 대체로 비슷한가
- 실제로 실행된 엔진이 기준값 CSV 와 같은 버전인가 (SQL `Simulations` 에서 검증)

**Tier A 가 확인하지 않는 것**
- 우리 `IdfBuilder` · `generate_idf_and_simulate()` · gbXML 변환
- `ep_simulator.py` 의 기상 파일 탐색 — **애플리케이션 기상 처리는 전혀 타지 않는다**
- 한국 프로젝트의 기상 선택

**존재 이유는 Tier B 의 대조군이다.** Tier A 가 정상인데 Tier B 가 실패하면
원인을 우리 번역 계층 쪽으로 좁힐 수 있다. 지금은 Tier A 만 구현돼 있다.

현재 구현: `test_tier_a_engine.py` (케이스 600, 연간 난방·냉방)

| 시험 | 성격 |
|---|---|
| `test_within_reference_program_range` | 비교 프로그램 6종 범위 대조 (합격 판정 아님) |
| `test_recorded_value_regression` | 관측값 ±0.5% — **회귀 감지**. 범위 시험이 xfail 인 항목도 여기선 실패한다 |
| `test_against_nrel_generated_model_diagnostic` | NREL 생성모델과의 근접도 — **진단용, 관문 아님** |

---

## 출처와 라이선스

| 파일 | 출처 |
|---|---|
| `stock_idf/case600.idf` | [NREL/BESTEST-GSR](https://github.com/NREL/BESTEST-GSR) `integration_testing/workflow/workflow_resources/case_en_600.idf` (**EnergyPlus 9.3** 판) 을 IDFVersionUpdater 로 25.2 전이 |
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
  우리 stock IDF 는 **EnergyPlus 9.3** 판 IDF 를 버전 전이한 것이고,
  NREL 값은 OpenStudio 3.11 measure 가 OSM 에서 새로 생성한 모델이다.

**원인은 아직 좁혀지지 않았다.** "일사 취득 과다 또는 외피 열손실 과소"는 가능한
가설일 뿐이고, 내부발열이나 침기 열교환 차이도 같은 방향(난방↓·냉방↑)을 만든다.

가장 빠른 판별은 **두 IDF 의 객체별 비교**다. 확인 순서:
1. 창 유리의 U-factor·SHGC·가시광 투과율과 각도 의존 특성
2. 창 면적뿐 아니라 좌표, 프레임/디바이더, 외부 차양
3. `SolarDistribution` 과 내부 표면 태양분배
4. 벽·지붕·바닥의 층 순서, 열전도율, 밀도, 비열, 두께
5. 침기 ACH 뿐 아니라 온도·풍속 계수와 스케줄
6. 외부/내부 대류 알고리즘, 지형 및 풍속 노출
7. 지면 경계와 10℃ 적용 방식
8. 내부발열의 복사/대류 분율과 스케줄
9. 존 체적 및 공기 열용량
10. IdealLoads 의 잠열·환기·제어 설정

출력을 늘려(월별 난방·냉방, 시간별 창 입사·투과 일사, 표면 전도열, 침기 현열,
존 내부 대류·복사 이득) 비교하면 원인이 분리된다. **무창 케이스나 600→620/610
델타가 있으면 일사 원인인지 훨씬 빨리 판별된다.**

**결론: 지금 Tier A 는 "격리된 IDF 를 엔진이 정상 실행하고 결과가 그럴듯하다"까지만
보증한다.** 관문으로 쓰려면 stock IDF 출처를 먼저 정리해야 한다.

### 해소 방법 (다음 작업)
BESTEST-GSR measure 로 케이스를 **정식 생성**하면 버전 전이 경로가 사라져
NREL 값과 직접 대조할 수 있다. **OpenStudio CLI 를 런타임·CI 의존성으로 둘 필요는
없다** — 별도 환경에서 한 번 생성해 IDF 와 provenance 를 커밋하고, 평상시 시험은
생성된 IDF 만 실행하면 된다. 재생성 스크립트와 버전 정보만 문서로 남긴다.

정식 IDF 를 확보하면 `test_against_nrel_generated_model_diagnostic` 의 허용오차를
반올림 수준으로 좁히고 관문으로 승격할 수 있다 — 같은 엔진·같은 모델이므로
결과가 거의 동일해야 하기 때문이다.

---

## 이 벤치마크가 답해주지 않는 것 — 기대를 정확히 잡을 것

용호동 난방/냉방 비율(6.6~7.0 vs 19.9~20.7 kWh/㎡·년) 문제에 대해:

- **Tier A 통과**: 우리 애플리케이션 외피 구현에 관해 **아무것도 지우지 못한다.**
  stock IDF 가 엔진에서 실행됐을 뿐이다.
- **Tier B 케이스 600 하나 통과**: 단순 상자에서 외피·일사·침기 번역이 대체로
  맞다는 증거는 되지만, **보상오차 때문에 외피 전체를 용의선상에서 지울 수 없다.**
- **600·610·620·630·640·650·900 + 케이스 간 델타까지 통과**: 그제서야 외피 전도,
  열용량, 창 일사, 차양, 방위 번역을 상당히 강하게 검증했다고 말할 수 있다.

반대로 **Tier B 실패가 곧 "원인은 외피"라는 뜻도 아니다.** 기상 강제, 내부발열,
IdealLoads 제어, 출력 집계, benchmark payload 변환 중 무엇이든 원인일 수 있다.

정확히 쓰면 이렇다:

> Tier B 의 관련 케이스와 민감도 델타가 통과하면 단순 외피·일사·침기 번역의
> 가능성을 낮추고, 용호동의 활동 스케줄·내부부하·HVAC·다중존 경계로 조사 범위를
> 옮길 근거가 된다.

---

## 다음 단계

1. **stock IDF 출처 정리** (위 「해소 방법」) — 이걸 먼저 해야 나머지가 의미를 가진다
2. **케이스 확장** — 610·620·630·640·650·900·910·920·930.
   기준값 CSV 에 92행이 이미 들어있어 IDF 만 확보하면 된다.
3. **케이스 간 델타 검사** — 600→900(열용량), 600→610(차양), 600→620(창 방위).
   델타는 기상·단위·절대 스케일에 둔감하고 **물리 번역만 직접 때리므로**
   우리한테는 절대값보다 예민한 지표다. 표준도 델타 범위를 공표한다.

### 4. Tier B — 막힌 곳을 순서대로 뚫어야 한다

**① benchmark configuration 경로 신설** — 기상 파일, timestep, `SolarDistribution`,
대류/열수지 알고리즘, RunPeriod, warmup 을 **강제할 수 있어야 한다.**
지금은 어느 것도 외부에서 못 정한다. 나머지가 전부 여기에 얹힌다.
⚠️ benchmark 용 예외가 **일반 사용자 경로의 기본값을 바꾸지 않도록** 분리할 것.

**② HVAC/외기/습도제어 분리** — `idf_builder.py:305-322` 의 IdealLoads 가
`DesignSpecification:OutdoorAir` 에 0 이 아닌 외기를 항상 넣는다.
**ASHRAE 140 은 기계환기 0, 침기만이다.** 습도제어 필드도 공란이라
`ConstantSensibleHeatRatio` 가 기본 적용된다(140 은 잠열 없음).
"외기 없음"과 "잠열 없음"을 명시할 수 있어야 한다.

**③ 내부발열·스케줄의 정확한 표현** — 현재 activity 기반 인원·조명·기기·DHW
자동값으로는 BESTEST 의 **고정 200 W 와 복사 0.6 / 대류 0.4 / 잠열 0** 을 정확히
표현하기 어렵다. 자동 DHW·활동 스케줄·설비 기본값을 **비활성화하는 방법**이 필요하다.

**④ 재료·구성·표면 경계조건** — BESTEST 의 열용량과 전도 특성을 payload 로 손실
없이 전달해야 한다. **600→900 의 핵심이므로 창 형상보다 먼저** 확인할 것.

**⑤ 침기 ACH 와 계수 명시화** — `ep_simulator.py:1242` 가 `add_infiltration()` 을
인자 없이 부른다. 기본 0.5 ACH 가 600·900 시리즈와 **우연히** 맞을 뿐이다.

**⑥ 명시적 opening geometry** — `ep_simulator.py:188` 의 WWR 중앙 스케일로는
3 m × 2 m 두 짝과 차양 케이스를 표현할 수 없다. gbXML opening 좌표를 보존하는
경로와 WWR 생성 경로를 **구분**해야 한다.

**그 밖에 확인 필요**: 대류/heat-balance 알고리즘, timestep·warmup·수렴 설정,
표면 일사·바람 노출 플래그, 월별/연간 출력변수의 정확한 의미와 SQL 집계.

⚠️ **BESTEST EPW 를 `_data/weather/` 에 두면 안 된다** — `ep_simulator.py:853~`
자동 탐색이 한국 프로젝트에 Denver 를 물릴 수 있다. 그래서 이 디렉터리 안에 두었다.
