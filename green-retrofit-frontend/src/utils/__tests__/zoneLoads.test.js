/**
 * utils/zoneLoads.js — **백엔드와의 산식 일치**.
 *
 * ⚠️ 콘센트 밀도와 합산 방식이 백엔드와 프런트에 **두 언어로 복제**돼 있다.
 *   · `ep_simulator.calc_outlet_power_density`
 *   · `domain/zone_loads.resolve`
 * 갈라지면 화면의 "시뮬레이션 반영 기기 부하"와 실제 계산이 달라진다.
 * 사용자는 화면 숫자를 믿고 판단하므로 조용히 어긋나면 안 된다.
 *
 * `backendOutletReference.json` 은 백엔드에서 생성한 값이다 — 손으로 고치지 말 것.
 */
import { describe, expect, it } from 'vitest';
import reference from './backendOutletReference.json';
import {
  DEFAULT_OUTLET_LOAD_TYPE,
  calcOutletPower,
  getActivityCategory,
  resolveEquipmentPower,
} from '../zoneLoads.js';

describe('백엔드 산식과 일치', () => {
  it.each(reference.cases)(
    '$label / 콘센트 $outletCount구 / $area㎡ → $outletWm2 W/㎡',
    ({ activityId, outletCount, area, outletWm2 }) => {
      expect(calcOutletPower({ activityId, outletCount }, area)).toBeCloseTo(outletWm2, 6);
    },
  );

  it.each(reference.cases)(
    '$label / $outletCount구 → max $max · sum $sum',
    ({ activityId, outletCount, area, max, sum }) => {
      const zone = { activityId, outletCount, equipmentPower: 12 };
      expect(resolveEquipmentPower({ ...zone, outletLoadType: 'max' }, area)).toBeCloseTo(max, 6);
      expect(resolveEquipmentPower({ ...zone, outletLoadType: 'sum' }, area)).toBeCloseTo(sum, 6);
    },
  );
});

describe('기본 동작', () => {
  it('⚠️ 기본은 큰 쪽만 — 더하면 같은 부하를 두 번 센다', () => {
    expect(DEFAULT_OUTLET_LOAD_TYPE).toBe('max');
    // 아키타입 12 + 콘센트 5.25 를 더하면 17.25 가 된다
    expect(resolveEquipmentPower(
      { activityId: 1105, outletCount: 10, equipmentPower: 12 }, 100)).toBe(12);
  });

  it.each([undefined, null, '', 'SUM', '알수없음'])(
    '알 수 없는 방식(%s)은 이중계산 쪽으로 떨어지지 않는다', (bad) => {
      expect(resolveEquipmentPower(
        { activityId: 1105, outletCount: 10, equipmentPower: 12, outletLoadType: bad },
        100)).toBe(12);
    });

  it('콘센트가 없으면 0', () => {
    expect(calcOutletPower({ activityId: 1105 }, 100)).toBe(0);
    expect(calcOutletPower({ activityId: 1105, outletCount: 0 }, 100)).toBe(0);
  });

  it('면적이 0 이어도 0 으로 나누지 않는다', () => {
    expect(Number.isFinite(calcOutletPower({ activityId: 1105, outletCount: 10 }, 0))).toBe(true);
  });

  it('상한 25 W/㎡ 를 넘지 않는다', () => {
    expect(calcOutletPower({ activityId: 1447, outletCount: 9999 }, 10)).toBe(25);
  });
});

describe('용도 분류', () => {
  it.each([[1105, 'office'], [1440, 'residential'], [1447, 'lab'],
           [1108, 'restaurant'], [9999, 'default'], [undefined, 'default']])(
    'activityId %s → %s', (id, expected) => {
      expect(getActivityCategory(id)).toBe(expected);
    });

  it('문자열 id 도 분류된다', () => {
    expect(getActivityCategory('1105')).toBe('office');
  });
});
