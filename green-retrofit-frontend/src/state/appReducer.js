// state/appReducer.js — 상태 묶음들을 조합하는 상위 reducer.
//
// ⚠️ 여기 있는 이유는 하나다: **여러 묶음이 한 사건에 함께 바뀌어야 할 때**를
// 한 전이로 만들기 위해서다. 특히 모델을 갈아끼울 때 편집 세션도 초기화해야
// 하는데, 호출부에서 두 dispatch 를 나란히 부르면 언젠가 하나를 빠뜨린다.

import { EditAction, editSessionReducer, initialEditSession } from './editSession';
import { ExecAction, executionReducer, initialExecution } from './execution';
import { ModelAction, initialModelState, modelReducer } from './modelReducer';

export const initialAppState = {
  model: initialModelState,
  edit: initialEditSession,
  exec: initialExecution,
};

export const AppAction = {
  //: 모델을 통째로 갈아끼운다. 편집 세션 초기화·결과 무효화가 **함께** 일어난다.
  MODEL_REPLACED: 'MODEL_REPLACED',
  //: 아래 셋은 **봉투(envelope)** 다. 어느 묶음으로 갈지를 이름이 아니라
  //: 구조로 정한다 — 값이 겹치면 조용히 잘못 라우팅되는 문제를 없앤다.
  MODEL: 'MODEL',
  EDIT: 'EDIT',
  EXEC: 'EXEC',
};

/** 묶음별 dispatch 봉투. `dispatch(toModel({type: ...}))` 처럼 쓴다. */
export const toModel = (action) => ({ type: AppAction.MODEL, action });
export const toEdit = (action) => ({ type: AppAction.EDIT, action });
export const toExec = (action) => ({ type: AppAction.EXEC, action });

/** 모델을 교체하는 action 들 — 이들은 편집 세션을 이전 건물에 남겨두면 안 된다. */
export const MODEL_REPLACING_ACTIONS = [
  ModelAction.PARSE_SUCCEEDED,
  ModelAction.SAMPLE_LOADED,
  ModelAction.MODEL_RESET,
];

export function appReducer(state, action) {
  if (action.type === AppAction.MODEL_REPLACED) {
    // ⚠️ 한 전이에서 둘 다 바꾼다. 예전에는 호출부가 두 dispatch 를 나란히
    // 불렀고, 그 연동은 정규식으로만 지켜지고 있었다(codex 지적).
    return {
      ...state,
      model: modelReducer(state.model, action.modelAction),
      edit: editSessionReducer(state.edit, { type: EditAction.SESSION_RESET }),
      // ⚠️ **이전 결과를 버린다.** 안 버리면 새 건물의 3D 뷰가 **옛 건물의 면별
      // 결과**로 칠해지고(뷰어가 `res.surfaceThermal` 을 쓴다), 결과 화면으로
      // 돌아가면 다른 건물의 숫자를 본다.
      exec: executionReducer(state.exec, { type: ExecAction.RESULT_INVALIDATED }),
    };
  }
  // ⚠️ 봉투로 라우팅한다. 예전에는 action **값**을 묶음별 목록과 대조했는데,
  // 값이 겹치면 조용히 다른 reducer 로 갔다(실제로 `PARSE_STARTED` 가 두 묶음에
  // 있어 한쪽 값을 바꿔야 했다). 구조로 정하면 겹칠 수가 없다.
  switch (action.type) {
    case AppAction.MODEL:
      return { ...state, model: modelReducer(state.model, action.action) };
    case AppAction.EDIT:
      return { ...state, edit: editSessionReducer(state.edit, action.action) };
    case AppAction.EXEC:
      return { ...state, exec: executionReducer(state.exec, action.action) };
    default:
      return state;
  }
}
