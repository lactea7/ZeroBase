# 작업 일지

> 세션이 바뀌어도 여기만 읽으면 **어디까지 했고 다음에 뭘 할지** 알 수 있게 유지한다.
> 최신 항목이 위로 온다. 각 세션 끝에 「다음 할 일」을 반드시 갱신할 것.

---

## 운영 규칙

**Claude 또는 codex 중 하나라도 일일 사용 한도에 도달하면 그 즉시 작업을 멈춘다.**
재시도·우회 금지. 남은 일은 이 파일에 적고 종료한다. (과금 방지)
`scripts/relay-cmux.sh` 에 구현돼 있다 — 패널에서 한도 신호 감지 시 exit 99.

---

## 지금 상태 요약 (2026-07-26 기준)

**다음에 바로 할 일** (codex 교차검증으로 우선순위 재조정함)

1. ✅ **자기참조 인접면 — 해결 완료.** 상세는 아래 「해결 완료」 참조.
2. 🟡 ASHRAE 140 Case 600 표준 벤치마크 — 표준 기준결과·허용범위까지 명시할 것.
   (기존 50개 테스트가 "전부 비용·추천 로직"이라는 내 서술은 틀렸다.
   `test_window_geometry`/`test_hvac_equipment`/`test_fuel_mode`/`test_failures` 는
   형상·설비·연료·실패계약을 검증한다. 없는 건 **표준 대조 풀런 검증**이다.)
3. 🟡 냉방 차단을 가용 스케줄로 이관 — **"작은 수정"이 아니다. 중간 우선순위.**
   PTHP는 유닛·팬·냉방코일·난방코일·보조히터가 `op_schedule` 하나를 공유하므로
   계절 마스크를 그대로 얹으면 **겨울 난방까지 꺼진다.** 냉방코일에만 별도
   `cooling_availability_schedule` 을 줘야 한다. WindowAC(냉방 전용)는 전체 적용 가능,
   UnitHeater(난방 전용)는 기존 유지. 또 IdealLoads 폴백은 장비 가용 스케줄이 비어 있어
   35℃ 마스크를 먼저 제거하면 폴백 경로의 계절 차단이 사라진다.
   → 장비별 스케줄 인터페이스 + IdealLoads 폴백까지 함께 설계해야 하고,
   WindowAC 겨울냉방 0 / PTHP 겨울난방 유지 / 폴백 동작을 EnergyPlus 풀런으로 확인한 뒤
   35℃ 마스크를 제거할 것.
4. ⚪ `ARCHETYPE_LOADS` 의 `heat`/`cool` 필드 정리 — **실제로 안 쓰인다.**
   `ep_simulator.py:1072-1073` 은 `z.get("heatingSetpoint", 20.0)` / `coolingSetpoint 26.0`
   으로 폴백하고, `gbxml_parser.py:779-780`·`App.jsx:488-489` 도 전 존을 20/26℃로 초기화한다.
   즉 운영 설정온도 기본값은 이미 20/26℃다. 미사용 필드가 오해를 부르므로 제거하거나
   용도를 명시. 출처가 필요한 쪽은 실제 계산에 쓰이는 `ARCHETYPES` 의 **setback** 값이다
   (healthcare 난방 setback 22℃ 등). setback 과 운영 설정온도를 혼동해 20/26 으로
   일괄 통일하면 안 된다.
5. ⚪ `ResultDashboard.jsx:2` ESLint — 오탐이지만 **종료코드 1이 실제로 난다.**
   CI/배포 전 lint 게이트가 필요하면 대문자 별칭이나 JSX 사용 인식 설정을 추가할 것.
6. 프론트엔드 실제 동작 확인 (창호 상향/하향 버튼, 공사비 부호). 서버는 8000/5173.
7. 커밋 정리 — 수정 5건 + VRF 제거 + `scripts/`, `WORKLOG.md` 신규.

**해결 완료 — 자기참조 인접면 (2026-07-26, 3라운드 검증)**

`용호동 파일 2.xml` 에 `AdjacentSpaceId` 가 같은 Space 로 두 번 들어간 면이 **19개**
(`InteriorFloor` 9 / `InteriorWall` 7 / **`Air` 3**). 익스포터가 지면 접촉 바닥을
`SlabOnGrade` 대신 자기참조로 내보낸 것. 파서가 이를 그대로 받아 `ep_simulator` 가
**같은 Zone 안에 원본+미러 쌍**을 만들고 있었다.

- `gbxml_parser.py` — `space_1 == space_2` 면 인접관계를 버리고 `selfAdjacent` 플래그를
  세운다. 경고는 stdout 뿐 아니라 **API 응답 `warnings`** 로 나간다
  (`issue='self_adjacent_surface'`, `count`, `surfaces`, `message`).
- `App.jsx` — 경고 모달이 갭 경고 형태(`zone`/`deviation`)에 고정돼 있어 새 경고가
  빈 칸으로 렌더됐다. `w.issue` 로 분기하도록 수정.
- `ep_simulator.py` — Adiabatic 판정 두 곳(≈1036, ≈1240)에 `selfAdjacent` 를 추가.
  **이게 핵심이다**: 판정식이 `"interior" in t` 라서 타입에 interior 가 없는 **`Air` 면
  3개가 `Outdoors`/`SunExposed` 로 빠질 뻔했다** — 없던 외피와 일사 취득이 생기는,
  원래 버그보다 나쁜 회귀였다.
- 지면 경계 **자동 승격은 하지 않았다** (지하층·필로티·외기노출 바닥 오분류 위험).
  경고로 사용자에게 알리고 판단을 맡긴다.
