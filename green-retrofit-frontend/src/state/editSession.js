// state/editSession.js — 평면도 편집 세션(선택·초안·모드·층).
//
// ⚠️ **모델과 분리된 묶음이다.** 여기 있는 `editState` 는 아직 커밋되지 않은
// **초안(draft)** 이고, 실제 반영은 model reducer 의 `*_EDIT_COMMITTED` 가 한다.
// 두 역할을 한 곳에 두면 "저장했는데 화면만 바뀐" 상태가 생긴다.
//
// ⚠️ 새 모델을 실으면 **반드시 `SESSION_RESET`** 을 함께 보낸다. 안 그러면
// `selectedId`·`activeFloor`·초안이 **이전 건물을 가리킨다**(codex 지적).

export const initialEditSession = {
  activeFloor: 1,
  editMode: 'surface',       // 'surface' | 'zone'
  selectedId: null,
  hoveredId: null,
  //: 선택한 면/존의 편집 초안. 저장 전까지 모델에 반영되지 않는다.
  editState: {},
  //: 같은 용도(activityId) 존에 일괄 적용할지.
  applyToSimilarZones: false,
  lightCalc: { active: false, w: 32, qty: 10, area: 100 },
  equipCalc: { active: false, w: 150, qty: 5, area: 100 },
};

export const EditAction = {
  SURFACE_SELECTED: 'SURFACE_SELECTED',
  ZONE_SELECTED: 'ZONE_SELECTED',
  SELECTION_CLEARED: 'SELECTION_CLEARED',
  DRAFT_CHANGED: 'DRAFT_CHANGED',
  HOVER_CHANGED: 'HOVER_CHANGED',
  MODE_SWITCHED: 'MODE_SWITCHED',
  FLOOR_CHANGED: 'FLOOR_CHANGED',
  APPLY_SIMILAR_CHANGED: 'APPLY_SIMILAR_CHANGED',
  LIGHT_CALC_CHANGED: 'LIGHT_CALC_CHANGED',
  EQUIP_CALC_CHANGED: 'EQUIP_CALC_CHANGED',
  EDIT_CLOSED: 'EDIT_CLOSED',
  SESSION_RESET: 'SESSION_RESET',
};

/** `useState` 처럼 값 또는 갱신함수를 받는다. */
function resolve(next, current) {
  return typeof next === 'function' ? next(current) : next;
}

/**
 * 편집을 닫을 때의 공통 정리.
 *
 * ⚠️ **일괄적용 체크를 반드시 끈다.** 안 끄면 다음 존을 편집할 때 사용자가
 * 의도하지 않은 일괄 적용이 조용히 걸린다.
 * 계산기는 접기만 하고 **입력값은 남긴다** — 같은 값을 다시 치게 하면 안 된다.
 */
function closed(state) {
  return {
    ...state,
    selectedId: null,
    editState: {},
    applyToSimilarZones: false,
    lightCalc: { ...state.lightCalc, active: false },
    equipCalc: { ...state.equipCalc, active: false },
  };
}

export function editSessionReducer(state, action) {
  switch (action.type) {
    case EditAction.SURFACE_SELECTED:
      // 면 초안은 편집 가능한 세 값만 담는다 — 전체를 복사하면 저장 시
      // 좌표·존 소속까지 덮어쓴다.
      return {
        ...state,
        selectedId: action.surface?.id ?? null,
        editState: action.surface
          ? {
              wwr: action.surface.wwr,
              uValue: action.surface.uValue,
              glazingId: action.surface.glazingId || 42,
            }
          : {},
      };

    case EditAction.ZONE_SELECTED:
      return {
        ...state,
        selectedId: action.zone?.id ?? action.zoneId ?? null,
        editState: action.zone ? { ...action.zone } : {},
        // ⚠️ 존을 옮기면 일괄적용을 끈다 — 다음 존에 실수로 이어붙지 않게.
        applyToSimilarZones: false,
      };

    case EditAction.SELECTION_CLEARED:
    case EditAction.EDIT_CLOSED:
      return closed(state);

    case EditAction.DRAFT_CHANGED:
      return { ...state, editState: resolve(action.editState, state.editState) };

    case EditAction.HOVER_CHANGED:
      return { ...state, hoveredId: action.hoveredId ?? null };

    case EditAction.MODE_SWITCHED:
      if (state.editMode === action.mode) return state;
      // ⚠️ 모드를 바꾸면 선택·hover 도 지운다. 면 id 를 든 채 존 모드로 가면
      // 존 편집기가 없는 존을 가리킨다.
      return { ...closed(state), editMode: action.mode, hoveredId: null };

    case EditAction.FLOOR_CHANGED:
      // ⚠️ 층을 옮기면 선택을 지운다 — 안 지우면 다른 층의 면이 선택된 채로
      // 편집 화면이 열린다.
      return { ...closed(state), activeFloor: action.floor, hoveredId: null };

    case EditAction.APPLY_SIMILAR_CHANGED:
      return { ...state, applyToSimilarZones: !!action.value };

    case EditAction.LIGHT_CALC_CHANGED:
      return { ...state, lightCalc: resolve(action.lightCalc, state.lightCalc) };

    case EditAction.EQUIP_CALC_CHANGED:
      return { ...state, equipCalc: resolve(action.equipCalc, state.equipCalc) };

    case EditAction.SESSION_RESET:
      // ⚠️ 새 모델을 실으면 반드시 여기까지 온다. 안 오면 선택·층·초안이
      // **이전 건물을 가리킨다.**
      return { ...initialEditSession };

    default:
      return state;
  }
}
