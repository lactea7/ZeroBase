/**
 * state/modelReducer.js — 업로드 모델 상태 전이표.
 *
 * ⚠️ 이 상태들은 **함께 바뀌어야 한다.** 흩어진 setter 로 두면 하나를 빠뜨리기
 * 쉽고, 그러면 이전 모델의 잔여물이 새 모델과 섞인다. 실제로 "수정하고 재업로드"
 * 가 `originalModel`(절감액의 기준선)과 `realFloorCount` 를 안 지우고 있었다.
 */
import { describe, expect, it } from 'vitest';
import {
  ModelAction, initialModelState, modelReducer,
} from '../modelReducer.js';

const FILE = { name: 'b.xml' };
const SURFACES = [{ id: 'S1', zone: 'Z1' }];
const ZONES = [{ id: 'Z1', name: '사무실', lightingPower: 9 }];

const act = (state, action) => modelReducer(state, action);
const loaded = () => act(initialModelState, {
  type: ModelAction.PARSE_SUCCEEDED,
  surfaces: SURFACES, zones: ZONES, materials: { constructions: [] },
  warnings: [{ id: 'S9' }], floorLevels: 3,
});

// ── 파싱 시작 ────────────────────────────────────────────

describe('PARSE_STARTED', () => {
  it('시도 중인 파일을 기록한다', () => {
    expect(act(initialModelState, { type: ModelAction.PARSE_STARTED, file: FILE })
      .parsingFile).toBe(FILE);
  });

  it('⚠️ 현재 성공 모델을 건드리지 않는다', () => {
    // 예전엔 여기서 재료·override 를 지웠는데, 파싱이 실패하면 이전 모델이
    // **재료 없는 반쪽**으로 남았다. 교체는 성공했을 때 한 번에 한다.
    const base = { ...loaded(), constructionOverrides: { S1: { tier: 'high' } } };
    const next = act(base, { type: ModelAction.PARSE_STARTED, file: FILE });
    expect(next.materials).toEqual(base.materials);
    expect(next.constructionOverrides).toEqual(base.constructionOverrides);
    expect(next.surfaces).toEqual(base.surfaces);
    expect(next.uploadedFile).toBe(base.uploadedFile);
  });

  it('이전 오류를 지운다', () => {
    const failed = act(initialModelState, { type: ModelAction.PARSE_FAILED, message: 'x' });
    expect(act(failed, { type: ModelAction.PARSE_STARTED, file: FILE }).uploadError).toBeNull();
  });
});

// ── 파싱 성공 ────────────────────────────────────────────

describe('PARSE_SUCCEEDED', () => {
  it('모델을 싣는다', () => {
    const s = loaded();
    expect(s.surfaces).toEqual(SURFACES);
    expect(s.zones[0].id).toBe('Z1');
    expect(s.materials).toEqual({ constructions: [] });
  });

  it('⚠️ 원본과 현재를 같은 순간에 채운다', () => {
    // 따로 두면 기준선이 어긋나 절감액이 통째로 틀린다
    const s = loaded();
    expect(s.originalModel).toEqual({ zones: s.zones, surfaces: s.surfaces });
  });

  it('존 매핑을 거친다 (백엔드 값 보존)', () => {
    const s = act(initialModelState, {
      type: ModelAction.PARSE_SUCCEEDED, surfaces: [], zones: [{ id: 'Z', lightingPower: 0 }],
    });
    expect(s.zones[0].lightingPower).toBe(0);      // 명시된 0 을 안 덮는다
    expect(s.zones[0].outletLoadType).toBe('max'); // 이중계산 방지 기본값
  });

  it('면 갭 경고를 싣는다', () => {
    expect(loaded().gapWarnings).toHaveLength(1);
  });

  it('⚠️ 새 모델에 경고가 없으면 이전 경고를 지운다', () => {
    // 남으면 멀쩡한 모델에 옛 경고가 뜬다
    const s = act(loaded(), { type: ModelAction.PARSE_SUCCEEDED, surfaces: [], zones: [] });
    expect(s.gapWarnings).toEqual([]);
  });

  it('실제 층수를 기록한다 (가상 층 구분용)', () => {
    expect(loaded().realFloorCount).toBe(3);
  });

  it('빈 응답에도 깨지지 않는다', () => {
    const s = act(initialModelState, { type: ModelAction.PARSE_SUCCEEDED });
    expect(s.surfaces).toEqual([]);
    expect(s.zones).toEqual([]);
  });
});

// ── 파싱 실패 ────────────────────────────────────────────