- `tests/test_surface_adjacency.py` **10건 신규** — 파서 경계조건에 테스트가 아예 없었다.
  수정을 일시 제거해 실제로 실패하는지 매 라운드 확인했다.
- 백엔드 테스트 **60개 통과** (50 → 54 → 57 → 60).

교훈: 릴레이 3라운드가 각각 다른 층위의 결함을 잡았다 — ①경고가 사용자에게 안 감
②경고 계약에 테스트 없음 ③내 수정이 만든 `Air` 면 회귀. 특히 ③은 내가 "안전하다"고
판단하고 넘어간 지점이었다.

**해결 완료 추가**: `idf_builder.py` 의 죽은 VRF 코드 **184줄 제거**(1016→832줄).
`add_vrf_outdoor_unit`/`add_vrf_terminal` 은 정의만 있고 호출부가 없었다.
EP25.2에서 불안정해 PTHP로 대체된 것(주석에 기록돼 있었음). 함께 죽은 `_vrf_sources`
상태와 `finalize_hvac` 의 빈 루프도 제거. 테스트 50개 통과.

**해결 완료 (2026-07-26)**

- ✅ `ep_simulator.py:631` — `baseline_same` 조건에 `hvacUpgradeActive` 추가.
  설비 교체만 켠 시나리오에서 절감량이 0으로 보고되던 버그. 640행 제거 목록과 일치시킴.
- ✅ `recommendationActions.js` `window_upgrade` — `changed` 집계를 `setSurfaces`
  업데이터 밖으로 이동 (`surfaces` 직접 필터링). React 18 지연 실행 + StrictMode 이중 집계 대응.
- ✅ `recommendationActions.js` `window`(하향) — 위와 동일한 버그가 남아 있던 것을 같은 방식으로 수정.
  (내 불완전한 수정을 릴레이 round 2가 잡아냈다.)
- ✅ `ResultDashboard.jsx:651` / `pdfReport.js:408` — 상향안 공사비에 `+`를 무조건
  붙여 `capital_delta`가 음수일 때 `+-30만원`으로 표시되던 것. 같은 파일의 622·403행은
  이미 조건부 부호를 쓰고 있었다 — 두 군데만 누락. 화면과 PDF 양쪽 모두 수정.
- 백엔드 테스트 **50개 전부 통과** (4분 40초).

**EPlusSimple(SNU) 대비 비교 — 교차검증 완료 (2026-07-26)**

SNU 건물시스템연구실 EPlusSimple V0-6-3 과 비교 후 codex 교차검증으로 오류 3건을 바로잡았다.
확정된 사실만 남긴다.

- 설정온도: EPlusSimple 24개 프로필 전부 20/26℃. 우리는 11종 중 9종이 20/26℃로 일치하나
  `healthcare` 22/25℃, `auxiliary` 18/28℃ 는 다르다. "전부 동일"은 과장이었다.
- HVAC 제어: **우리도 가용 스케줄을 쓴다.** `ep_simulator.py:1103-1131` 이 `op_sch` 를
  PTHP·UnitHeater·WindowAC 에 `op_schedule=` 로 전달한다. `COOLING_OFF_TEMP=35` 는
  그 위에 얹은 계절 마스크이지 가용 스케줄의 대체재가 아니다.
- 기본 HVAC 모델: **IdealLoads 가 기본이 아니다.** 기본 열원은 지역난방(`App.jsx:157`
  heatSource=11) → UnitHeater + WindowAC 조합이고, IdealLoads 는 매핑 실패 시 폴백이다.
- **`idf_builder.py` 의 VRF 생성 함수(`add_vrf` 계열)는 호출하는 코드가 없다 — 죽은 코드다.**
  정리하거나 연결할지 판단 필요.
- EPlusSimple에 계절(냉난방기간) 개념이 없는 것은 사실 확인됨 — 가용 스케줄이 일간 시간대와
  방학만 반영한다. 다만 저쪽 회귀검증은 "ASHRAE 140-modified 사례분석"이지 표준 적합성
  검증은 아니므로 "ASHRAE 140 검증 완료"로 인용하면 안 된다.
- 교훈: gemma는 주장 6건 중 5건을 "판단보류"하고 유일하게 동의한 1건이 **틀린 주장**이었다.
  로컬 소형 모델은 사실 검증자로 쓰지 말 것 — 분류·포맷 용도로 한정. ([[cmux-relay-pipeline]])

**알아둘 것**: `ResultDashboard.jsx:2` 의 `'motion' is defined but never used` ESLint
에러는 **기존부터 있던 오탐**이다. `motion` 은 HEAD와 현재 모두 17회 등장해 실제로
쓰이며, ESLint 설정이 `<motion.div>` 같은 JSX 멤버 표현식을 인식하지 못할 뿐이다. 건드리지 말 것.

**보류 — P0 아님으로 판단**

`activity_schedules.py:304` `COOLING_OFF_TEMP = 35.0`. codex는 "35℃가 냉방을 원천
차단하지 못한다"고 P0로 지적했다. **기존 시뮬 결과(`temp_workspace/mcp_5840730dab28/
eplusout.csv`)로 실측한 결과 지적 자체는 사실이나 영향이 미미하다** —
겨울(12/1/2월) 냉방 6.4 kWh / 연간 냉방 57,756 kWh = **0.011%**.
즉 35℃ 차단은 사실상 작동 중이고, 완전 차단을 원하면 설정온도가 아니라 HVAC
가용 스케줄로 막아야 한다. 우선순위 낮음.

**커밋 안 된 변경**: 11개 파일 + 신규 `scripts/`, `WORKLOG.md`.
PDF 리포트 전문가 리뷰 반영 작업 (절감률 라벨, 예산 초과 경고, NPV 민감도) 진행 중.

---

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
