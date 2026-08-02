# ASHRAE 140 (BESTEST) 벤치마크

우리 시뮬레이션 결과가 맞는지 판정할 **외부 기준**이다.
지금까지는 결과가 이상해 보일 때마다 후보를 손으로 하나씩 지워왔고
(면적 기준 → 지면 열손실 → 내부발열 → 기상 파일), 다 지우면 남는 게 없었다.
그 상태를 끝내려고 붙인다.

---

## ⚠️ 먼저: 이것은 ASHRAE 140 합격시험이 아니다

여기 있는 건 **참조모델 재현 확인**이다. 표 B8 의 6종 min~max 범위는 원래
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
- NREL 이 같은 조합(OpenStudio 3.11 + EnergyPlus 25.2.0)으로 낸 값을 재현하는가
- 그 값이 공표된 비교 프로그램 범위 안에 드는가
- **케이스 간 델타**(열용량·차양·창 방위 등)가 비교 프로그램들의 델타 범위 안에 드는가
- 실제로 실행된 엔진이 기준값과 같은 버전인가 (SQL `Simulations` 에서 검증)

**Tier A 가 확인하지 않는 것**
- 우리 `IdfBuilder` · `generate_idf_and_simulate()` · gbXML 변환
- `ep_simulator.py` 의 기상 파일 탐색 — **애플리케이션 기상 처리는 전혀 타지 않는다**
- 한국 프로젝트의 기상 선택

**Tier A 는 Tier B 의 대조군이다.** Tier A 가 정상인데 Tier B 가 실패하면
원인을 우리 번역 계층 쪽으로 좁힐 수 있다.

### 시험 구성

**Tier A** (`test_tier_a_engine.py`) — 케이스 19종 × 2지표

| 시험 | 성격 | 개수 |
|---|---|---|
| `test_reproduces_nrel_reference_run` | **주 관문.** NREL 25.2.0 값 대비 ±0.5% | 38 |
| `test_within_reference_program_range` | 비교 프로그램 6종 범위 (합격 판정 아님) | 38 |
| `test_case_delta_within_program_range` | 케이스 간 델타 | 22 |

**Tier B** (`test_tier_b_pipeline.py`) — 케이스 4종. 케이스 정의는 `cases/bestest.py`

| 시험 | 성격 | 개수 |
|---|---|---|
| `test_case_matches_reference` | NREL 값 대비 ±1.0% | 8 |
| `test_case_delta_matches_reference` | **격리된 물리 효과** — 절대값보다 예민 | 6 |
| `test_benchmark_config_is_opt_in` | 벤치마크 설정이 사용자 기본값으로 새지 않는지 | 1 |

전체 **약 34초**.

---

## 결과 (2026-08-02, EnergyPlus 25.2.0)

**19케이스 38지표 전부 NREL 값을 ±0.4% 이내로 재현한다** (최대 편차 0.39%, 케이스 640 난방).
범위 이탈 3건은 아래 「알려진 범위 이탈」 참조.

| 케이스 | 난방 | 냉방 | | 케이스 | 난방 | 냉방 |
|---|---|---|---|---|---|---|
| 600 | 4.3247 | 6.0441 | | 900 | 1.6612 | 2.4982 |
| 610 | 4.3750 | 4.3466 | | 910 | 1.9528 | 1.3895 |
| 620 | 4.4828 | 4.0742 | | 920 | 3.3315 | 2.7407 |
| 630 | 4.7800 | 2.8470 | | 930 | 3.9884 | 1.9271 |
| 640 | 2.6685 | 5.7804 | | 940 | 1.0669 | 2.4335 |
| 650 | 0 | 4.8435 | | 950 | 0 | 0.6959 |
| 660 | 3.7065 | 3.2437 | | 985 | 2.3671 | 6.3741 |
| 670 | 5.6147 | 6.6404 ❌ | | 995 | 0.9997 | 7.2228 |
| 680 | 2.1790 | 6.4579 | | | | |
| 685 | 4.8762 | 9.1326 ❌ | | | | |
| 695 | 2.8012 | 9.1830 ❌ | | | | |

