/**
 * state/appReducer.js — 묶음 조합.
 *
 * ⚠️ 여기의 존재 이유는 하나다: 모델을 갈아끼울 때 **편집 세션도 반드시 함께**
 * 초기화하는 것. 안 하면 새 건물에 이전 건물의 선택·층·초안이 남는다.
 *
 * 예전에는 이 연동을 App 안에서 두 dispatch 를 나란히 불러 처리했고, 그게
 * 지켜지는지는 **정규식 소스 검사**로만 확인했다(codex 지적). 이제 한 전이다.
 */
import { describe, expect, it } from 'vitest';
import {
  AppAction, MODEL_REPLACING_ACTIONS, appReducer, initialAppState,
  toEdit, toExec, toModel,
} from '../appReducer.js';
import { EditAction, initialEditSession } from '../editSession.js';
import { ExecAction } from '../execution.js';
import { ModelAction } from '../modelReducer.js';

const act = (s, a) => appReducer(s, a);

/** 봉투를 자동으로 씌운다 — 시험이 라우팅 세부를 반복하지 않게. */
function send(state, action) {
  if (Object.values(ModelAction).includes(action.type)) return act(state, toModel(action));
  if (Object.values(EditAction).includes(action.type)) return act(state, toEdit(action));
  if (Object.values(ExecAction).includes(action.type)) return act(state, toExec(action));
  return act(state, action);
}

/** 편집 중이고 모델도 실린 상태. */
function busy() {
  let s = act(initialAppState, {
    type: AppAction.MODEL_REPLACED,
    modelAction: {
      type: ModelAction.PARSE_SUCCEEDED,
      surfaces: [{ id: 'S1', wwr: 30, uValue: 0.5 }], zones: [{ id: 'Z1' }],
      floorLevels: 3,
    },
  });
  s = send(s, { type: EditAction.FLOOR_CHANGED, floor: 3 });
  s = send(s, { type: EditAction.SURFACE_SELECTED, surface: { id: 'S1', wwr: 30, uValue: 0.5 } });
  s = send(s, { type: EditAction.HOVER_CHANGED, hoveredId: 'S2' });
  return s;
}

describe('MODEL_REPLACED', () => {
  it.each(MODEL_REPLACING_ACTIONS)(
    '⚠️ %s 가 편집 세션을 함께 초기화한다', (type) => {
      const before = busy();
      expect(before.edit.selectedId).toBe('S1');   // 전제 확인

      const after = act(before, {
        type: AppAction.MODEL_REPLACED,
        modelAction: { type, surfaces: [], zones: [] },
      });
      expect(after.edit).toEqual(initialEditSession);
    });

  it('모델 전이도 실제로 일어난다', () => {
    const s = act(initialAppState, {
      type: AppAction.MODEL_REPLACED,
      modelAction: {
        type: ModelAction.PARSE_SUCCEEDED, surfaces: [{ id: 'S9' }], zones: [],
      },
    });
    expect(s.model.surfaces).toEqual([{ id: 'S9' }]);
  });

  it('실행 상태(step·결과)는 건드리지 않는다', () => {
    const before = send(busy(), { type: ExecAction.NAVIGATED, step: 'floorView' });
    const after = act(before, {
      type: AppAction.MODEL_REPLACED,
      modelAction: { type: ModelAction.MODEL_RESET },
    });
    expect(after.exec).toBe(before.exec);
  });
});

