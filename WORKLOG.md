# 작업 일지

> 세션이 바뀌어도 여기만 읽으면 **어디까지 했고 다음에 뭘 할지** 알 수 있게 유지한다.
> 최신 항목이 위로 온다. 각 세션 끝에 「다음 할 일」을 반드시 갱신할 것.

---

## 재시작 절차 (컴퓨터를 껐다 켠 뒤)

디스크에 남는 것: `scripts/` 도구 4종, 이 파일, codex CLI(`~/.local/bin/codex`)와
로그인(`~/.codex/auth.json`), ollama 모델. **다시 띄워야 하는 것은 아래뿐이다.**

```bash
# 1) cmux 레이아웃 복구 (4분할: Claude / 브라우저 / codex / ollama)
cmux restore-session

# 2) 백엔드 — 저장소 루트의 .venv 를 쓴다
cd green-retrofit-backend && ../.venv/bin/python -m uvicorn main:app --host 127.0.0.1 --port 8000

# 3) 프론트 — 반드시 5173 을 잡아야 한다 (ALLOWED_ORIGINS 기본값이 5173뿐)
cd green-retrofit-frontend && npm run dev

# 4) 브라우저 패널
cmux open http://localhost:5173
```

**패널 세션은 수동으로 다시 띄워야 한다.** 좌하단 터미널에서 `codex`,
우하단에서 `ollama run gemma4:e4b`. 이게 떠 있지 않으면 릴레이 스크립트의
패널 자동 탐지가 실패한다(탐지는 화면 내용으로 하므로 surface 번호가 바뀌어도 무방).

릴레이 사용법:
```bash
./scripts/relay-cmux.sh "무엇을 바꿨는지 브리핑"        # 코드 검토 (codex→ollama)
./scripts/ask-panels.sh --codex-only <질문파일.md>      # 자유 질문 교차검증
```
`.relay/` 는 gitignore 대상이라 재부팅 후 비어 있을 수 있다 — 라운드 카운터가
초기화될 뿐 문제 없다. 라운드 상한은 3.

**사라지는 것**: 실행 중이던 서버, 패널 세션, `/private/tmp` 의 스크래치패드
(EPlusSimple 클론, 이전 릴레이 기록 보관분). 전부 재생성 가능하다.
EPlusSimple 비교가 다시 필요하면:
`git clone --depth 1 --branch V0-6-3 https://github.com/snu-bslab/EPlusSimple.git`

---

## 운영 규칙

**Claude 또는 codex 중 하나라도 일일 사용 한도에 도달하면 그 즉시 작업을 멈춘다.**
재시도·우회 금지. 남은 일은 이 파일에 적고 종료한다. (과금 방지)
`scripts/relay-cmux.sh` 에 구현돼 있다 — 패널에서 한도 신호 감지 시 exit 99.

---

## 지금 상태 요약 (2026-07-30 기준)

커밋: `891694b` + 미커밋(WORKLOG 갱신, duplicate_zone_id 검증). 백엔드 테스트 **118개**,
프런트 lint 0/0, 빌드 성공. 브랜치 `fix/self-adjacent-surfaces` (main 미병합, 원격 미푸시).

**다음에 바로 할 일** (EPlusSimple 비교 + codex 검토로 우선순위 확정)

1. 🔴 **모델 의미 검증 규칙 추가** — 지금까지는 기하·참조 오류만 잡는다.
   "실행은 되지만 의미가 틀린 상태"를 잡아야 한다. EPlusSimple `debug.py` 참고:
   존에 floor/ceiling/wall 최소 하나씩 존재 / 창·문과 투명·불투명 construction 호환성 /
   비외기창 blind / 설비 참조 호환성 / 미사용 설비·구조체 / 냉난방·급탕 시스템 부재.
   기하 검사 개수를 늘리는 것보다 이쪽이 우선순위가 높다.
2. 🔴 **`/api/simulate` payload validator 완성** — 현재는 일부만 본다.
   미반영: 전역 ID·XML 참조 타입·단위 불일치·not_enclosed·Surface 자체의 퇴화 좌표·
   opening 퇴화·잘못된 adjacentZone·**baselineModel 무결성**.
   (중복 zone id·빈 id 는 2026-07-30 에 추가함)
