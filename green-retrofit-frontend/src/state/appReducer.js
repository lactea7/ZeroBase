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
  //: 모델을 통째로 갈아끼운다. 편집 세션 초기화가 **함께** 일어난다.
  MODEL_REPLACED: 'MODEL_REPLACED',
};

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
    };
  }
  if (Object.values(ModelAction).includes(action.type)) {
    return { ...state, model: modelReducer(state.model, action) };
  }
  if (Object.values(EditAction).includes(action.type)) {
    return { ...state, edit: editSessionReducer(state.edit, action) };
  }
  if (Object.values(ExecAction).includes(action.type)) {
    return { ...state, exec: executionReducer(state.exec, action) };
  }
  return state;
}
