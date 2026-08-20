// utils/loadingStage.js — 백엔드 진행 단계 → 사용자 문구.
//
// ⚠️ 사용자가 여기서 **최대 30분**을 기다린다. 문구가 사라지면 멈춘 것인지 도는
// 것인지 알 수 없어 창을 닫는다 — 그러면 30분이 버려진다.

/** 백엔드 `stage` 값을 화면 문구로 옮긴다. **빈 문자열을 내면 안 된다.** */
export function stageMessage(loadingStage) {
  // ⚠️ 배포(Render 무료)는 15분 무요청이면 잠든다. 깨우는 데 **실측 32.7초**가
  // 걸리는데 그동안 문구가 없으면 멈춘 것처럼 보인다.
  if (loadingStage === 'waking') return '서버를 깨우는 중... (첫 요청은 30초 이상 걸릴 수 있습니다)';
  // ⚠️ 상태 조회가 일시적으로 실패한 것이지 계산이 멈춘 게 아니다.
  // 여기서 실패 문구를 내면 사용자가 창을 닫아 진행 중인 계산을 버린다.
  if (loadingStage === 'reconnecting') return '서버 응답을 기다리는 중... (계산은 계속 진행됩니다)';
  if (loadingStage === 'queued') return '대기열에서 순서를 기다리는 중...';
  if (loadingStage === 'baseline') return '1/2단계 — 개선 전(원본) 건물 시뮬레이션 중';
  if (loadingStage === 'retrofit') return '개선안 건물 시뮬레이션 중';
  if (loadingStage?.startsWith('alt:')) {
    return '추가 절감 대안의 에너지 영향 계산 중 (대안별 재시뮬레이션)';
  }
  // ⚠️ 단계를 모를 때도 문구를 낸다 — 비우면 멈춘 것처럼 보인다.
  return 'EnergyPlus 물리 엔진 가동 중';
}
