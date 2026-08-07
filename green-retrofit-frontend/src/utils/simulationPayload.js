// utils/simulationPayload.js — 백엔드로 보내는 시뮬레이션 요청 조립.
//
// ⚠️ **백엔드와의 계약이다.** 키 하나가 빠지거나 위치가 틀리면 백엔드가 조용히
// 기본값으로 돌아가고, 화면엔 정상처럼 보이는 결과가 나온다.
//
// `App.handleSimulation` 안에 있던 것을 옮겼다. 순수 함수라 화면 없이 시험할 수 있다.

/**
 * 실측 기준선 입력에서 **선택한 모드의 필드만** 남긴다.
 *
 * ⚠️ 두 모드의 값을 다 보내면 백엔드의 우선순위 판단이 뒤집힌다. 사용자가
 * 요금 모드로 바꿔도 예전에 입력한 사용량이 남아 그쪽이 기준선이 된다.
 */
export function pickBaselineActual(baselineActual) {
  const ba = baselineActual || {};
  return ba.mode === 'usage'
    ? { mode: 'usage', elecKwh: ba.elecKwh, heatKwh: ba.heatKwh }
    : { mode: 'bill', elecBill: ba.elecBill, heatBill: ba.heatBill };
}

/**
 * 시뮬레이션 요청 payload.
 *
 * ⚠️ `lccParameters` / `hvacUpgradeActive` 는 **`projectData` 안에** 있어야 한다.
 * 최상위로 올리면 백엔드 `SimulationPayload` 가 그 키를 모르고 통째로 버린다 —
 * 할인율·분석기간이 조용히 기본값으로 돌아간다.
 */
export function buildSimulationPayload({
  projectData, zones, surfaces, materials, constructionOverrides, originalModel,
}) {
  return {
    projectData: {
      ...projectData,
      baselineActual: pickBaselineActual(projectData?.baselineActual),
    },
    zones,
    surfaces,
    materials,
    constructionOverrides,
    // 전/후 비교: 업로드 원본을 함께 보내 백엔드가 '개선 전' 건물을 별도 시뮬레이션한다.
    // (실측 요금이 입력되면 백엔드가 전-시뮬을 생략하고 실측을 기준선으로 쓴다)
    baselineModel: originalModel || {},
  };
}
