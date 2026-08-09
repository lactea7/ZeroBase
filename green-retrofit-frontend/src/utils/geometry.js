// utils/geometry.js — 면 기하 계산.
//
// ⚠️ **백엔드 `simulation/geometry.calculate_surface_area` 와 같은 산식이어야
// 한다.** 갈라지면 화면에 보이는 면적과 시뮬레이션이 쓰는 면적이 달라진다.
// `src/utils/__tests__/geometry.test.js` 가 백엔드 생성 참조값으로 대조한다.

/**
 * 3D 다각형 면적 (Newell 법선 길이 ÷ 2).
 *
 * ⚠️ 예전에는 **삼각형 fan 면적의 절댓값 합**이었다. 볼록 사각형에서는 같지만
 * **오목 다각형에서 과대**하게 나온다 — 되접히는 삼각형이 빼지지 않고 더해진다.
 * gbXML 은 L 자 평면 같은 오목 폴리곤을 흔히 내보내므로 실재하는 차이다.
 */
export function calculateSurfaceArea(vertices) {
  if (!vertices || vertices.length < 3) return 0;

  let nx = 0;
  let ny = 0;
  let nz = 0;
  for (let i = 0; i < vertices.length; i += 1) {
    const v1 = vertices[i];
    const v2 = vertices[(i + 1) % vertices.length];
    nx += (v1[1] - v2[1]) * (v1[2] + v2[2]);
    ny += (v1[2] - v2[2]) * (v1[0] + v2[0]);
    nz += (v1[0] - v2[0]) * (v1[1] + v2[1]);
  }
  return Math.sqrt(nx * nx + ny * ny + nz * nz) / 2;
}