describe('PARSE_FAILED', () => {
  it('원인을 싣는다', () => {
    expect(act(initialModelState, {
      type: ModelAction.PARSE_FAILED, message: 'Space 참조 없음',
    }).uploadError).toBe('Space 참조 없음');
  });

  it('⚠️ 어떤 파일이 실패했는지 남긴다', () => {
    const started = act(initialModelState, { type: ModelAction.PARSE_STARTED, file: FILE });
    expect(act(started, { type: ModelAction.PARSE_FAILED, message: 'x' }).parsingFile).toBe(FILE);
  });

  it('⚠️ 실패한 파일이 성공한 것처럼 보이지 않는다', () => {
    // `uploadedFile` 은 **성공적으로 실린** 모델의 파일이다. 실패한 새 파일을
    // 여기에 넣으면 업로드 화면이 그 파일을 정상 로드된 것처럼 보여준다.
    const base = loaded();
    const started = act(base, { type: ModelAction.PARSE_STARTED, file: FILE });
    const failed = act(started, { type: ModelAction.PARSE_FAILED, message: 'x' });
    expect(failed.uploadedFile).toBe(base.uploadedFile);
    expect(failed.uploadedFile).not.toBe(FILE);
  });

  it('⚠️ 이전에 성공한 모델을 **통째로** 보존한다', () => {
    // 재업로드가 실패했다고 편집하던 모델을 반쪽으로 만들면 안 된다
    const base = { ...loaded(), constructionOverrides: { S1: { tier: 'high' } } };
    const started = act(base, { type: ModelAction.PARSE_STARTED, file: FILE });
    const failed = act(started, { type: ModelAction.PARSE_FAILED, message: 'x' });
    expect(failed.surfaces).toEqual(SURFACES);
    expect(failed.materials).toEqual(base.materials);
    expect(failed.constructionOverrides).toEqual(base.constructionOverrides);
    expect(failed.originalModel).toEqual(base.originalModel);
    expect(failed.realFloorCount).toBe(base.realFloorCount);
  });
});

// ── 샘플 ─────────────────────────────────────────────────

describe('SAMPLE_LOADED', () => {
  it('모델과 기준선을 함께 채운다', () => {
    const s = act(initialModelState, {
      type: ModelAction.SAMPLE_LOADED, surfaces: SURFACES, zones: ZONES,
    });
    expect(s.originalModel).toEqual({ zones: ZONES, surfaces: SURFACES });
    expect(s.uploadedFile.name).toMatch(/Sample/);
  });

  it('⚠️ 이전 모델의 override 와 경고를 지운다', () => {
    const dirty = { ...loaded(), constructionOverrides: { S1: {} } };
    const s = act(dirty, { type: ModelAction.SAMPLE_LOADED, surfaces: [], zones: [] });
    expect(s.constructionOverrides).toEqual({});
    expect(s.gapWarnings).toEqual([]);
  });

  it('오류 상태에서 시작해도 오류가 지워진다', () => {
    const failed = act(initialModelState, { type: ModelAction.PARSE_FAILED, message: 'x' });
    expect(act(failed, { type: ModelAction.SAMPLE_LOADED, surfaces: [], zones: [] })
      .uploadError).toBeNull();
  });
});

// ── 초기화 ───────────────────────────────────────────────

describe('MODEL_RESET', () => {
  it('⚠️ 모든 키를 초기값으로 되돌린다', () => {
    // 하나라도 남으면 다음 모델과 섞인다. 특히 `originalModel` 이 남으면
    // 엉뚱한 건물과 비교해 절감액이 통째로 틀린다.
    expect(act(loaded(), { type: ModelAction.MODEL_RESET })).toEqual(initialModelState);
  });

  it.each(Object.keys(initialModelState))('%s 가 초기값으로 돌아간다', (key) => {
    const reset = act(loaded(), { type: ModelAction.MODEL_RESET });
    expect(reset[key]).toEqual(initialModelState[key]);
  });

  it('초기 상태 객체를 공유하지 않는다', () => {
    // 반환값을 나중에 변형해도 초기값이 오염되면 안 된다
    expect(act(loaded(), { type: ModelAction.MODEL_RESET })).not.toBe(initialModelState);
  });
});

// ── 편집 ─────────────────────────────────────────────────

