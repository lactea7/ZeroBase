// utils/simulationFlow.js — 시뮬레이션 실행의 화면 전환 계약.
//
// ⚠️ 이 흐름은 사용자가 **30분을 기다리는 경로**다. 화면 하나를 잘못 넘기거나
// 정리를 빠뜨리면 로딩이 안 끝나거나, 실패했는데 이유 없이 편집 화면으로 돌아간다.
//
// `App.handleSimulation` 에 있던 것을 옮겼다. UI 경로(landing→…→floorView)를 타지
// 않고 이 계약만 시험한다 — 긴 경로를 태우면 시험이 취약해진다.

/**
 * 시뮬레이션을 실행하고 결과에 따라 화면을 넘긴다.
 *
 * @param payload   `buildSimulationPayload()` 결과
 * @param runner    `runSimulation(payload, onStage)` — 주입해서 시험 가능하게
 * @param actions   화면 전환·상태 갱신 콜백 묶음
 * @param onError   실패 안내(기본 `alert`) — 시험에서 갈아끼운다
 */
export async function runSimulationFlow(payload, runner, actions, onError = null) {
  const {
    setStep, setRes, setLoadingStage, setActiveResultTab, startTicker, stopTicker,
  } = actions;

  setStep('loading');
  startTicker?.();

  try {
    const response = await runner(payload, setLoadingStage);
    // ⚠️ 성공·실패 어느 쪽이든 타이머와 단계 표시를 **반드시** 정리한다.
    // 안 하면 결과 화면에서 로딩 문구가 계속 돌고 타이머가 남는다.
    stopTicker?.();
    setLoadingStage(null);
    setRes(response.result);
    setStep('result');
    // 시뮬레이션 직후에는 에너지 탭이 먼저 보여야 한다 — 이전 탭이 남으면
    // 사용자가 방금 돌린 결과를 못 찾는다.
    setActiveResultTab('energy');
    return response;
  } catch (error) {
    stopTicker?.();
    setLoadingStage(null);
    // ⚠️ 원인을 삼키면 사용자는 무엇을 고쳐야 할지 모른다.
    const detail = error?.message ? `\n\n원인: ${error.message}` : '';
    (onError || globalThis.alert)(
      `시뮬레이션에 실패했습니다. 백엔드 서버 상태를 확인하세요.${detail}`);
    // ⚠️ 로딩 화면에 갇히면 안 된다 — 편집 화면으로 돌려보내 다시 시도하게 한다.
    setStep('floorView');
    return null;
  }
}
