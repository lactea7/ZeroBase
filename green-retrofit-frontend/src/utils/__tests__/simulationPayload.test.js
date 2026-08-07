/**
 * utils/simulationPayload.js — 백엔드와의 요청 계약.
 *
 * ⚠️ 키 하나가 빠지거나 위치가 틀리면 백엔드가 **조용히 기본값으로** 돌아가고,
 * 화면엔 정상처럼 보이는 결과가 나온다. 그래서 값으로 고정한다.
 */
import { describe, expect, it } from 'vitest';
import { buildSimulationPayload, pickBaselineActual } from '../simulationPayload.js';

const BASE = {
  projectData: { name: '테스트', location: 'KOR_SO_Seoul', heatSource: 11 },
  zones: [{ id: 'Z1' }],
  surfaces: [{ id: 'S1' }],
  materials: { constructions: [] },
  constructionOverrides: { S1: { tier: 'high' } },
  originalModel: { zones: [{ id: 'Z1' }], surfaces: [{ id: 'S1' }] },
};

describe('buildSimulationPayload', () => {
  it('백엔드가 읽는 최상위 키를 전부 담는다', () => {
    expect(Object.keys(buildSimulationPayload(BASE)).sort()).toEqual([
      'baselineModel', 'constructionOverrides', 'materials',
      'projectData', 'surfaces', 'zones',
    ]);
  });

  it('⚠️ lccParameters 는 projectData 안에 있어야 한다', () => {
    // 최상위로 올리면 백엔드 SimulationPayload 가 그 키를 모르고 통째로 버린다 —
    // 할인율·분석기간이 조용히 기본값으로 돌아간다.
    const p = buildSimulationPayload({
      ...BASE,
      projectData: { ...BASE.projectData, lccParameters: { discountRate: 3.0 } },
    });
    expect(p.projectData.lccParameters).toEqual({ discountRate: 3.0 });
    expect(p.lccParameters).toBeUndefined();
  });

  it('⚠️ hvacUpgradeActive 도 projectData 안이다', () => {
    const p = buildSimulationPayload({
      ...BASE, projectData: { ...BASE.projectData, hvacUpgradeActive: true },
    });
    expect(p.projectData.hvacUpgradeActive).toBe(true);
  });

  it('업로드 원본을 전/후 비교용으로 함께 보낸다', () => {
    // ⚠️ 안 보내면 백엔드가 기준선을 못 만들어 절감액이 추정으로 대체된다
    expect(buildSimulationPayload(BASE).baselineModel).toEqual(BASE.originalModel);
  });

  it('원본이 없으면 빈 객체를 보낸다 (undefined 가 아니라)', () => {
    const p = buildSimulationPayload({ ...BASE, originalModel: null });
    expect(p.baselineModel).toEqual({});
  });

  it('입력 객체를 변형하지 않는다', () => {
    const projectData = { ...BASE.projectData, baselineActual: { mode: 'bill', elecBill: 1 } };
    buildSimulationPayload({ ...BASE, projectData });
    expect(projectData.baselineActual).toEqual({ mode: 'bill', elecBill: 1 });
  });
});

// ── 실측 기준선 ──────────────────────────────────────────
// ⚠️ 두 모드의 값을 다 보내면 백엔드의 우선순위 판단이 뒤집힌다. 사용자가 모드를
// 바꿔도 예전 입력이 남아 그쪽이 기준선이 된다 — 절감액이 통째로 달라진다.

describe('pickBaselineActual', () => {
  it('사용량 모드에서는 요금 잔여값을 보내지 않는다', () => {
    const out = pickBaselineActual({
      mode: 'usage', elecKwh: 1000, heatKwh: 500,
      elecBill: 9999999, heatBill: 8888888,   // 예전에 입력해 둔 값
    });
    expect(out).toEqual({ mode: 'usage', elecKwh: 1000, heatKwh: 500 });
    expect(out.elecBill).toBeUndefined();
  });

  it('요금 모드에서는 사용량 잔여값을 보내지 않는다', () => {
    const out = pickBaselineActual({
      mode: 'bill', elecBill: 1000000, heatBill: 500000,
      elecKwh: 77777, heatKwh: 66666,
    });
    expect(out).toEqual({ mode: 'bill', elecBill: 1000000, heatBill: 500000 });
    expect(out.elecKwh).toBeUndefined();
  });

  it('모드가 없으면 요금 모드로 본다', () => {
    expect(pickBaselineActual({ elecBill: 100 }).mode).toBe('bill');
  });

  it('입력이 아예 없어도 깨지지 않는다', () => {
    expect(pickBaselineActual(undefined).mode).toBe('bill');
    expect(pickBaselineActual(null).mode).toBe('bill');
  });
});