### 알려진 범위 이탈 (3건, `xfail(strict=True)`)

670·685·695 의 **냉방**이 공표 상한을 0.03~0.3% 초과한다.
셋 다 **EnergyPlus 자체가 밴드 최상단인 케이스**다:

| 케이스 | EnergyPlus 제출값 | 공표 상한 | 우리 |
|---|---|---|---|
| 670 냉방 | 6.623 | 6.6227 | 6.6404 |
| 685 냉방 | 9.119 | 9.130 | 9.1326 |
| 695 냉방 | 9.172 | 9.1716 | 9.1830 |

즉 상한을 EnergyPlus 가 직접 정하고 있어서, **NREL 값을 0.1% 미만으로 재현해도
상한을 살짝 넘는다.** 우리 설정 결함이 아니다. 허용오차를 늘려 통과시키지 않고
`xfail(strict=True)` 로 남겼다 — 해소되면 XPASS 로 알려준다.

---

## 출처와 라이선스

| 파일 | 출처 |
|---|---|
| `stock_idf/case*.idf` (19종) | [NREL/BESTEST-GSR](https://github.com/NREL/BESTEST-GSR) `bestest_building_thermal_envelope_and_fabric_load` measure 가 **정식 생성**. provenance 는 `stock_idf/PROVENANCE.txt` |
| `weather/725650TYCST.epw` | 같은 저장소 `shared_resources/` — Denver-Stapleton. **measure 가 이 파일명을 내부에 고정**하고 있다 |
| `reference/std140_annual_loads.csv` | `results/resources/RESULTS5-2A.xlsx` 표 B8-1·B8-2 의 min/max/mean |
| `reference/std140_by_program.csv` | 같은 표의 **프로그램별 원값** — 델타 범위를 직접 계산하는 데 쓴다 |
| `reference/nrel_energyplus_25_2.csv` | `results/historical/OpenStudio_3_11_0.csv` — NREL 이 EnergyPlus 25.2.0 으로 낸 값 |
| `reference/BESTEST-GSR-LICENSE.md` | 재배포 조건 (BSD 계열, 저작권 고지 유지 의무) |

⚠️ **ASHRAE Standard 140 표준 본문은 유료다.** 여기 있는 건 NREL 이 공표한
입력파일과 결과값이지 표준 문서 내용이 아니다. 라이선스 조항 (4)에 따라
수정본을 원래 명칭으로 부르면 안 된다.

기준값 CSV 는 **커밋된 것이 정본**이다. 테스트가 xlsx 를 직접 읽지 않는 이유는
배포본이 갱신되면 기준값이 조용히 바뀌어 어제 통과하던 시험이 오늘 실패하기 때문이다.

---

## 실행

```bash
cd green-retrofit-backend
../.venv/bin/python -m pytest tests/ashrae140/ -q      # 약 12초
../.venv/bin/python -m pytest -m "not slow"            # 벤치마크 제외
```

EnergyPlus 가 없는 환경에서는 자동 skip 된다.
**기준값과 다른 EnergyPlus 버전으로 실행하면 실패한다** — 비교가 무의미해지므로
조용히 통과시키지 않는다.

### 재생성 (평상시엔 필요 없다)

**OpenStudio 는 런타임·CI 의존성이 아니다.** 생성된 IDF 가 커밋돼 있고 테스트는
그것만 돌린다. EnergyPlus 버전을 올리거나 케이스를 추가할 때만:

```bash
# OpenStudio 3.11.0 (EnergyPlus 25.2.0 동봉) — tar.gz 라 시스템 설치가 필요 없다
curl -LO https://github.com/NatLabRockies/OpenStudio/releases/download/v3.11.0/OpenStudio-3.11.0%2B241b8abb4d-Darwin-arm64.tar.gz
tar xzf OpenStudio-3.11.0*.tar.gz
git clone --depth 1 https://github.com/NREL/BESTEST-GSR.git

./regenerate_stock_idf.sh ./OpenStudio-3.11.0+241b8abb4d-Darwin-arm64 ./BESTEST-GSR
python extract_reference.py ./BESTEST-GSR      # 기준값 CSV 도 함께
```

전체 재생성 약 100초(케이스당 약 5초).
EnergyPlus 를 올렸다면 `EXPECTED_EP_VERSION` 과 위 결과표도 함께 고칠 것.

---

## 이 벤치마크가 답해주지 않는 것 — 기대를 정확히 잡을 것

용호동 난방/냉방 비율(6.6~7.0 vs 19.9~20.7 kWh/㎡·년) 문제에 대해:

- **Tier A 통과**: 우리 애플리케이션 외피 구현에 관해 **아무것도 지우지 못한다.**
  표준 IDF 가 엔진에서 정확히 실행됐을 뿐이다.
- **Tier B 케이스 600 하나 통과**: 단순 상자에서 외피·일사·침기 번역이 대체로
  맞다는 증거는 되지만, **보상오차 때문에 외피 전체를 용의선상에서 지울 수 없다.**
- **Tier B 가 600·610·620·630·640·650·900 + 델타까지 통과**: 그제서야 외피 전도,
  열용량, 창 일사, 차양, 방위 번역을 상당히 강하게 검증했다고 말할 수 있다.

반대로 **Tier B 실패가 곧 "원인은 외피"라는 뜻도 아니다.** 기상 강제, 내부발열,
IdealLoads 제어, 출력 집계, benchmark payload 변환 중 무엇이든 원인일 수 있다.

정확히 쓰면 이렇다:

> Tier B 의 관련 케이스와 민감도 델타가 통과하면 단순 외피·일사·침기 번역의
> 가능성을 낮추고, 용호동의 활동 스케줄·내부부하·HVAC·다중존 경계로 조사 범위를
> 옮길 근거가 된다.

---

## Tier B 결과 (2026-08-02)

우리 payload → `generate_idf_and_simulate()` → EnergyPlus 전 경로.

| 케이스 | 난방 | 편차 | 냉방 | 편차 |
|---|---|---|---|---|
| 600 기준 | 4.3267 | +0.04% | 6.0424 | +0.01% |
| 620 창 방위 | 4.4856 | +0.05% | 4.0665 | −0.07% |
| 900 열용량 | 1.6681 | +0.42% | 2.5037 | +0.48% |
| 610 차양 | 4.3773 | +0.05% | 4.3472 | +0.06% |

**델타 (격리된 물리 효과)**

| 델타 | 난방 (우리 / NREL) | 냉방 (우리 / NREL) |
|---|---|---|
| 900−600 열용량 | −2.6586 / −2.6639 | −3.5387 / −3.5500 |
| 620−600 창 방위 | +0.1589 / +0.1583 | −1.9759 / −1.9723 |
| 610−600 차양 | +0.0507 / +0.0500 | −1.6952 / −1.6973 |

**주어진 입력이 정확하면 우리 번역 계층의 물리는 맞다.**
특히 900−600 이 맞는다는 것은 `layers` 가 열용량을 실제로 보존한다는 뜻이다 —
기존 U-value 합성 경로로는 600 과 900 이 같은 값을 냈다.

### 도달까지 세 번 틀렸다 — 그 과정이 결과보다 중요하다

1. **난방 +9% / 냉방 −35%** — 설정온도가 사무소 아키타입 스케줄(야간 16℃ setback +
   냉방기간 5~10월 마스크)로 만들어졌다. 존의 `heatingSetpoint`/`coolingSetpoint` 는
   스케줄 생성의 입력일 뿐 상시 값이 아니다. → `constantSetpoints`
2. **난방 +50%** — AirflowNetwork 때문.
3. **⚠️ AFN 이 켜지면 `ZoneInfiltration` 은 아예 시뮬레이션되지 않는다.**
   EnergyPlus 가 명시적으로 경고한다:
   *"Specified AirflowNetwork Control = MultizoneWithoutDistribution and
   ZoneInfiltration:* objects are present. ZoneInfiltration objects will not be simulated."*
   이중계산이 아니라 **대체**다. `add_infiltration(ach=...)` 은 AFN 이 켜진 존에서
   무시되고, 실제 침기는 `WallCrack` 계수(`setup_airflow_network` 의 0.01 / 0.65)가
   정한다. 케이스 600 에서 그 차이가 난방 4.33 → 6.50 MWh(**+50%**)였다.
   AFN 은 외기 접촉면 2개 이상인 존에 켜지므로 **사실상 거의 모든 존**이 해당한다.
   → **실제 프로젝트의 침기 가정이 코드 표기와 다르다. 별도 조사 항목.**

### 벤치마크 설정 (`payload["benchmark"]`)

**없으면 기존 사용자 경로와 100% 동일하게 동작한다.** 벤치마크는 실제 프로젝트에
적용하면 안 되는 값을 강제하므로 기본값으로 새면 안 된다 —
`test_benchmark_config_is_opt_in` 이 이 격리를 지킨다.

| 키 | 무엇을 강제하나 |
|---|---|
| `weatherFile` | 기상 파일 (자동 탐색 우회) |
| `timestep` · `minWarmupDays` | 시간 해상도·warmup |
| `solarDistribution` · `terrain` | 태양복사 분배·지형 |
| `insideConvection` · `outsideConvection` · `heatBalance` | 알고리즘 |
| `infiltrationAch` | 침기 ACH |
| `disableAirflowNetwork` | AFN off (위 3번) |
| `suppressAutoLoads` | 용도별 자동 부하·급탕·콘센트 억제 |
| `constantSetpoints` | 상시 고정 설정온도 |
| `forceIdealLoads` · `idealNoOutdoorAir` · `idealNoHumidityControl` | HVAC |
| `otherEquipment` | 고정 발열(`OtherEquipment`, 연료 None) |

### 파이프라인 표현력 확장

기존 payload 에 없는 키라 사용자 경로에는 영향이 없다.

- **`surface["layers"]`** — 층 구성을 바깥→안 그대로 생성. U-value 합성과 달리
  **열용량이 보존된다.** `Material:NoMass`(`thermalResistance`)도 지원.
- **`surface["glazingLayers"]`** — 상세 유리(`WindowMaterial:Glazing`/`Gas`).
  `SimpleGlazingSystem` 은 U/SHGC 만 맞추고 입사각 의존성이 달라 일사가 어긋난다.
- **`surface["boundaryCondition"/"sunExposure"/"windExposure"]`** — 140 의 바닥은
  `Outdoors` + `NoSun`/`NoWind` 인데 자동 추정으로는 나올 수 없는 조합이다.
- **`payload["shadingSurfaces"]`** — `Shading:Building:Detailed`(투과율 0).
  gbXML 파서는 아직 Shade 요소를 읽지 않는다.

---

## 남은 일

1. **케이스 확장** — 기준값 CSV 에 92행(케이스 46종)이 이미 있다.
   Tier A 는 `regenerate_stock_idf.sh` 와 `test_tier_a_engine.py` 의 `CASES` 에,
   Tier B 는 `cases/bestest.py` 의 `CASE_SPECS` 에 추가하면 된다.
   측면 케이스(195~320, 395~470, 960 sunspace, FF 자유부동)는 아직 없다.
2. **AFN 침기 조사** — 위 3번. 실제 프로젝트의 침기가 `WallCrack` 계수로
   결정되고 있다. 그 값이 타당한지, 사용자에게 어떻게 보여야 하는지 정해야 한다.
3. **gbXML Shade 파싱** — 지금은 payload 로만 차양이 들어온다.
4. **다중 존 케이스(960 sunspace)** — 존 간 경계 번역을 검증할 수 있다.

⚠️ **BESTEST EPW 를 `_data/weather/` 에 두면 안 된다** — `ep_simulator.py` 의
자동 탐색이 한국 프로젝트에 Denver 를 물릴 수 있다. 그래서 이 디렉터리 안에 두었다.