describe('편집 갱신', () => {
  it('면을 값으로 바꾼다', () => {
    const s = act(loaded(), { type: ModelAction.SURFACES_CHANGED, surfaces: [] });
    expect(s.surfaces).toEqual([]);
  });

  it('면을 갱신함수로 바꾼다 (기존 setState 사용법 호환)', () => {
    const s = act(loaded(), {
      type: ModelAction.SURFACES_CHANGED,
      surfaces: (prev) => prev.map((x) => ({ ...x, uValue: 0.2 })),
    });
    expect(s.surfaces[0].uValue).toBe(0.2);
  });

  it('⚠️ 편집이 기준선(originalModel)을 바꾸지 않는다', () => {
    // 바뀌면 개선 전후가 같아져 절감이 0 이 된다
    const base = loaded();
    const s = act(base, { type: ModelAction.SURFACES_CHANGED, surfaces: [] });
    expect(s.originalModel).toBe(base.originalModel);
  });

  it('override 를 갱신함수로 바꾼다', () => {
    const s = act(loaded(), {
      type: ModelAction.OVERRIDES_CHANGED,
      overrides: (prev) => ({ ...prev, S1: { tier: 'high' } }),
    });
    expect(s.constructionOverrides.S1).toEqual({ tier: 'high' });
  });

  it('경고를 닫아도 모델은 남는다', () => {
    const s = act(loaded(), { type: ModelAction.WARNINGS_DISMISSED });
    expect(s.gapWarnings).toEqual([]);
    expect(s.surfaces).toEqual(SURFACES);
  });
});

describe('불변성', () => {
  it('알 수 없는 action 은 같은 객체를 돌려준다', () => {
    const s = loaded();
    expect(act(s, { type: '없는액션' })).toBe(s);
  });

  it.each([
    ModelAction.PARSE_STARTED, ModelAction.PARSE_FAILED,
    ModelAction.WARNINGS_DISMISSED, ModelAction.MODEL_RESET,
  ])('%s 가 이전 상태를 변형하지 않는다', (type) => {
    const before = loaded();
    const snapshot = JSON.parse(JSON.stringify(before));
    act(before, { type, file: FILE, message: 'x' });
    expect(JSON.parse(JSON.stringify(before))).toEqual(snapshot);
  });
});

// ── 성공 시 완전 교체 ────────────────────────────────────

describe('PARSE_SUCCEEDED 가 이전 모델을 남기지 않는다', () => {
  it('⚠️ override 를 초기화한다', () => {
    // 새 건물에 옛 면 id 로 걸린 override 가 남으면 U 값이 엉뚱해진다
    const dirty = { ...loaded(), constructionOverrides: { S1: { tier: 'high' } } };
    expect(act(dirty, { type: ModelAction.PARSE_SUCCEEDED, surfaces: [], zones: [] })
      .constructionOverrides).toEqual({});
  });

  it('⚠️ 재료를 교체한다 (새 응답에 없으면 비운다)', () => {
    expect(act(loaded(), { type: ModelAction.PARSE_SUCCEEDED, surfaces: [], zones: [] })
      .materials).toBeNull();
  });

  it('⚠️ 층수를 교체한다', () => {
    expect(act(loaded(), { type: ModelAction.PARSE_SUCCEEDED, surfaces: [], zones: [] })
      .realFloorCount).toBe(initialModelState.realFloorCount);
  });

  it('시도 중이던 파일이 성공 파일이 된다', () => {
    const started = act(initialModelState, { type: ModelAction.PARSE_STARTED, file: FILE });
    const ok = act(started, { type: ModelAction.PARSE_SUCCEEDED, surfaces: [], zones: [] });
    expect(ok.uploadedFile).toBe(FILE);
    expect(ok.parsingFile).toBeNull();
  });
});

describe('SAMPLE_LOADED 가 이전 건물 잔여물을 남기지 않는다', () => {
  it('⚠️ 층수를 교체한다 — 파싱 실패 화면에서 바로 샘플로 갈 수 있다', () => {
    const s = act(loaded(), {
      type: ModelAction.SAMPLE_LOADED, surfaces: [], zones: [], floorLevels: 5,
    });
    expect(s.realFloorCount).toBe(5);
  });

  it('층수를 안 주면 초기값으로 돌린다 (이전 건물 값이 아니라)', () => {
    expect(act(loaded(), { type: ModelAction.SAMPLE_LOADED, surfaces: [], zones: [] })
      .realFloorCount).toBe(initialModelState.realFloorCount);
  });
});

// ── 구성체 override ──────────────────────────────────────
// ⚠️ 예전에는 `setConstructionOverrides(prev => ...)` 의 갱신함수 **안에서**
// `setSurfaces`·`setEditState` 를 불렀다. reducer 로 옮기면 그 함수가 reducer 안에서
// 실행돼 **순수하지 않은 reducer** 가 된다(codex 지적). 의미 있는 action 으로 바꿨다.