3. 🟡 **ASHRAE 140/BESTEST 자동 pass/fail 벤치마크** — 양쪽 프로젝트 모두 없는 항목이다.
   EPlusSimple 의 "모델×프로필×기상 일괄 실행" 구조는 참고하되 **승인 기준값 +
   tolerance assertion** 을 반드시 붙일 것. 표 생성만 복제하면 의미가 없다.
4. 🟡 **냉방 차단을 35℃ setpoint 대신 명시적 availability schedule 로 전환** —
   PTHP 는 유닛·팬·냉방코일·난방코일·보조히터가 `op_schedule` 하나를 공유하므로
   계절 마스크를 그대로 얹으면 **겨울 난방까지 꺼진다.** 냉방코일에만 별도
   `cooling_availability_schedule` 이 필요하다. WindowAC(냉방 전용)는 전체 적용 가능,
   UnitHeater(난방 전용)는 기존 유지. IdealLoads 폴백은 장비 가용 스케줄이 비어 있어
   35℃ 마스크를 먼저 제거하면 폴백 경로의 계절 차단이 사라진다.
   → WindowAC 겨울냉방 0 / PTHP 겨울난방 유지 / 폴백 동작을 풀런으로 확인한 뒤 제거.
5. 🟡 **opening containment·overlap 검증** — 현재는 면적 합만 본다. 호스트 평면 이탈,
   개구부 간 겹침, 다른 평면에 있는 개구부는 통과한다. 2D 투영 후 containment/clipping 필요.
6. ⚪ **진짜 watertight 검사** — `detect_zone_gaps()` 는 법선벡터 합의 잔차만 본다.
   떨어진 면·상쇄되는 구멍은 통과하고 법선이 뒤집힌 면은 닫혀 있어도 걸린다.
   5% 를 "폐합 실패율"로 해석할 수 없다. edge incidence + signed volume 필요.
7. ⚪ 프로필 DB 확장(11 → 24종), 프런트 번들 code splitting, TRM/검증 보고서,
   Linux/CI 품질 게이트.
8. ⚪ 커밋 정리 / main 병합 / 푸시. `용호동 파일 2.xml` 은 여전히 untracked
   (실제 파일 검증 테스트 3건이 다른 환경에서 skip 됨).

**미해명으로 남은 것 — 난방 과소산정**

용호동 실행 결과 난방 6.6~7.0 vs 냉방 19.9~20.7 kWh/㎡·년. 서울 사무소로서 비상식적이다.
지워진 후보: 면적 기준 불일치(수정했으나 비율 불변) / 지면 열손실 누락(Ground 승격 민감도
+0.4 kWh/㎡, 6.1% — 기각) / 내부발열 과다(용도별로 정정했으나 조명 19.4 + 기기 25.1 = 44.5 로
여전히 큼) / 기상 파일 오선택(성남→서울 정정, 기후 차이 작음).
다음 후보: **외피 성능**. 단열재가 광물면 R13(λ=0.062)·광물보드 R-10.4 두 종뿐이고
창이 15개(WWR 매우 낮음)인데, 이 조합이 난방부하를 이렇게까지 낮출 수 있는지 검증 필요.
3번 벤치마크를 먼저 도입해 엔진 신뢰구간을 잡는 편이 순서상 나을 수 있다.

**정정된 과거 기록** (아래 옛 항목들과 충돌하면 이쪽이 맞다)

- ESLint `motion` 오탐: "건드리지 말라"고 적어뒀던 것은 진단이 얕았다. 진짜 원인은
  **`eslint-plugin-react` 미설치**였고, 설치 후 `react/jsx-uses-vars` 를 켜서 해결했다.
  현재 lint 는 0 errors / 0 warnings 다.
- 바닥면적 3중 불일치(864/964/1050): **해결됐다.** `<Space><Area>` 선언값 우선으로
  864.38㎡ 단일 기준. `areaUnit` 을 `lengthUnit` 과 독립 환산.
