// gbXML 평면 다각형 → Three.js 삼각형 목록.
//
// ⚠️ **정점 0 부채꼴(triangle fan)로 자르면 안 된다.** 부채꼴은 볼록 다각형에만
// 유효하고, 오목 다각형에서는 삼각형이 다각형 **바깥으로 삐져나간다.**
// 실측(용호동 파일 2.xml): 235면 중 17면이 어긋났고 최악은 면적이 4.8배로 그려졌다.
//
//   su-b-204-204-i-f-105   진짜  27.8㎡ → 부채꼴 133.9㎡ (+382%)
//   su-x-s-235             진짜  87.9㎡ → 부채꼴 148.4㎡  (+69%)
//   su-b-104-104-i-f-43    진짜 111.6㎡ → 부채꼴 176.8㎡  (+58%)
//
// 삐져나간 삼각형의 바깥 변은 이웃 삼각형과 공유되지 않아 `EdgesGeometry` 가
// 숨기지 못하고 그린다 — 화면에서 건물을 가로지르는 긴 대각선이 그것이다.
// **선만 고치면 면은 여전히 잘못 칠해진다.** 삼각분할 자체를 바꿔야 한다.
//
// 백엔드는 이 문제가 없다. 면적은 뉴웰 법선으로 구하고 IDF 에는 원본 좌표가
// 그대로 나가므로, 이건 뷰어 전용 결함이다.

import { calculateSurfaceArea } from './geometry.js';

/** 뉴웰 법선. 비평면 다각형에서도 안정적이다. */
export const newellNormal = (verts) => {
  let nx = 0, ny = 0, nz = 0;
  for (let i = 0; i < verts.length; i++) {
    const a = verts[i], b = verts[(i + 1) % verts.length];
    nx += (a[1] - b[1]) * (a[2] + b[2]);
    ny += (a[2] - b[2]) * (a[0] + b[0]);
    nz += (a[0] - b[0]) * (a[1] + b[1]);
  }
  const m = Math.hypot(nx, ny, nz);
  return m > 0 ? [nx / m, ny / m, nz / m] : [0, 0, 1];
};

// ⚠️ 면적은 **여기서 다시 구현하지 않는다.** `utils/geometry.js` 의
// `calculateSurfaceArea` 가 정본이고, 백엔드
// `simulation/geometry.calculate_surface_area` 와 같은 산식임을 참조값 시험이
// 대조한다. 같은 계산을 세 군데 두면 갈라지는 건 시간문제다(codex 지적).
export const polygonArea3D = calculateSurfaceArea;

/**
 * 다각형 평면 위의 2D 좌표계로 투영한다.
 * ⚠️ 축 정렬 면(바닥은 법선이 ±Z)에서 기준 벡터가 법선과 나란해지면 축이 무너진다.
 * 법선의 **최소 성분** 축을 골라 그 위험을 없앤다.
 */
const projectTo2D = (verts) => {
  const n = newellNormal(verts);
  const ax = Math.abs(n[0]), ay = Math.abs(n[1]), az = Math.abs(n[2]);
  const seed = ax <= ay && ax <= az ? [1, 0, 0] : ay <= az ? [0, 1, 0] : [0, 0, 1];
  let u = [
    seed[1] * n[2] - seed[2] * n[1],
    seed[2] * n[0] - seed[0] * n[2],
    seed[0] * n[1] - seed[1] * n[0],
  ];
  const um = Math.hypot(...u);
  u = um > 0 ? u.map((c) => c / um) : [1, 0, 0];
  const v = [
    n[1] * u[2] - n[2] * u[1],
    n[2] * u[0] - n[0] * u[2],
    n[0] * u[1] - n[1] * u[0],
  ];
  return verts.map((p) => [
    p[0] * u[0] + p[1] * u[1] + p[2] * u[2],
    p[0] * v[0] + p[1] * v[1] + p[2] * v[2],
  ]);
};

const signedArea2D = (pts) => {
  let s = 0;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    s += a[0] * b[1] - b[0] * a[1];
  }
  return s / 2;
};

