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
  //: **성공적으로 실린** 모델의 파일. 파싱 시도 중인 파일과 구분한다.
  uploadedFile: null,
  //: 지금 파싱을 시도 중인(또는 실패한) 파일. ⚠️ 이걸 `uploadedFile` 과 섞으면
  //: 실패한 파일이 업로드 화면에서 **성공한 것처럼** 보인다.
  parsingFile: null,
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
  SURFACE_EDIT_COMMITTED: 'SURFACE_EDIT_COMMITTED',
  ZONE_EDIT_COMMITTED: 'ZONE_EDIT_COMMITTED',
  CONSTRUCTION_OVERRIDE_APPLIED: 'CONSTRUCTION_OVERRIDE_APPLIED',
  CONSTRUCTION_OVERRIDE_RESET: 'CONSTRUCTION_OVERRIDE_RESET',
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
      // ⚠️ **현재 성공 모델은 건드리지 않는다.** 예전엔 여기서 재료·override 를
      // 지웠는데, 파싱이 실패하면 이전 모델이 **재료 없는 반쪽**으로 남았다.
      // 교체는 성공했을 때(`PARSE_SUCCEEDED`) 한 번에 한다.
      return { ...state, parsingFile: action.file, uploadError: null };

    case ModelAction.PARSE_SUCCEEDED: {
      const surfaces = action.surfaces || [];
      const zones = mapZones(action.zones);
      // ⚠️ 모델 관련 키를 **전부** 교체한다. `...state` 로 흘려보내면 이전 모델의
      // 잔여물(재료·override·경고·층수)이 새 건물에 섞인다.
      return {
        ...state,
        uploadedFile: action.file ?? state.parsingFile,
        parsingFile: null,
        uploadError: null,
        surfaces,
        zones,
        // 원본과 현재를 **같은 순간에** 채운다 — 따로 두면 기준선이 어긋난다.
        originalModel: { zones, surfaces },
        materials: action.materials ?? null,
        constructionOverrides: {},
        gapWarnings: action.warnings || [],
        realFloorCount: action.floorLevels ?? initialModelState.realFloorCount,
      };
    }

    case ModelAction.PARSE_FAILED:
      // ⚠️ **성공했던 모델을 통째로 보존한다.** 실패한 파일은 `parsingFile` 에
      // 남아 있어 무엇이 실패했는지 알 수 있고, `uploadedFile` 은 여전히 이전
      // 성공 파일을 가리킨다 — 실패한 파일이 성공한 것처럼 보이면 안 된다.
      return { ...state, uploadError: action.message };

    case ModelAction.SAMPLE_LOADED: {
      const zones = action.zones || [];
      const surfaces = action.surfaces || [];
      return {
        ...state,
        uploadedFile: action.file ?? { name: 'Sample_Building_V1.xml' },
        parsingFile: null,
        uploadError: null,
        surfaces,
        zones,
        originalModel: { zones, surfaces },
        materials: action.materials ?? null,
        constructionOverrides: {},
        gapWarnings: [],
        // ⚠️ 층수도 **반드시 교체**한다. `...state` 로 남기면 이전 건물의 층수로
        // 가상층을 판정한다 — 파싱 실패 화면에서 바로 샘플로 갈 수 있어 실제 경로다.
        realFloorCount: action.floorLevels ?? initialModelState.realFloorCount,
      };
    }

    case ModelAction.MODEL_RESET:
      // ⚠️ **전부** 초기값으로. 하나라도 남기면 다음 모델과 섞인다.
      return { ...initialModelState };

    case ModelAction.WARNINGS_DISMISSED:
      return { ...state, gapWarnings: [] };

    case ModelAction.SURFACE_EDIT_COMMITTED:
      return {
        ...state,
        surfaces: state.surfaces.map(
          (s) => (s.id === action.surfaceId ? { ...s, ...action.patch } : s)),
      };

    case ModelAction.ZONE_EDIT_COMMITTED: {
      // ⚠️ 일괄 적용은 **화이트리스트 필드만** 복사한다. 존 전체를 복사하면
      // 위치·면적·id 같은 고유 정보까지 덮어써 다른 존이 통째로 망가진다.
      const { surfaceId: _ignored, zoneId, patch, similarFields } = action;
      const applySimilar = Array.isArray(similarFields) && similarFields.length > 0
        && patch?.activityId != null;
      const shared = {};
      if (applySimilar) {
        similarFields.forEach((k) => { shared[k] = patch[k]; });
      }
      return {
        ...state,
        zones: state.zones.map((z) => {
          if (z.id === zoneId) return { ...z, ...patch };
          if (applySimilar && z.activityId === patch.activityId) return { ...z, ...shared };
          return z;
        }),
      };
    }

    case ModelAction.CONSTRUCTION_OVERRIDE_APPLIED:
      // ⚠️ override 와 면의 U 값을 **한 번에** 바꾼다. 예전에는
      // `setConstructionOverrides(prev => ...)` 의 갱신함수 **안에서**
      // `setSurfaces`·`setEditState` 를 불렀다. reducer 로 옮기면서 그 함수가
      // reducer 안에서 실행되게 되어 **순수하지 않은 reducer** 가 됐다.
      return {
        ...state,
        constructionOverrides: {
          ...state.constructionOverrides,
          [action.surfaceId]: action.override,
        },
        surfaces: action.uValue == null ? state.surfaces : state.surfaces.map(
          (s) => (s.id === action.surfaceId ? { ...s, uValue: action.uValue } : s)),
      };

    case ModelAction.CONSTRUCTION_OVERRIDE_RESET: {
      const rest = { ...state.constructionOverrides };
      delete rest[action.surfaceId];
      return {
        ...state,
        constructionOverrides: rest,
        // 원본 U 값 복원도 같은 전이에서 한다.
        surfaces: action.uValue == null ? state.surfaces : state.surfaces.map(
          (s) => (s.id === action.surfaceId ? { ...s, uValue: action.uValue } : s)),
      };
    }

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