- `ARCHETYPE_LOADS` 의 `heat`/`cool` 미사용 필드 정리는 아직 안 했다(우선순위 낮음).

## 2026-07-30 — EPlusSimple(SNU) 대비 장단점 (codex 판정 + gemma 정리)

`891694b` 기준. codex가 두 저장소를 읽고 판정, gemma가 정리. **아래는 내가 코드로
재확인한 것만 확정 사실로 적는다.** 미확인 항목은 그렇게 표시했다.

### 먼저 바로잡은 내 오해 3건

1. **"EPlusSimple에 ASHRAE 140 표준 벤치마크 대조가 있다"는 틀렸다.**
   `scripts/dev/regressiontest.py` 는 `ASHRAE 140 modified.grm` 을 프로필·기상별로
   반복 실행해 결과 표를 LaTeX에 삽입할 뿐이다. **기준 범위·기준 프로그램 결과와의
   허용오차 비교도, 실패 assertion도 코드에 없다.** 표준 적합성 시험이 아니다.
   → 정확한 대비: 저쪽은 "시스템 수준 smoke/report 도구", 우리는 "자동 판정 테스트 116개".
   **양쪽 모두 공인 기준값 대조는 없다.**
2. **저쪽 입력 검증은 Excel 전용이다.** `debug.py` 의 `JSON_INSPECTORS` 는
   `JSON_INSPECTORS = []` 로 **비어 있다**(직접 확인). GRM/JSON 검증은 미구현이다.
   또 3단계는 항목별 등급이 아니라 "Exception 있으면 SEVERE, Warning만 있으면 WARNING"
   으로 병합하는 **결과 등급**이다. 우리 info/warn/choice/block(행동 정책 포함)과 동급 비교가 아니다.
3. **"우리 서버 신뢰 경계가 완성됐다"는 이르다.** `model_validation.py` 는 일부만 본다.
   특히 `zone_ids` 를 바로 set 으로 만들어 **중복 zone id 를 잃고 있었다**(확인 후 수정).

### 판정 요약

| 항목 | 판정 | 근거 |
|---|---|---|
| 입력 접근성(BIM 연계·웹) | **우리 장점** | gbXML 업로드 후 웹 3D 편집. 저쪽은 Excel/GRM 준비 + Windows launcher |
| 입력의 명시성·통제성 | 저쪽 장점 | 구조화 Excel은 관계를 명시. gbXML은 자기참조·면 귀속·이름 기반 용도추론 등 모호성이 구조적 |
| 기하·단위 검증 | **우리 장점** | 전역 ID·XML 참조·면적 단위·퇴화 기하·opening 초과·자기참조·선언/기하 불일치 |
| **의미 계층 검증** | **저쪽 장점** | 존에 floor/ceiling/wall 부재, 잘못된 인접존, 설비 참조·호환성, 투명/불투명 construction, 비외기창 blind, 미사용 설비, 냉난방·급탕 부재 |
| 경고 UX·승인 정책 | **우리 장점** | choice/block이 실제 행동(진행 차단, Ground/Adiabatic 선택)으로 연결 |
| HVAC 모델 상세도 | **우리 단점** | 저쪽은 Chiller/AbsorptionChiller/Boiler/AHU/FCU/Radiator/RadiantFloor + PlantLoop. 우리는 존 단위 PTHP·UnitHeater+WindowAC·IdealLoads |
| 프로필 DB | **우리 단점** | 저쪽 24종(환기량·급탕·요일·방학 포함) vs 우리 11종 |
| 설정온도 | 무승부 | 양쪽 20/26℃ 기본, 양쪽 override 가능 |
| 계절 제어 | 제한적 우리 장점 | 우리만 냉방기간 마스크. 단 35℃는 절대 차단이 아니고 고정 기간이 이상고온에 부적절할 수 있음 |
| 면적·내부발열 일관성 | **우리 장점** | 선언면적 우선 + 용도별 부하 전달이 코드상 일관 |
| 1차에너지·CO2 계약 | **우리 장점** | 백엔드 단일 출처 + 회귀 테스트로 고정 |
| 단위 테스트 | **우리 장점** | pytest 116개(현재 118). 저쪽 저장소에 pytest/unittest suite 없음 |
| **물리적 결과 검증** | **무승부이자 양쪽 약점** | 양쪽 모두 공인 기준값 assertion 없음 |
| 시스템 수준 시나리오 실행 | 저쪽 장점 | 프로필 24 × 지역 18 조합을 실제로 돌려 관찰 |
| 문서 | **우리 단점** | 저쪽 TRM/RN/RTR LaTeX 본문 + 도식·참고문헌. 우리는 WORKLOG·README 수준 (방법론 문서는 저장소 밖 아티팩트) |
| 비용·리모델링 의사결정 | **우리 장점** | 공사비 DB·LCC·요금·CO2·PV·baseline 비교·추천 UI 결합 |