const pointInTriangle = (p, a, b, c) => {
  const d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1]);
  if (Math.abs(d) < 1e-12) return false;
  const s = ((b[1] - c[1]) * (p[0] - c[0]) + (c[0] - b[0]) * (p[1] - c[1])) / d;
  const t = ((c[1] - a[1]) * (p[0] - c[0]) + (a[0] - c[0]) * (p[1] - c[1])) / d;
  return s > 1e-9 && t > 1e-9 && s + t < 1 - 1e-9;
};

/**
 * 평면 다각형을 삼각형 인덱스 배열로 자른다 (ear clipping).
 *
 * ⚠️ **계약을 정확히 적는다**(codex 지적): 이 함수는 "다각형 안쪽만 덮는다"를
 * **보장하지 않는다.** `pointInTriangle` 이 경계 위의 정점을 바깥으로 치므로,
 * ear 대각선이 비인접 변에 맞닿는 경우 잘못된 ear 를 허용할 수 있다. 자기교차
 * 사전 검출도 하지 않는다.
 * 보장되는 것은 `buildSurfaceGeometry` 가 얹는 **면적 검증을 통과한 후보**라는
 * 것뿐이다. 겹침과 누락이 서로 상쇄되면 면적만으로는 못 잡는다 — 그 한계를
 * 알고 쓰라. (제대로 된 기하 검사는 별도 작업으로 미뤘다.)
 *
 * @returns {number[]} 길이 3N 의 인덱스 배열. 실패하면 빈 배열.
 */
export const triangulatePolygon = (verts) => {
  if (!verts || verts.length < 3) return [];
  if (verts.length === 3) {
    // ⚠️ 삼각형이라고 무조건 통과시키면 **공선 3점**이 면적 0 짜리 삼각형으로
    // 들어가고, `buildSurfaceGeometry` 는 area 0 == drawnArea 0 이라 `ok: true`
    // 로 판정한다 — 퇴화 형상이 "성한 면"으로 보고된다(codex 지적).
    const p = projectTo2D(verts);
    const cross = (p[1][0] - p[0][0]) * (p[2][1] - p[0][1])
      - (p[1][1] - p[0][1]) * (p[2][0] - p[0][0]);
    return Math.abs(cross) > 1e-12 ? [0, 1, 2] : [];
  }

  const pts = projectTo2D(verts);
  // 반시계로 맞춘다 — ear 판정이 감김 방향에 의존한다.
  let idx = pts.map((_, i) => i);
  if (signedArea2D(pts) < 0) idx.reverse();

  const out = [];
  let guard = idx.length * idx.length + 16;   // 무한루프 방지

  // `relaxed` 는 **공선 정점**을 위한 2차 패스다.
  // ⚠️ 실측: 용호동의 `su-t-101-201-i-f-14` 등 4면은 한 직선 위에 정점이 4개
  // 늘어서 있다(y=2.85 에 4개). 엄격 패스는 그 지점의 cross 가 0 이라 ear 로
  // 인정하지 않고, 그런 정점만 남으면 진행이 멈춘다. 공선 정점을 떼어내는 건
  // 면적을 바꾸지 않으므로(퇴화 삼각형 = 0㎡) 안전하다.
  const findEar = (relaxed) => {
    for (let i = 0; i < idx.length; i++) {
      const ia = idx[(i + idx.length - 1) % idx.length];
      const ib = idx[i];
      const ic = idx[(i + 1) % idx.length];
      const a = pts[ia], b = pts[ib], c = pts[ic];
      // 볼록 꼭짓점인가 (반시계 기준 좌회전)
      const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
      if (relaxed ? cross < -1e-12 : cross <= 1e-12) continue;
      // ⚠️ 공선 정점을 뗄 때는 그것이 a~c **사이**에 있어야 한다. 밖으로 튀어나온
      // 바늘 모양이면 떼는 순간 형상이 달라진다.
      if (Math.abs(cross) <= 1e-12) {
        const dot = (b[0] - a[0]) * (c[0] - a[0]) + (b[1] - a[1]) * (c[1] - a[1]);
        const len2 = (c[0] - a[0]) ** 2 + (c[1] - a[1]) ** 2;
        if (!(dot >= -1e-12 && dot <= len2 + 1e-12)) continue;
      } else {
        // 다른 정점을 품고 있으면 ear 가 아니다
        let contains = false;
        for (let j = 0; j < idx.length; j++) {
          const k = idx[j];
          if (k === ia || k === ib || k === ic) continue;
          if (pointInTriangle(pts[k], a, b, c)) { contains = true; break; }
        }
        if (contains) continue;
      }
      return { i, tri: [ia, ib, ic], degenerate: Math.abs(cross) <= 1e-12 };
    }
    return null;
  };

  while (idx.length > 3 && guard-- > 0) {
    const ear = findEar(false) || findEar(true);
    // ⚠️ 자기교차 등으로 끝내 ear 를 못 찾으면 **부채꼴로 되돌아가지 않는다.**
    // 조용히 틀린 면적을 그리느니 그 면을 포기하는 편이 낫다 — 호출자가
    // 빈 배열을 보고 결정한다.
    if (!ear) return [];
    if (!ear.degenerate) out.push(...ear.tri);   // 퇴화 삼각형은 버린다
    idx.splice(ear.i, 1);
  }
  // ⚠️ 마지막 삼각형도 퇴화 검사를 한다(codex 지적). 남은 3점이 한 직선 위면
  // 면적 0 짜리 삼각형이 들어가고, 그 변이 `EdgesGeometry` 시절처럼 선으로 튄다.
  if (idx.length === 3) {
    const a = pts[idx[0]], b = pts[idx[1]], c = pts[idx[2]];
    const cross = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
    if (Math.abs(cross) > 1e-12) out.push(idx[0], idx[1], idx[2]);
  }
  return out;
};

