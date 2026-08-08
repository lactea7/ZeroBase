// state/modelReducer.js — 업로드한 건물 모델의 상태.
//
// ⚠️ 이 상태들은 **함께 바뀌어야 한다.** 흩어진 setter 로 두면 한두 개를 빠뜨리기
// 쉽고, 그러면 이전 모델의 잔여물이 새 모델과 섞인다. 실제로 "수정하고 재업로드"
// 버튼이 `originalModel` 과 `realFloorCount` 를 안 지우고 있었다 —
// `originalModel` 은 **절감액의 기준선**이라 남으면 엉뚱한 건물과 비교하게 된다.
//
// 상태 전이는 `src/state/__tests__/modelReducer.test.js` 가 표로 고정한다.

import { mapZones } from '../utils/parseResponse';

export const initialModelState = {
  uploadedFile: null,
  uploadError: null,
  surfaces: [],
  zones: [],
  //: 업로드 원본. 전/후 비교의 기준선이다 — 새 모델을 올리면 반드시 함께 바뀐다.
  originalModel: null,
  materials: null,
  constructionOverrides: {},
  gapWarnings: [],
  //: 파서가 감지한 실제 층수 (가상 층 제외)
  realFloorCount: 0,
};

export const ModelAction = {
  PARSE_STARTED: 'PARSE_STARTED',
  PARSE_SUCCEEDED: 'PARSE_SUCCEEDED',
  PARSE_FAILED: 'PARSE_FAILED',
  SAMPLE_LOADED: 'SAMPLE_LOADED',
  MODEL_RESET: 'MODEL_RESET',
  WARNINGS_DISMISSED: 'WARNINGS_DISMISSED',
  SURFACES_CHANGED: 'SURFACES_CHANGED',
  ZONES_CHANGED: 'ZONES_CHANGED',
  OVERRIDES_CHANGED: 'OVERRIDES_CHANGED',
};

/** `useState` 처럼 값 또는 갱신함수를 받는다 — 기존 호출부를 그대로 옮기기 위해. */
function resolve(next, current) {
  return typeof next === 'function' ? next(current) : next;
}

export function modelReducer(state, action) {
  switch (action.type) {
    case ModelAction.PARSE_STARTED:
      // ⚠️ 이전 모델의 재료·override 를 여기서 지운다. 안 지우면 새 건물에
      // 옛 구성체가 붙어 U 값이 엉뚱해진다.
      return {
        ...state,
        uploadedFile: action.file,
        uploadError: null,
        materials: null,
        constructionOverrides: {},
      };

    case ModelAction.PARSE_SUCCEEDED: {
      const surfaces = action.surfaces || [];
      const zones = mapZones(action.zones);
      return {
        ...state,
        surfaces,
        zones,
        // 원본과 현재를 **같은 순간에** 채운다 — 따로 두면 기준선이 어긋난다.
        originalModel: { zones, surfaces },
        materials: action.materials ?? null,
        gapWarnings: action.warnings || [],
        realFloorCount: action.floorLevels ?? initialModelState.realFloorCount,
        uploadError: null,
      };
    }

    case ModelAction.PARSE_FAILED:
      // ⚠️ 실패해도 `uploadedFile` 은 남긴다 — 어떤 파일이 실패했는지 보여야 한다.
      return { ...state, uploadError: action.message };

    case ModelAction.SAMPLE_LOADED: {
      const zones = action.zones || [];
      const surfaces = action.surfaces || [];
      return {
        ...state,
        uploadedFile: action.file ?? { name: 'Sample_Building_V1.xml' },
        uploadError: null,
        surfaces,
        zones,
        originalModel: { zones, surfaces },
        materials: action.materials ?? null,
        constructionOverrides: {},
        gapWarnings: [],
      };
    }

    case ModelAction.MODEL_RESET:
      // ⚠️ **전부** 초기값으로. 하나라도 남기면 다음 모델과 섞인다.
      return { ...initialModelState };

    case ModelAction.WARNINGS_DISMISSED:
      return { ...state, gapWarnings: [] };

    case ModelAction.SURFACES_CHANGED:
      return { ...state, surfaces: resolve(action.surfaces, state.surfaces) };

    case ModelAction.ZONES_CHANGED:
      return { ...state, zones: resolve(action.zones, state.zones) };

    case ModelAction.OVERRIDES_CHANGED:
      return {
        ...state,
        constructionOverrides: resolve(action.overrides, state.constructionOverrides),
      };

    default:
      return state;
  }
}
