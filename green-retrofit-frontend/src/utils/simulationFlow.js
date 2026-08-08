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
 * @param actions   화면 전환 콜백 묶음. 각각이 **하나의 상태 전이**에 대응한다
 *                  (`onStarted`/`onStage`/`onSucceeded`/`onFailed`) — 예전처럼
 *                  setter 를 낱개로 받으면 정리를 빠뜨리기 쉽다.
 * @param onError   실패 안내(기본 `alert`) — 시험에서 갈아끼운다
 */
export async function runSimulationFlow(payload, runner, actions, onError = null) {
  const {
    onStarted, onStage, onSucceeded, onFailed, startTicker, stopTicker,
  } = actions;

  onStarted();
  startTicker?.();

  try {
    let response;
    // ⚠️ **`runner()` 만 감싼다.** 예전엔 전체를 try/catch 로 묶어서,
    // `onSucceeded()`(화면 갱신)가 던져도 **백엔드 실패로 오인**해 오류 안내를
    // 띄우고 `onFailed()` 로 편집 화면에 돌려보냈다(codex 지적).
    // 시뮬레이션은 성공했는데 실패했다고 알리는 셈이다.
    try {
      response = await runner(payload, onStage);
    } catch (error) {
      // ⚠️ 원인을 삼키면 사용자는 무엇을 고쳐야 할지 모른다.
      const detail = error?.message ? `\n\n원인: ${error.message}` : '';
      (onError || globalThis.alert)(
        `시뮬레이션에 실패했습니다. 백엔드 서버 상태를 확인하세요.${detail}`);
      // ⚠️ 로딩 화면에 갇히면 안 된다 — 편집 화면으로 돌려보내 다시 시도하게 한다.
      onFailed();
      return null;
    }

    // 여기서 던지는 것은 **화면 쪽 문제**다. 백엔드 실패로 위장하지 않는다.
    onSucceeded(response.result);
    // 결과 탭 초기화는 하지 않는다 — 결과 화면이 unmount 되므로 다시 성공하면
    // 자연히 첫 탭으로 돌아간다. 여기서 되돌리면 남의 상태를 만지는 셈이다.
    return response;
  } finally {
    // 성공·실패·예외 어느 쪽이든 타이머를 끈다. 안 하면 로딩 문구가 계속 돈다.
    stopTicker?.();
  }
}