### 당장 가져올 것 3가지 (우선순위)

1. **모델 의미 검증 규칙** — 저쪽의 `InsufficientSurfaceForZone`,
   `InvalidFenestrationConstruction`, `BlindForNonOutdoorWindow`,
   `InvalidSourceSystemName`, `NoHVACSystemApplied` 에 해당하는 검사.
   **"실행은 되지만 의미가 틀린 상태"를 잡는다.** 기하 검사 개수를 늘리는 것보다 우선순위가 높다.
2. **pass/fail 있는 벤치마크 harness** — 저쪽의 모델×프로필×기상 실행 구조는 가져오되
   LaTeX 표 생성만 복제하지 말고 **승인 기준값 + tolerance assertion**을 붙인다.
3. **한국형 프로필 확장** — 24종의 환기량·급탕·요일·방학 필드 참고. 단순 복사 금지,
   출처·단위·적용범위를 검증하고 CSV/JSON 으로 코드 밖에 분리.

상세 PlantLoop 이식은 가치는 크지만 "당장"이 아니다 — 데이터 모델·UI·비용집계·결과 미터를 함께 바꿔야 한다.

### 우리 단점 분류

**구조적으로 어려운 것**
- gbXML 익스포터별 의미 손실(자기참조 바닥, 공유면 한쪽 귀속, 이름 기반 용도추론) —
  원본 BIM 정보 없이 완전 자동 복구 불가
- 상세 HVAC/PlantLoop 확장 — 백엔드·UI·IDF 생성·결과 집계 전면 재설계 필요
- 실제 건물 calibration — 계측·운전·제어 데이터 없이는 코드로 해결 불가
- 웹 서비스의 EnergyPlus 계산 자원(큐·격리·메모리·보안)

**작업하면 되는 것**
- ASHRAE 140/BESTEST 자동 pass/fail 벤치마크
- 의미 검증 규칙 추가
- `/api/simulate` payload validator 완성 (전역 ID·참조 타입·단위·not_enclosed 미반영)
- 프로필 DB 확장 + 출처 문서화
- TRM/RN/검증 보고서
- **냉방 차단을 35℃ setpoint 대신 명시적 availability schedule 로 전환**
- opening containment·overlap 검증
- 프런트 번들 code splitting
- Linux/CI 품질 게이트(pytest+lint+build+benchmark)

**최종 평가**: 우리는 BIM 업로드·오류 진단·웹 편집·비용 의사결정·회귀 테스트에서 우세.
저쪽은 설비 모델 폭·한국형 프로필·의미 계층 검증·기술문서·시스템 시나리오 실행에서 우세.

---

## 2026-07-28 — 용호동 전체 시뮬레이션 + 결과 교차검증

자기참조 수정 후 처음으로 실제 업무 파일을 끝까지 돌렸다. **파이프라인은 완주**했고
경고가 API 응답까지 전달되는 것, 자기참조로 남은 면이 0개인 것을 확인했다.

결과: 요구량 117.6 / 소요량 80.1 / 1차 126.7 kWh/㎡·년, CO2 35.33 kg/㎡·년,
연간 에너지비 1,054만원. 월별 합계는 난방 5.1 / 냉방 21.6 / 조명 21.8 / 기기 28.5 / 급탕 2.4.