describe('묶음 분리', () => {
  it('모델 action 은 편집 세션을 건드리지 않는다', () => {
    const before = busy();
    const after = act(before, {
      type: ModelAction.SURFACE_EDIT_COMMITTED, surfaceId: 'S1', patch: { wwr: 40 } });
    expect(after.edit).toBe(before.edit);
  });

  it('편집 action 은 모델을 건드리지 않는다', () => {
    const before = busy();
    const after = send(before, { type: EditAction.HOVER_CHANGED, hoveredId: 'X' });
    expect(after.model).toBe(before.model);
  });

  it('실행 action 은 모델·편집을 건드리지 않는다', () => {
    const before = busy();
    const after = send(before, { type: ExecAction.NAVIGATED, step: 'result' });
    expect(after.model).toBe(before.model);
    expect(after.edit).toBe(before.edit);
  });

  it('알 수 없는 action 은 같은 객체를 돌려준다', () => {
    const s = busy();
    expect(act(s, { type: '없는액션' })).toBe(s);
  });
});

// ── 실행 상태머신 ────────────────────────────────────────

describe('시뮬레이션 실행', () => {
  const running = () => send(busy(), { type: ExecAction.SIMULATION_STARTED });

  it('시작하면 로딩 화면으로 가고 메시지가 처음부터다', () => {
    // ⚠️ 인덱스를 안 되돌리면 지난 실행의 마지막 문구부터 뜬다
    const ticked = send(busy(), { type: ExecAction.LOADING_MESSAGE_TICKED, lastIndex: 5 });
    const s = send(ticked, { type: ExecAction.SIMULATION_STARTED });
    expect(s.exec.step).toBe('loading');
    expect(s.exec.loadingMsgIdx).toBe(0);
    expect(s.exec.loadingStage).toBeNull();
  });

  it('⚠️ 성공은 결과·화면·로딩정리를 한 전이에서 한다', () => {
    const staged = send(running(), { type: ExecAction.LOADING_STAGE_CHANGED, stage: 'retrofit' });
    const result = { summary: {} };
    const s = send(staged, { type: ExecAction.SIMULATION_SUCCEEDED, result });
    expect(s.exec.res).toBe(result);
    expect(s.exec.step).toBe('result');
    expect(s.exec.loadingStage).toBeNull();
  });

  it('⚠️ 실패는 로딩에 가두지 않고 편집 화면으로 돌려보낸다', () => {
    const s = send(running(), { type: ExecAction.SIMULATION_FAILED });
    expect(s.exec.step).toBe('floorView');
    expect(s.exec.loadingStage).toBeNull();
  });

  it('⚠️ 실패가 지난 성공 결과를 지우지 않는다', () => {
    // 지우면 사용자가 비교 대상을 잃는다
    const ok = send(running(), { type: ExecAction.SIMULATION_SUCCEEDED, result: { a: 1 } });
    const failed = act(send(ok, { type: ExecAction.SIMULATION_STARTED }),
                       { type: ExecAction.SIMULATION_FAILED });
    expect(failed.exec.res).toEqual({ a: 1 });
  });

  it('메시지 인덱스가 상한을 넘지 않는다', () => {
    let s = running();
    for (let i = 0; i < 20; i += 1) {
      s = send(s, { type: ExecAction.LOADING_MESSAGE_TICKED, lastIndex: 3 });
    }
    expect(s.exec.loadingMsgIdx).toBe(3);
  });
});

describe('파싱 단계', () => {
  it('시작하면 parsing 화면', () => {
    expect(send(initialAppState, { type: ExecAction.PARSE_STARTED }).exec.step).toBe('parsing');
  });

  it('성공하면 upload 로 돌아간다', () => {
    const p = send(initialAppState, { type: ExecAction.PARSE_STARTED });
    expect(send(p, { type: ExecAction.PARSE_SETTLED, ok: true }).exec.step).toBe('upload');
  });

  it('⚠️ 실패하면 parsing 에 머문다', () => {
    // 오류 화면이 그 단계 안에 있다 — upload 로 넘기면 아무 안내도 못 받고 튕긴다
    const p = send(initialAppState, { type: ExecAction.PARSE_STARTED });
    expect(send(p, { type: ExecAction.PARSE_SETTLED, ok: false }).exec.step).toBe('parsing');
  });
});

