// state/execution.js — 화면 단계와 시뮬레이션 실행 상태.
//
// ⚠️ 이 넷은 **함께 바뀌어야 한다.** 시뮬레이션이 끝나면 결과 적재·화면 전환·
// 로딩 표시 정리가 한 순간에 일어나야 한다. 따로 두면 "결과 화면인데 로딩 문구가
// 계속 도는" 상태가 생긴다.
//
// ⚠️ `step` 전이를 마법사 순서로 **엄격히 제한하지 않는다.** 뒤로 가기,
// 파싱 실패, 결과에서 편집 복귀 같은 정상적인 비선형 경로가 이미 있다(codex 판정).
// 대신 의미 있는 action 으로 묶어 "무엇 때문에 화면이 바뀌었는지"를 남긴다.

export const initialExecution = {
  step: 'landing',
  loadingStage: null,     // queued | baseline | retrofit | alt:*
  loadingMsgIdx: 0,
  res: null,
};

export const ExecAction = {
  NAVIGATED: 'NAVIGATED',
  PARSE_STARTED: 'EXEC_PARSE_STARTED',
  PARSE_SETTLED: 'EXEC_PARSE_SETTLED',
  SIMULATION_STARTED: 'SIMULATION_STARTED',
  LOADING_STAGE_CHANGED: 'LOADING_STAGE_CHANGED',
  LOADING_MESSAGE_TICKED: 'LOADING_MESSAGE_TICKED',
  SIMULATION_SUCCEEDED: 'SIMULATION_SUCCEEDED',
  SIMULATION_FAILED: 'SIMULATION_FAILED',
  RESULT_INVALIDATED: 'RESULT_INVALIDATED',
};

export function executionReducer(state, action) {
  switch (action.type) {
    case ExecAction.NAVIGATED:
      return { ...state, step: action.step };

    case ExecAction.PARSE_STARTED:
      return { ...state, step: 'parsing' };

    case ExecAction.PARSE_SETTLED:
      // ⚠️ 실패 시에는 `parsing` 에 **머문다.** 오류 화면이 그 단계 안에 있어서,
      // upload 로 넘기면 사용자가 아무 안내도 못 받고 튕긴다.
      return action.ok ? { ...state, step: 'upload' } : state;

    case ExecAction.SIMULATION_STARTED:
      // 메시지 인덱스를 처음으로 되돌린다 — 안 하면 지난 실행의 마지막 문구부터 뜬다.
      return { ...state, step: 'loading', loadingMsgIdx: 0, loadingStage: null };

    case ExecAction.LOADING_STAGE_CHANGED:
      return { ...state, loadingStage: action.stage ?? null };

    case ExecAction.LOADING_MESSAGE_TICKED: {
      // ⚠️ 상한은 호출부가 준다 — reducer 가 UI 문구 배열을 import 하면
      // 의존성이 거꾸로 흐른다(codex 조언).
      const next = state.loadingMsgIdx + 1;
      const last = Number.isFinite(action.lastIndex) && action.lastIndex >= 0
        ? action.lastIndex : next;
      return { ...state, loadingMsgIdx: Math.min(next, last) };
    }

    case ExecAction.SIMULATION_SUCCEEDED:
      // ⚠️ 결과 적재·화면 전환·로딩 정리를 **한 전이에서** 한다.
      return { ...state, res: action.result, step: 'result', loadingStage: null };

    case ExecAction.SIMULATION_FAILED:
      // ⚠️ 결과는 건드리지 않는다 — 지난 성공 결과를 지우면 사용자가 비교 대상을
      // 잃는다. 로딩 화면에 가두지 않고 편집 화면으로 돌려보낸다.
      return { ...state, step: 'floorView', loadingStage: null };

    case ExecAction.RESULT_INVALIDATED:
      // ⚠️ 모델이 바뀌면 이전 결과는 **다른 건물의 것**이다. 남기면 3D 뷰가
      // 옛 결과로 칠해지고 결과 화면이 다른 건물 숫자를 보여준다.
      if (state.res === null) return state;
      return {
        ...state,
        res: null,
        loadingStage: null,
        // ⚠️ 결과 화면에 있는데 결과만 지우면 **0 으로 채워진 빈 결과 화면**이
        // 남는다. 안전한 단계로 보낸다(codex 지적).
        step: state.step === 'result' ? 'buildingView' : state.step,
      };

    default:
      return state;
  }
}
