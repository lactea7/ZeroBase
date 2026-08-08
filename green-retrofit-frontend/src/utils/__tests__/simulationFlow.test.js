/**
 * utils/simulationFlow.js — 시뮬레이션 실행의 화면 전환 계약.
 *
 * ⚠️ 사용자가 **30분을 기다리는 경로**다. 화면 하나를 잘못 넘기거나 정리를
 * 빠뜨리면 로딩이 안 끝나거나, 실패했는데 이유 없이 편집 화면으로 돌아간다.
 *
 * UI 경로(landing→…→floorView)를 태우지 않고 계약만 본다 — 긴 경로를 태우면
 * 시험이 취약해진다(codex 조언).
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { runSimulationFlow } from '../simulationFlow.js';

const PAYLOAD = { projectData: {}, zones: [], surfaces: [] };

function makeActions() {
  return {
    onStarted: vi.fn(),
    onStage: vi.fn(),
    onSucceeded: vi.fn(),
    onFailed: vi.fn(),
    startTicker: vi.fn(),
    stopTicker: vi.fn(),
  };
}

/** 원할 때 resolve/reject 할 수 있는 러너. */
function deferredRunner() {
  let resolve, reject;
  const runner = vi.fn(() => new Promise((res, rej) => { resolve = res; reject = rej; }));
  runner.resolve = (v) => resolve(v);
  runner.reject = (e) => reject(e);
  return runner;
}

let onError;
beforeEach(() => { onError = vi.fn(); });

describe('시작', () => {
  it('호출 즉시 로딩 화면으로 넘긴다', async () => {
    const actions = makeActions();
    const runner = deferredRunner();
    const p = runSimulationFlow(PAYLOAD, runner, actions, onError);

    // ⚠️ 결과를 기다리기 **전에** 넘어가야 한다. 안 그러면 사용자는 30분간
    // 아무 반응 없는 화면을 본다.
    expect(actions.onStarted).toHaveBeenCalled();
    expect(actions.startTicker).toHaveBeenCalled();

    runner.resolve({ result: {} });
    await p;
  });

  it('payload 와 단계 콜백을 그대로 넘긴다', async () => {
    const actions = makeActions();
    const runner = vi.fn().mockResolvedValue({ result: {} });
    await runSimulationFlow(PAYLOAD, runner, actions, onError);

    expect(runner).toHaveBeenCalledWith(PAYLOAD, actions.onStage);
  });
});

describe('성공', () => {
  it('결과를 싣고 결과 화면으로 넘긴다', async () => {
    const actions = makeActions();
    const result = { summary: { consume_per_m2: 100 } };
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result }), actions, onError);

    expect(actions.onSucceeded).toHaveBeenCalledWith(result);
  });

  it('타이머를 정리한다', async () => {
    // ⚠️ 안 하면 결과 화면에서 로딩 문구가 계속 돈다
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }), actions, onError);
    expect(actions.stopTicker).toHaveBeenCalled();
  });

  it('오류 안내를 내지 않는다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }), actions, onError);
    expect(onError).not.toHaveBeenCalled();
  });
});

describe('실패', () => {
  it('원인을 그대로 안내한다', async () => {
    // ⚠️ 삼키면 사용자는 무엇을 고쳐야 할지 모른다
    const actions = makeActions();
    await runSimulationFlow(
      PAYLOAD, vi.fn().mockRejectedValue(new Error('동시 실행 한도를 초과했습니다')),
      actions, onError);

    expect(onError).toHaveBeenCalledTimes(1);
    expect(onError.mock.calls[0][0]).toContain('동시 실행 한도를 초과했습니다');
  });

  it('원인이 없어도 안내는 낸다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue({}), actions, onError);
    expect(onError).toHaveBeenCalled();
  });

  it('⚠️ 로딩 화면에 가두지 않고 실패 전이를 낸다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError);
    expect(actions.onFailed).toHaveBeenCalled();
  });

  it('실패해도 타이머를 정리한다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError);
    expect(actions.stopTicker).toHaveBeenCalled();
  });

  it('실패 시 결과를 싣지 않는다', async () => {
    // ⚠️ 예전 결과가 남아 있으면 실패했는데 성공한 것처럼 보인다
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError);
    expect(actions.onSucceeded).not.toHaveBeenCalled();
  });

  it('예외를 밖으로 던지지 않는다', async () => {
    const actions = makeActions();
    await expect(
      runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError),
    ).resolves.toBeNull();
  });
});

// ── 타이머 정리 (finally) ────────────────────────────────
// ⚠️ 예전엔 try/catch 양쪽에서 각각 껐다. 그러면 `onSucceeded` 가 던졌을 때
// **백엔드 실패로 오인**해 `onFailed` 를 부르고 타이머도 남는다(codex 지적).

describe('타이머 정리', () => {
  it('실패해도 끈다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')),
                            actions, onError);
    expect(actions.stopTicker).toHaveBeenCalled();
  });

  it('성공 경로에서도 끈다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }),
                            actions, onError);
    expect(actions.stopTicker).toHaveBeenCalled();
  });
});

// ── 화면 오류를 백엔드 실패로 위장하지 않는다 ────────────
// ⚠️ 예전엔 전체를 try/catch 로 묶어서, `onSucceeded()`(화면 갱신)가 던져도
// 오류 안내를 띄우고 `onFailed()` 로 편집 화면에 돌려보냈다 — 시뮬레이션은
// 성공했는데 실패했다고 알리는 셈이다(codex 지적).

describe('화면 오류 ≠ 백엔드 실패', () => {
  function throwingSuccess() {
    const actions = makeActions();
    actions.onSucceeded.mockImplementation(() => { throw new Error('렌더 오류'); });
    return actions;
  }

  it('⚠️ 성공 처리가 던져도 실패 안내를 하지 않는다', async () => {
    const actions = throwingSuccess();
    await expect(runSimulationFlow(
      PAYLOAD, vi.fn().mockResolvedValue({ result: {} }), actions, onError,
    )).rejects.toThrow('렌더 오류');
    expect(onError).not.toHaveBeenCalled();
  });

  it('⚠️ 성공 처리가 던져도 편집 화면으로 돌려보내지 않는다', async () => {
    const actions = throwingSuccess();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }),
                            actions, onError).catch(() => {});
    expect(actions.onFailed).not.toHaveBeenCalled();
  });

  it('그래도 타이머는 끈다', async () => {
    const actions = throwingSuccess();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }),
                            actions, onError).catch(() => {});
    expect(actions.stopTicker).toHaveBeenCalled();
  });
});
