import { describe, it, expect } from 'vitest';
import {
  triangulatePolygon,
  triangulatedArea3D,
  polygonArea3D,
  buildSurfaceGeometry,
  newellNormal,
} from '../polygonGeometry';

// 뷰어가 예전에 쓰던 방식. 비교 기준으로만 둔다.
const fanArea = (verts) => {
  let sum = 0;
  for (let i = 1; i < verts.length - 1; i++) {
    const a = verts[0], b = verts[i], c = verts[i + 1];
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

const area = (verts) => triangulatedArea3D(verts, triangulatePolygon(verts));

describe('triangulatePolygon', () => {
  it('사각형은 그대로', () => {
    const sq = [[0, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]];
    expect(area(sq)).toBeCloseTo(20, 6);
    expect(area(sq)).toBeCloseTo(polygonArea3D(sq), 6);
  });

  it('⚠️ ㄱ자(오목) 면 — 부채꼴은 바깥을 칠하고, ear clipping 은 안 그런다', () => {
    // 6×6 정사각형에서 4×4 를 도려낸 ㄱ자 = 36 − 16 = 20
    // ⚠️ 정점 순서가 중요하다. 부채꼴은 **정점 0에서 다각형 전체가 보일 때만**
    // 우연히 맞는다. [0,0] 이나 [2,2] 에서 시작하면 20 이 나와서 결함이 안 보인다.
    // 아래 네 시작점은 전부 36(=바깥까지 칠함)이 된다.
    const ring = [[0, 0, 0], [6, 0, 0], [6, 2, 0], [2, 2, 0], [2, 6, 0], [0, 6, 0]];
    [1, 2, 4, 5].forEach((r) => {
      const L = [...ring.slice(r), ...ring.slice(0, r)];
      expect(polygonArea3D(L)).toBeCloseTo(20, 6);
      expect(area(L)).toBeCloseTo(20, 6);
      // 예전 방식은 오목부 바깥까지 칠했다 — 이 시험이 회귀를 막는다
      expect(fanArea(L)).toBeCloseTo(36, 6);
    });
  });

  it('⚠️ 바닥면(법선 ±Z)에서 투영축이 무너지지 않는다', () => {
    // 투영 기준 벡터를 법선과 나란히 잡으면 여기서 면적이 0 이 된다
    const floor = [[0, 0, 3], [4, 0, 3], [4, 5, 3], [0, 5, 3]];
    expect(area(floor)).toBeCloseTo(20, 6);
    const wallX = [[0, 0, 0], [0, 5, 0], [0, 5, 3], [0, 0, 3]];
    expect(area(wallX)).toBeCloseTo(15, 6);
    const wallY = [[0, 0, 0], [4, 0, 0], [4, 0, 3], [0, 0, 3]];
    expect(area(wallY)).toBeCloseTo(12, 6);
  });

  it('감김 방향이 뒤집혀도 같은 면적', () => {
    const L = [
      [0, 0, 0], [6, 0, 0], [6, 2, 0], [2, 2, 0], [2, 6, 0], [0, 6, 0],
    ];
    expect(area([...L].reverse())).toBeCloseTo(20, 6);
  });

  it('삼각형·퇴화 입력을 안전하게 다룬다', () => {
    expect(triangulatePolygon([[0, 0, 0], [1, 0, 0], [0, 1, 0]])).toEqual([0, 1, 2]);
    expect(triangulatePolygon([[0, 0, 0], [1, 0, 0]])).toEqual([]);
    expect(triangulatePolygon(null)).toEqual([]);
  });

  it('만들어진 삼각형이 원본 정점만 참조한다', () => {
    const L = [
      [0, 0, 0], [6, 0, 0], [6, 2, 0], [2, 2, 0], [2, 6, 0], [0, 6, 0],
    ];
    const tris = triangulatePolygon(L);
    expect(tris.length).toBe((L.length - 2) * 3);
    tris.forEach((i) => expect(i).toBeGreaterThanOrEqual(0));
    tris.forEach((i) => expect(i).toBeLessThan(L.length));
  });
});

describe('실제 파일에서 나온 형상', () => {
  // 용호동 파일 2.xml `su-b-204-204-i-f-105` 계열 — 부채꼴이 4.8배로 그리던 모양
  it('가늘고 긴 ㄷ자에서도 실제 면적과 일치한다', () => {
    const U = [
      [0, 0, 0], [12, 0, 0], [12, 1, 0], [1, 1, 0],
      [1, 8, 0], [12, 8, 0], [12, 9, 0], [0, 9, 0],
    ];
    // 12×9 에서 11×7 을 도려낸 ㄷ자 = 108 − 77 = 31
    expect(polygonArea3D(U)).toBeCloseTo(31, 6);
    expect(area(U)).toBeCloseTo(31, 6);
    expect(fanArea(U)).toBeGreaterThan(31 * 2);   // 예전 방식은 2배 넘게 칠했다
  });
});

// ── round-1 codex 검토 반영분 ────────────────────────────────────────────────

describe('buildSurfaceGeometry — 검증까지 한다', () => {
  it('성한 면은 ok, 삼각형을 돌려준다', () => {
    const sq = [[0, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]];
    const r = buildSurfaceGeometry(sq);
    expect(r.ok).toBe(true);
    expect(r.triangles.length).toBe(6);
    expect(r.drawnArea).toBeCloseTo(r.area, 6);
  });

  it('⚠️ 자기교차(8자) 면은 통과시키지 않는다', () => {
    // ⚠️ 예전 시험은 `if (!r.ok) expect(...)` 라 **ok 면 아무것도 검사하지 않고
    // 통과**했다(codex 지적). 무효한 시험이었다.
    const bowtie = [[0, 0, 0], [4, 4, 0], [4, 0, 0], [0, 4, 0]];
    const r = buildSurfaceGeometry(bowtie);
    expect(r.ok).toBe(false);
    expect(r.triangles).toEqual([]);
  });

  it('⚠️ 공선 3점을 "성한 면"으로 보고하지 않는다', () => {
    // 면적 0 이면 `|0 − 0| <= tol × 0` 이라 검증을 통과해 버렸다(codex 지적).
    const line = [[0, 0, 0], [4, 0, 0], [8, 0, 0]];
    const r = buildSurfaceGeometry(line);
    expect(r.ok).toBe(false);
    expect(r.triangles).toEqual([]);
    expect(triangulatePolygon(line)).toEqual([]);
  });

  it('정상 삼각형은 그대로 통과한다', () => {
    const tri = [[0, 0, 0], [4, 0, 0], [0, 3, 0]];
    const r = buildSurfaceGeometry(tri);
    expect(r.ok).toBe(true);
    expect(r.triangles).toEqual([0, 1, 2]);
    expect(r.area).toBeCloseTo(6, 9);
  });

  it('허용 오차를 넘기면 ok 가 false 다', () => {
    const sq = [[0, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]];
    expect(buildSurfaceGeometry(sq, -1).ok).toBe(false);
    expect(buildSurfaceGeometry(sq, -1).triangles).toEqual([]);
  });
});

describe('⚠️ 시작점·감김에 의존하지 않는다', () => {
  // 부채꼴은 "정점 0에서 전체가 보일 때"만 우연히 맞는다. 그런 우연이 시험을
  // 통과시키지 않도록 **모든 회전 × 양쪽 감김**을 돌린다.
  const shapes = {
    'ㄱ자': [[0, 0, 0], [6, 0, 0], [6, 2, 0], [2, 2, 0], [2, 6, 0], [0, 6, 0]],
    'ㄷ자': [[0, 0, 0], [12, 0, 0], [12, 1, 0], [1, 1, 0],
             [1, 8, 0], [12, 8, 0], [12, 9, 0], [0, 9, 0]],
    '수직벽': [[0, 0, 0], [0, 5, 0], [0, 5, 3], [0, 3, 3], [0, 3, 2], [0, 0, 2]],
  };
  Object.entries(shapes).forEach(([name, ring]) => {
    it(`${name} — 모든 시작점과 양쪽 감김에서 면적이 같다`, () => {
      const expected = polygonArea3D(ring);
      expect(expected).toBeGreaterThan(0);
      for (let r = 0; r < ring.length; r++) {
        const rot = [...ring.slice(r), ...ring.slice(0, r)];
        expect(area(rot)).toBeCloseTo(expected, 6);
        expect(area([...rot].reverse())).toBeCloseTo(expected, 6);
      }
    });
  });
});

describe('⚠️ 퇴화 입력', () => {
  it('연속 중복점이 있어도 면적이 유지된다', () => {
    const dup = [[0, 0, 0], [4, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]];
    expect(area(dup)).toBeCloseTo(20, 6);
  });

  it('한 변 위에 공선 정점이 늘어서도 면적이 유지된다', () => {
    // 용호동 `su-t-101-201-i-f-14` 가 이 모양이다 (한 직선 위 정점 4개)
    const collinear = [
      [-9.8, 0.75, 3.7], [-4.1, 0.75, 3.7], [-4.1, 2.85, 3.7], [-7.25, 2.85, 3.7],
      [-7.25, 3.55, 3.7], [-7.9, 3.55, 3.7], [-7.9, 2.85, 3.7], [-9.8, 2.85, 3.7],
    ];
    expect(area(collinear)).toBeCloseTo(polygonArea3D(collinear), 6);
    expect(polygonArea3D(collinear)).toBeGreaterThan(0);
  });

  it('면적 0 인 다각형은 삼각형을 만들지 않는다', () => {
    const line = [[0, 0, 0], [4, 0, 0], [8, 0, 0]];
    expect(triangulatePolygon(line)).toEqual([]);
    expect(triangulatedArea3D(line, triangulatePolygon(line))).toBeCloseTo(0, 9);
  });

  it('마지막 삼각형도 퇴화 검사를 거친다', () => {
    // 남은 3점이 한 직선 위가 되는 모양 — 면적 0 삼각형이 끼면 안 된다
    const spike = [[0, 0, 0], [4, 0, 0], [8, 0, 0], [8, 4, 0], [0, 4, 0]];
    const tris = triangulatePolygon(spike);
    for (let i = 0; i < tris.length; i += 3) {
      const a = spike[tris[i]], b = spike[tris[i + 1]], c = spike[tris[i + 2]];
      const u = [b[0] - a[0], b[1] - a[1], b[2] - a[2]];
      const w = [c[0] - a[0], c[1] - a[1], c[2] - a[2]];
      const ar = Math.hypot(
        u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2], u[0] * w[1] - u[1] * w[0]
      ) / 2;
      expect(ar).toBeGreaterThan(1e-9);
    }
    expect(triangulatedArea3D(spike, tris)).toBeCloseTo(32, 6);
  });
});

describe('newellNormal', () => {
  it('⚠️ 첫 세 점이 공선이어도 법선을 구한다 — 외적 방식은 여기서 영벡터가 된다', () => {
    const v = [[0, 0, 0], [2, 0, 0], [4, 0, 0], [4, 5, 0], [0, 5, 0]];
    const n = newellNormal(v);
    expect(Math.hypot(...n)).toBeCloseTo(1, 9);
    expect(Math.abs(n[2])).toBeCloseTo(1, 9);
    // 예전 방식(첫 세 점 외적)은 영벡터가 된다
    const cr = [
      (v[1][1] - v[0][1]) * (v[2][2] - v[0][2]) - (v[1][2] - v[0][2]) * (v[2][1] - v[0][1]),
      (v[1][2] - v[0][2]) * (v[2][0] - v[0][0]) - (v[1][0] - v[0][0]) * (v[2][2] - v[0][2]),
      (v[1][0] - v[0][0]) * (v[2][1] - v[0][1]) - (v[1][1] - v[0][1]) * (v[2][0] - v[0][0]),
    ];
    expect(Math.hypot(...cr)).toBeCloseTo(0, 12);
  });
});

describe('면적 산식은 하나뿐이다', () => {
  it('polygonArea3D 가 utils/geometry 의 정본과 동일 함수다', async () => {
    const { calculateSurfaceArea } = await import('../geometry.js');
    expect(polygonArea3D).toBe(calculateSurfaceArea);
  });
});
