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
    setStep: vi.fn(),
    setRes: vi.fn(),
    setLoadingStage: vi.fn(),
    setActiveResultTab: vi.fn(),
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
    expect(actions.setStep).toHaveBeenCalledWith('loading');
    expect(actions.startTicker).toHaveBeenCalled();

    runner.resolve({ result: {} });
    await p;
  });

  it('payload 와 단계 콜백을 그대로 넘긴다', async () => {
    const actions = makeActions();
    const runner = vi.fn().mockResolvedValue({ result: {} });
    await runSimulationFlow(PAYLOAD, runner, actions, onError);

    expect(runner).toHaveBeenCalledWith(PAYLOAD, actions.setLoadingStage);
  });
});

describe('성공', () => {
  it('결과를 싣고 결과 화면으로 넘긴다', async () => {
    const actions = makeActions();
    const result = { summary: { consume_per_m2: 100 } };
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result }), actions, onError);

    expect(actions.setRes).toHaveBeenCalledWith(result);
    expect(actions.setStep).toHaveBeenLastCalledWith('result');
  });

  it('에너지 탭을 먼저 보여준다', async () => {
    // ⚠️ 이전 탭이 남으면 사용자가 방금 돌린 결과를 못 찾는다
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }), actions, onError);
    expect(actions.setActiveResultTab).toHaveBeenCalledWith('energy');
  });

  it('타이머와 단계 표시를 정리한다', async () => {
    // ⚠️ 안 하면 결과 화면에서 로딩 문구가 계속 돈다
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockResolvedValue({ result: {} }), actions, onError);
    expect(actions.stopTicker).toHaveBeenCalled();
    expect(actions.setLoadingStage).toHaveBeenCalledWith(null);
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

  it('⚠️ 로딩 화면에 가두지 않고 편집 화면으로 돌려보낸다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError);
    expect(actions.setStep).toHaveBeenLastCalledWith('floorView');
  });

  it('실패해도 타이머와 단계 표시를 정리한다', async () => {
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError);
    expect(actions.stopTicker).toHaveBeenCalled();
    expect(actions.setLoadingStage).toHaveBeenCalledWith(null);
  });

  it('실패 시 결과를 싣지 않는다', async () => {
    // ⚠️ 예전 결과가 남아 있으면 실패했는데 성공한 것처럼 보인다
    const actions = makeActions();
    await runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError);
    expect(actions.setRes).not.toHaveBeenCalled();
  });

  it('예외를 밖으로 던지지 않는다', async () => {
    const actions = makeActions();
    await expect(
      runSimulationFlow(PAYLOAD, vi.fn().mockRejectedValue(new Error('x')), actions, onError),
    ).resolves.toBeNull();
  });
});
