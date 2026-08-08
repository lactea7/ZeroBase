// utils/geometry.js — 면 기하 계산.
//
// ⚠️ **백엔드 `ep_simulator.calculate_surface_area` 와 같은 산식이어야 한다.**
// 갈라지면 화면에 보이는 면적과 시뮬레이션이 쓰는 면적이 달라진다.

export function calculateSurfaceArea(vertices) {
    if (!vertices || vertices.length < 3) return 0;
    let area = 0;
    const v0 = vertices[0];
    for (let i = 1; i < vertices.length - 1; i++) {
      const v1 = vertices[i];
      const v2 = vertices[i + 1];
      const ux = v1[0] - v0[0];
      const uy = v1[1] - v0[1];
      const uz = v1[2] - v0[2];
      const vx = v2[0] - v0[0];
      const vy = v2[1] - v0[1];
      const vz = v2[2] - v0[2];
      const cx = uy * vz - uz * vy;
      const cy = uz * vx - ux * vz;
      const cz = ux * vy - uy * vx;
      area += 0.5 * Math.sqrt(cx * cx + cy * cy + cz * cz);
    }
    return area;
}