describe('CONSTRUCTION_OVERRIDE_APPLIED', () => {
  it('override 와 면 U 값을 한 번에 바꾼다', () => {
    const s = act(loaded(), {
      type: ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
      surfaceId: 'S1', override: { tier: 'high', uValue: 0.24 }, uValue: 0.24,
    });
    expect(s.constructionOverrides.S1.tier).toBe('high');
    expect(s.surfaces[0].uValue).toBe(0.24);
  });

  it('U 값이 없으면 면을 건드리지 않는다 (구성체를 못 찾은 경우)', () => {
    const base = loaded();
    const s = act(base, {
      type: ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
      surfaceId: 'S1', override: { tier: 'high' },
    });
    expect(s.surfaces).toBe(base.surfaces);
  });

  it('다른 면은 건드리지 않는다', () => {
    const base = { ...loaded(), surfaces: [{ id: 'S1', uValue: 1 }, { id: 'S2', uValue: 2 }] };
    const s = act(base, {
      type: ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
      surfaceId: 'S1', override: {}, uValue: 0.3,
    });
    expect(s.surfaces[1].uValue).toBe(2);
  });
});

describe('CONSTRUCTION_OVERRIDE_RESET', () => {
  it('override 를 지우고 원본 U 값을 되돌린다', () => {
    const withOv = act(loaded(), {
      type: ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
      surfaceId: 'S1', override: { tier: 'high' }, uValue: 0.24,
    });
    const s = act(withOv, {
      type: ModelAction.CONSTRUCTION_OVERRIDE_RESET, surfaceId: 'S1', uValue: 0.8,
    });
    expect(s.constructionOverrides.S1).toBeUndefined();
    expect(s.surfaces[0].uValue).toBe(0.8);
  });

  it('다른 면의 override 는 남는다', () => {
    let s = loaded();
    for (const id of ['S1', 'S2']) {
      s = act(s, { type: ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
                   surfaceId: id, override: { tier: 'high' } });
    }
    s = act(s, { type: ModelAction.CONSTRUCTION_OVERRIDE_RESET, surfaceId: 'S1' });
    expect(s.constructionOverrides.S2).toBeDefined();
  });
});

// ── 불변성 (전 action) ───────────────────────────────────
// ⚠️ 예전 시험은 일부 action 만 봤다. **모든 action** 을 얼린 입력으로 돌린다.

function deepFreeze(o) {
  Object.getOwnPropertyNames(o).forEach((k) => {
    const v = o[k];
    if (v && typeof v === 'object') deepFreeze(v);
  });
  return Object.freeze(o);
}

describe('모든 action 이 입력을 변형하지 않는다', () => {
  it.each([
    [ModelAction.PARSE_STARTED, { file: FILE }],
    [ModelAction.PARSE_SUCCEEDED, { surfaces: SURFACES, zones: ZONES, floorLevels: 2 }],
    [ModelAction.PARSE_FAILED, { message: 'x' }],
    [ModelAction.SAMPLE_LOADED, { surfaces: SURFACES, zones: ZONES }],
    [ModelAction.MODEL_RESET, {}],
    [ModelAction.WARNINGS_DISMISSED, {}],
    [ModelAction.SURFACES_CHANGED, { surfaces: [] }],
    [ModelAction.ZONES_CHANGED, { zones: [] }],
    [ModelAction.OVERRIDES_CHANGED, { overrides: {} }],
    [ModelAction.CONSTRUCTION_OVERRIDE_APPLIED,
     { surfaceId: 'S1', override: { tier: 'high' }, uValue: 0.3 }],
    [ModelAction.CONSTRUCTION_OVERRIDE_RESET, { surfaceId: 'S1', uValue: 0.8 }],
  ])('%s', (type, payload) => {
    const frozen = deepFreeze(loaded());
    expect(() => modelReducer(frozen, { type, ...payload })).not.toThrow();
  });
});

// ── 편집 커밋 ────────────────────────────────────────────
// ⚠️ `handleSaveClose` 는 두 역할이 섞여 있었다 — 초안을 모델에 커밋하는 것과
// 편집 세션을 닫는 것. 커밋만 여기로 옮겼다(codex 조언).

const SIMILAR_FIELDS = ['activityId', 'lightingPower', 'equipmentPower', 'isConditioned'];

function withZones(zones) {
  return { ...initialModelState, zones, originalModel: { zones, surfaces: [] } };
}

