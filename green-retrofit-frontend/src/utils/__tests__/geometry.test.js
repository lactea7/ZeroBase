/**
 * utils/geometry.js — **백엔드와의 산식 일치**.
 *
 * ⚠️ 면 면적이 프런트·백엔드에 두 언어로 복제돼 있다. 갈라지면 화면에 보이는
 * 면적과 시뮬레이션이 쓰는 면적이 달라지고, 사용자는 화면 숫자를 믿고 판단한다.
 *
 * `backendGeometryReference.json` 은 백엔드에서 생성한 값이다 — 손으로 고치지 말 것.
 */
import { describe, expect, it } from 'vitest';
import reference from './backendGeometryReference.json';
import { calculateSurfaceArea } from '../geometry.js';

const CASES = {
  '정사각 10x10': [[0, 0, 0], [10, 0, 0], [10, 10, 0], [0, 10, 0]],
  '직사각 4x3': [[0, 0, 0], [4, 0, 0], [4, 3, 0], [0, 3, 0]],
  'L자(오목)': [[0, 0, 0], [4, 0, 0], [4, 2, 0], [2, 2, 0], [2, 4, 0], [0, 4, 0]],
  '기울어진 3D': [[0, 0, 0], [4, 0, 3], [4, 3, 3], [0, 3, 0]],
  '수직벽': [[0, 0, 0], [0, 0, 3], [5, 0, 3], [5, 0, 0]],
  '정점2개': [[0, 0, 0], [1, 0, 0]],
  '빈 배열': [],
  '퇴화(동일점)': [[0, 0, 0], [0, 0, 0], [0, 0, 0]],
  '삼각형': [[0, 0, 0], [6, 0, 0], [0, 4, 0]],
};

describe('백엔드 산식과 일치', () => {
  it.each(Object.entries(reference.surfaceArea))(
    '%s → %s ㎡', (label, expected) => {
      expect(calculateSurfaceArea(CASES[label])).toBeCloseTo(expected, 9);
    });
});

describe('오목 다각형', () => {
  it('⚠️ 삼각형 fan 절댓값 합보다 작다 — 되접힌 삼각형이 더해지면 안 된다', () => {
    // 예전 프런트 산식은 오목 폴리곤에서 과대했다. gbXML 은 L 자 평면을 흔히 낸다.
    const L = CASES['L자(오목)'];
    // 4×4 정사각(16)에서 2×2 를 뺀 12 가 정답이다
    expect(calculateSurfaceArea(L)).toBeCloseTo(12, 9);
  });
});

describe('방어', () => {
  it.each([null, undefined, [], [[0, 0, 0]], [[0, 0, 0], [1, 0, 0]]])(
    '정점이 부족하면(%s) 0', (verts) => {
      expect(calculateSurfaceArea(verts)).toBe(0);
    });

  it('정점 순서를 뒤집어도 면적은 같다', () => {
    const sq = CASES['정사각 10x10'];
    expect(calculateSurfaceArea([...sq].reverse())).toBeCloseTo(100, 9);
  });
});