**난방 5.1 vs 냉방 21.6 은 서울 사무소로서 비상식적이다.** 원인 후보를 codex에 검토시켜
아래를 코드로 확인했다.

- ❌ **내 해석 오류**: "11~4월 냉방 0.0 이니 `COOLING_OFF_TEMP` 마스크가 작동한다"는 틀렸다.
  `cost_analyzer.py:804-810` 이 월별 값을 `round(..., 1)` 로 반올림하므로
  0.05 kWh/㎡·월 미만은 전부 0.0 으로 찍힌다. 0.0 은 차단의 증거가 아니다.
- ✅ **바닥면적 3중 불일치** — 위 「다음에 바로 할 일」 0번. 1,050.42 / 964.47 / 864.37 전부 실측 재현.
- ✅ **Z=0 자기참조 바닥 6면 = 177.99㎡** 가 Adiabatic. 지면 열손실 누락의 유력 후보.
- ⚠️ **`App.jsx:490-492` 가 모든 존에 `peopleDensity=0.1 / lightingPower=10 / equipmentPower=15`
  를 주입**한다(608-610은 `z.x || 기본값`). 화장실·계단실에도 사무실 수준 부하가 들어간다.
  **단, 이번 실행은 API 직접 호출이라 프론트를 거치지 않았다** — 존에 `activityId` 만 있고
  부하값은 비어 있어 백엔드가 용도별 아키타입을 썼다. 즉 이 버그는 실재하지만
  **이번 난방 과소산정의 원인은 아니다.** (프론트 경로에서는 별개로 고쳐야 한다.)

난방 과소산정의 최종 원인은 아직 미확정. 지면 열손실 누락과 면적 불일치가 유력하다.

## 2026-07-26 — 멀티 에이전트 릴레이 검토 파이프라인 구축

**한 일**

- 로컬 서버 기동 확인: 백엔드 `127.0.0.1:8000` (uvicorn, 루트 `.venv`),
  프론트 `localhost:5173` (Vite 8.0.3). 5173을 잡아서 CORS 문제 없음.
- Codex CLI 설치 — `/usr/local/lib` 는 EACCES라 `npm i -g --prefix ~/.local @openai/codex`.
  `codex-cli 0.145.0`, ChatGPT 계정으로 로그인 완료.
- **릴레이 파이프라인 2종 구축** (상세는 메모리 `cmux-relay-pipeline` 참조)
  - `scripts/relay.sh` — 헤드리스. codex CLI 직접 호출.
  - `scripts/relay-cmux.sh` — cmux 패널 가시화. Claude → codex 패널 → ollama 패널 → Claude.
    진행 상황이 화면에 그대로 보인다. 종료코드 0=P0없음 / 10=P0있음 / 20=라운드상한(3).
- **분류 모델 실측 비교** → `gemma4:e4b` 채택.
  | 모델 | 소요 | 원문 보존 |
  |---|---|---|
  | gemma4:e4b | 328초(첫 로드 포함) | 4/4 ✅ |
  | llama3.2:3b | 5초 | 0/4 — 본문을 "원문"이라는 글자로 치환 ❌ |
  | qwen3.5 | 2회 완주 실패 | — ❌ |
- 파이프라인 자체에서 버그 5개를 잡아가며 완성. 마지막 실행 EXIT=10 정상.

**관측 — `용호동 파일 2.xml`** (저장소 루트, 아직 git 미추가)
서울, Office, 연면적 864.37㎡, 5층, Space/Zone 20, Surface 235, 창 15.
시뮬레이션 시 주의할 점 2가지:
- 지면 접촉면(`SlabOnGrade`/`UndergroundWall`)이 **하나도 없다** → 1층 바닥 열손실 왜곡 가능.
- 외벽 113면에 창 15개뿐이라 WWR이 매우 낮다 → 창호 개선 시나리오 효과가 과소평가될 수 있다.

**미해결로 남긴 것**
- 위 P0 2건 (맨 위 「다음에 바로 할 일」 참조).
- 릴레이를 Claude Code `Stop` 훅에 걸어 자동 트리거하는 건 아직 안 붙였다.