describe('SURFACE_EDIT_COMMITTED', () => {
  it('대상 면만 바꾼다', () => {
    const base = { ...initialModelState, surfaces: [{ id: 'S1', wwr: 10 }, { id: 'S2', wwr: 10 }] };
    const s = act(base, {
      type: ModelAction.SURFACE_EDIT_COMMITTED, surfaceId: 'S1', patch: { wwr: 40 } });
    expect(s.surfaces[0].wwr).toBe(40);
    expect(s.surfaces[1].wwr).toBe(10);
  });

  it('⚠️ 기준선(originalModel)은 안 바뀐다', () => {
    // 바뀌면 개선 전후가 같아져 절감이 0 이 된다
    const base = loaded();
    const s = act(base, {
      type: ModelAction.SURFACE_EDIT_COMMITTED, surfaceId: 'S1', patch: { wwr: 40 } });
    expect(s.originalModel).toBe(base.originalModel);
  });

  it('없는 면 id 는 아무것도 안 바꾼다', () => {
    const base = loaded();
    const s = act(base, {
      type: ModelAction.SURFACE_EDIT_COMMITTED, surfaceId: '없음', patch: { wwr: 40 } });
    expect(s.surfaces).toEqual(base.surfaces);
  });
});

describe('ZONE_EDIT_COMMITTED', () => {
  const ZS = [
    { id: 'Z1', activityId: 1105, lightingPower: 9, area: 100, floor: 1 },
    { id: 'Z2', activityId: 1105, lightingPower: 9, area: 250, floor: 2 },
    { id: 'Z3', activityId: 9999, lightingPower: 4, area: 30, floor: 1 },
  ];

  it('일괄 적용이 없으면 대상 존만 바꾼다', () => {
    const s = act(withZones(ZS), {
      type: ModelAction.ZONE_EDIT_COMMITTED, zoneId: 'Z1',
      patch: { lightingPower: 5 },
    });
    expect(s.zones[0].lightingPower).toBe(5);
    expect(s.zones[1].lightingPower).toBe(9);
  });

  it('같은 용도의 존에 일괄 적용한다', () => {
    const s = act(withZones(ZS), {
      type: ModelAction.ZONE_EDIT_COMMITTED, zoneId: 'Z1',
      patch: { activityId: 1105, lightingPower: 5 }, similarFields: SIMILAR_FIELDS,
    });
    expect(s.zones[1].lightingPower).toBe(5);   // 같은 용도
    expect(s.zones[2].lightingPower).toBe(4);   // 다른 용도는 그대로
  });

  it('⚠️ **고유 필드는 절대 복사하지 않는다**', () => {
    // 존 전체를 복사하면 위치·면적·id 까지 덮어써 다른 존이 통째로 망가진다
    const s = act(withZones(ZS), {
      type: ModelAction.ZONE_EDIT_COMMITTED, zoneId: 'Z1',
      patch: { activityId: 1105, lightingPower: 5, area: 100, floor: 1, id: 'Z1' },
      similarFields: SIMILAR_FIELDS,
    });
    expect(s.zones[1].id).toBe('Z2');
    expect(s.zones[1].area).toBe(250);
    expect(s.zones[1].floor).toBe(2);
  });

  it('용도가 없으면 일괄 적용하지 않는다', () => {
    // activityId 가 없으면 "같은 용도"를 판정할 수 없다
    const s = act(withZones(ZS), {
      type: ModelAction.ZONE_EDIT_COMMITTED, zoneId: 'Z1',
      patch: { lightingPower: 5 }, similarFields: SIMILAR_FIELDS,
    });
    expect(s.zones[1].lightingPower).toBe(9);
  });

  it('대상 존 자신은 patch 전체를 받는다', () => {
    const s = act(withZones(ZS), {
      type: ModelAction.ZONE_EDIT_COMMITTED, zoneId: 'Z1',
      patch: { activityId: 1105, lightingPower: 5, coolingSetpoint: 24 },
      similarFields: SIMILAR_FIELDS,
    });
    expect(s.zones[0].coolingSetpoint).toBe(24);
    // 화이트리스트 밖 필드는 다른 존에 안 간다
    expect(s.zones[1].coolingSetpoint).toBeUndefined();
  });

  it('⚠️ 기준선은 안 바뀐다', () => {
    const base = withZones(ZS);
    const s = act(base, {
      type: ModelAction.ZONE_EDIT_COMMITTED, zoneId: 'Z1', patch: { lightingPower: 5 } });
    expect(s.originalModel).toBe(base.originalModel);
  });
});
