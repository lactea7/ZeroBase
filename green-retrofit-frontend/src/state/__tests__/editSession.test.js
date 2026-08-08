/**
 * state/editSession.js — 편집 세션 상태 전이표.
 *
 * ⚠️ 여기 `editState` 는 아직 커밋되지 않은 **초안**이다. 실제 모델 반영은
 * model reducer 의 `*_EDIT_COMMITTED` 가 한다 — 두 역할을 섞으면 "저장했는데
 * 화면만 바뀐" 상태가 생긴다.
 */
import { describe, expect, it } from 'vitest';
import { EditAction, editSessionReducer, initialEditSession } from '../editSession.js';

const act = (state, action) => editSessionReducer(state, action);
const SURFACE = { id: 'S1', wwr: 30, uValue: 0.5, glazingId: 154, vertices: [[0, 0, 0]] };
const ZONE = { id: 'Z1', activityId: 1105, lightingPower: 9, area: 100 };

const withSurface = () => act(initialEditSession,
  { type: EditAction.SURFACE_SELECTED, surface: SURFACE });
const withZone = () => act({ ...initialEditSession, editMode: 'zone' },
  { type: EditAction.ZONE_SELECTED, zone: ZONE });

// ── 선택 ─────────────────────────────────────────────────

describe('SURFACE_SELECTED', () => {
  it('면을 선택하고 초안을 만든다', () => {
    const s = withSurface();
    expect(s.selectedId).toBe('S1');
    expect(s.editState).toEqual({ wwr: 30, uValue: 0.5, glazingId: 154 });
  });

  it('⚠️ 편집 가능한 값만 초안에 담는다', () => {
    // 면 전체를 복사하면 저장 시 좌표·존 소속까지 덮어쓴다
    expect(withSurface().editState.vertices).toBeUndefined();
  });

  it('유리가 없으면 기본 복층(42)으로 시작한다', () => {
    const s = act(initialEditSession, {
      type: EditAction.SURFACE_SELECTED, surface: { id: 'S1', wwr: 0, uValue: 1 } });
    expect(s.editState.glazingId).toBe(42);
  });

  it('빈 선택은 초안을 비운다', () => {
    const s = act(withSurface(), { type: EditAction.SURFACE_SELECTED, surface: null });
    expect(s.selectedId).toBeNull();
    expect(s.editState).toEqual({});
  });
});

describe('ZONE_SELECTED', () => {
  it('존 전체를 초안으로 삼는다', () => {
    expect(withZone().editState).toEqual(ZONE);
  });

  it('⚠️ 존을 옮기면 일괄적용 체크를 끈다', () => {
    // 안 끄면 다음 존에 의도치 않은 일괄 적용이 조용히 걸린다
    const on = act(withZone(), { type: EditAction.APPLY_SIMILAR_CHANGED, value: true });
    expect(on.applyToSimilarZones).toBe(true);
    const next = act(on, { type: EditAction.ZONE_SELECTED, zone: { id: 'Z2' } });
    expect(next.applyToSimilarZones).toBe(false);
  });
});

// ── 닫기 ─────────────────────────────────────────────────

describe('EDIT_CLOSED', () => {
  it('선택과 초안을 지운다', () => {
    const s = act(withSurface(), { type: EditAction.EDIT_CLOSED });
    expect(s.selectedId).toBeNull();
    expect(s.editState).toEqual({});
  });

  it('⚠️ 일괄적용을 끈다', () => {
    const on = act(withZone(), { type: EditAction.APPLY_SIMILAR_CHANGED, value: true });
    expect(act(on, { type: EditAction.EDIT_CLOSED }).applyToSimilarZones).toBe(false);
  });

  it('⚠️ 계산기는 접되 입력값은 남긴다', () => {
    // 같은 값을 다시 치게 하면 안 된다
    const open = act(withZone(), {
      type: EditAction.LIGHT_CALC_CHANGED, lightCalc: { active: true, w: 45, qty: 20, area: 80 } });
    const closed = act(open, { type: EditAction.EDIT_CLOSED });
    expect(closed.lightCalc.active).toBe(false);
    expect(closed.lightCalc).toMatchObject({ w: 45, qty: 20, area: 80 });
  });

  it('선택이 없어도 깨지지 않는다', () => {
    expect(() => act(initialEditSession, { type: EditAction.EDIT_CLOSED })).not.toThrow();
  });
});

// ── 모드·층 전환 ─────────────────────────────────────────

describe('MODE_SWITCHED', () => {
  it('⚠️ 모드를 바꾸면 선택과 hover 를 지운다', () => {
    // 면 id 를 든 채 존 모드로 가면 존 편집기가 없는 존을 가리킨다
    const hovered = act(withSurface(), { type: EditAction.HOVER_CHANGED, hoveredId: 'S9' });
    const s = act(hovered, { type: EditAction.MODE_SWITCHED, mode: 'zone' });
    expect(s.editMode).toBe('zone');
    expect(s.selectedId).toBeNull();
    expect(s.hoveredId).toBeNull();
    expect(s.editState).toEqual({});
  });

  it('같은 모드면 아무것도 바꾸지 않는다', () => {
    const s = withSurface();
    expect(act(s, { type: EditAction.MODE_SWITCHED, mode: 'surface' })).toBe(s);
  });
});

describe('FLOOR_CHANGED', () => {
  it('층을 바꾼다', () => {
    expect(act(initialEditSession, { type: EditAction.FLOOR_CHANGED, floor: 3 })
      .activeFloor).toBe(3);
  });

  it('⚠️ 층을 옮기면 선택을 지운다', () => {
    // 안 지우면 다른 층의 면이 선택된 채로 편집 화면이 열린다
    const s = act(withSurface(), { type: EditAction.FLOOR_CHANGED, floor: 2 });
    expect(s.selectedId).toBeNull();
    expect(s.editState).toEqual({});
  });
});

// ── 초기화 ───────────────────────────────────────────────

describe('SESSION_RESET', () => {
  it('⚠️ 전부 초기값으로 — 새 모델이 이전 선택을 물려받으면 안 된다', () => {
    const dirty = act(act(withZone(), { type: EditAction.FLOOR_CHANGED, floor: 7 }),
                      { type: EditAction.HOVER_CHANGED, hoveredId: 'X' });
    expect(act(dirty, { type: EditAction.SESSION_RESET })).toEqual(initialEditSession);
  });

  it.each(Object.keys(initialEditSession))('%s 가 초기값으로 돌아간다', (key) => {
    const reset = act(withZone(), { type: EditAction.SESSION_RESET });
    expect(reset[key]).toEqual(initialEditSession[key]);
  });
});

// ── 불변성 ───────────────────────────────────────────────

function deepFreeze(o) {
  Object.getOwnPropertyNames(o).forEach((k) => {
    const v = o[k];
    if (v && typeof v === 'object') deepFreeze(v);
  });
  return Object.freeze(o);
}

describe('불변성', () => {
  it('알 수 없는 action 은 같은 객체를 돌려준다', () => {
    const s = withSurface();
    expect(act(s, { type: '없는액션' })).toBe(s);
  });

  it.each(Object.values(EditAction))('%s 가 입력을 변형하지 않는다', (type) => {
    const frozen = deepFreeze(withZone());
    expect(() => editSessionReducer(frozen, {
      type, surface: SURFACE, zone: ZONE, mode: 'surface', floor: 2,
      value: true, hoveredId: 'H', editState: {}, lightCalc: {}, equipCalc: {},
    })).not.toThrow();
  });
});