// ── action 라우팅 ────────────────────────────────────────
// ⚠️ 봉투를 쓰기 **전에는** action 값이 겹치면 조용히 다른 reducer 로 갔다
// (실제로 `PARSE_STARTED` 가 두 묶음에 있어 한쪽 값을 바꿔야 했다).
// 이제는 **값이 같아도** 봉투가 라우팅을 정한다 — 그것을 시험한다.

describe('봉투가 라우팅을 정한다', () => {
  it('⚠️ 같은 action 값이어도 봉투대로 간다', () => {
    // 두 묶음이 같은 문자열을 써도 서로를 침범하지 않아야 한다
    const before = busy();
    const shared = { type: ModelAction.PARSE_FAILED, message: 'x' };

    const asModel = act(before, toModel(shared));
    expect(asModel.model.uploadError).toBe('x');
    expect(asModel.edit).toBe(before.edit);

    // edit reducer 는 이 값을 모르므로 아무것도 안 바꾼다
    const asEdit = act(before, toEdit(shared));
    expect(asEdit.model).toBe(before.model);
    expect(asEdit.edit).toBe(before.edit);
  });

  it.each([
    ['model', toModel, { type: ModelAction.WARNINGS_DISMISSED }],
    ['edit', toEdit, { type: EditAction.SELECTION_CLEARED }],
    ['exec', toExec, { type: ExecAction.NAVIGATED, step: 'result' }],
  ])('%s 봉투는 자기 묶음만 바꾼다', (group, wrap, action) => {
    const before = busy();
    const after = act(before, wrap(action));
    for (const other of ['model', 'edit', 'exec'].filter((g) => g !== group)) {
      expect(after[other]).toBe(before[other]);
    }
  });

  it('봉투 없는 action 은 아무것도 안 바꾼다', () => {
    const s = busy();
    expect(act(s, { type: ModelAction.WARNINGS_DISMISSED })).toBe(s);
  });
});

// ── 모델 교체 시 결과 무효화 ─────────────────────────────

describe('MODEL_REPLACED 가 이전 결과를 버린다', () => {
  const withResult = () => send(busy(), {
    type: ExecAction.SIMULATION_SUCCEEDED, result: { surfaceThermal: { S1: {} } } });

  it.each(MODEL_REPLACING_ACTIONS)('⚠️ %s 후 res 가 남지 않는다', (type) => {
    // 남으면 새 건물의 3D 뷰가 **옛 건물의 면별 결과**로 칠해지고,
    // 결과 화면으로 돌아가면 다른 건물의 숫자를 본다.
    const before = withResult();
    expect(before.exec.res).not.toBeNull();

    const after = act(before, {
      type: AppAction.MODEL_REPLACED,
      modelAction: { type, surfaces: [], zones: [] },
    });
    expect(after.exec.res).toBeNull();
  });

  it('⚠️ 결과 화면에 있었다면 빈 결과 화면으로 남기지 않는다', () => {
    // 결과만 지우고 화면을 그대로 두면 **0 으로 채워진 결과 화면**이 남는다
    const s = act(withResult(), {
      type: AppAction.MODEL_REPLACED, modelAction: { type: ModelAction.MODEL_RESET } });
    expect(s.exec.step).not.toBe('result');
  });

  it('결과 화면이 아니면 단계를 건드리지 않는다', () => {
    const editing = send(withResult(), { type: ExecAction.NAVIGATED, step: 'floorView' });
    const s = act(editing, {
      type: AppAction.MODEL_REPLACED, modelAction: { type: ModelAction.MODEL_RESET } });
    expect(s.exec.step).toBe('floorView');
  });

  it('결과가 없으면 exec 를 건드리지 않는다', () => {
    const before = busy();
    const after = act(before, {
      type: AppAction.MODEL_REPLACED, modelAction: { type: ModelAction.MODEL_RESET } });
    expect(after.exec).toBe(before.exec);
  });
});