/**
 * 면을 그릴 삼각형과, 그 결과를 **믿어도 되는지**를 함께 돌려준다.
 *
 * ⚠️ 삼각분할이 원래 면적과 어긋나면 그 다각형은 성한 모양이 아니다.
 * 실측(회의실.xml 1,230면 중 5면): 폭 0.15m 짜리 긴 슬릿처럼 CAD 가 내보낸
 * 퇴화 형상이다. 이럴 때 **면을 칠하지 않는다** — 잘못된 덩어리를 조용히
 * 그리느니 윤곽선만 남기고 사실을 알리는 편이 낫다.
 *
 * @returns {{triangles:number[], ok:boolean, area:number, drawnArea:number}}
 */
export const buildSurfaceGeometry = (verts, tolerance = 0.01) => {
  const area = polygonArea3D(verts);
  // ⚠️ 면적이 0 인 다각형은 `|0 − 0| <= tol × 0` 이라 **검증을 통과해 버린다.**
  // 퇴화 형상을 성한 면으로 보고하지 않으려면 먼저 걸러야 한다.
  if (!(area > 1e-9)) {
    return { triangles: [], ok: false, area, drawnArea: 0 };
  }
  const triangles = triangulatePolygon(verts);
  if (triangles.length === 0) {
    return { triangles: [], ok: false, area, drawnArea: 0 };
  }
  const drawnArea = triangulatedArea3D(verts, triangles);
  const ok = Math.abs(drawnArea - area) <= tolerance * Math.max(area, 1e-9);
  return { triangles: ok ? triangles : [], ok, area, drawnArea };
};

/**
 * 삼각분할 결과의 면적. 검증용 — 올바르면 `polygonArea3D` 와 같아야 한다.
 * ⚠️ 이 등식이 이 모듈의 계약이다. 시험이 이걸 고정한다.
 */
export const triangulatedArea3D = (verts, tris) => {
  let sum = 0;
  for (let i = 0; i < tris.length; i += 3) {
    const a = verts[tris[i]], b = verts[tris[i + 1]], c = verts[tris[i + 2]];
    const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
    const w = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
    sum += Math.hypot(
      u[1] * w[2] - u[2] * w[1],
      u[2] * w[0] - u[0] * w[2],
      u[0] * w[1] - u[1] * w[0],
    ) / 2;
  }
  return sum;
};
