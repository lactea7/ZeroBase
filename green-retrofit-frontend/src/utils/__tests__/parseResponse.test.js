/**
 * utils/parseResponse.js — 파싱 응답 매핑.
 *
 * ⚠️ 이 회귀는 **화면에 안 보이고 결과 숫자로만** 나타난다. 그래서 렌더 시험이
 * 아니라 값으로 고정한다. (예전 시험은 "사무실 문구가 없다" 정도만 봐서,
 * 값이 덮여도 통과했다 — codex 지적)
 */
import { describe, expect, it } from 'vitest';
import { mapZones } from '../parseResponse.js';

const OFFICE = { id: 'Z1', name: '사무실', lightingPower: 9, equipmentPower: 12,
                 peopleDensity: 0.06 };
const TOILET = { id: 'Z2', name: '화장실', lightingPower: 4, equipmentPower: 1,
                 peopleDensity: 0.02 };

describe('용도별 내부발열 보존', () => {
  it('⚠️ 백엔드가 준 값을 그대로 유지한다', () => {
    // 덮어쓰면 화장실·계단실에도 사무실 부하가 들어가 용도 구분이 무력화된다
    const [office, toilet] = mapZones([OFFICE, TOILET]);
    expect(office.lightingPower).toBe(9);
    expect(office.equipmentPower).toBe(12);
    expect(toilet.lightingPower).toBe(4);
    expect(toilet.equipmentPower).toBe(1);
    expect(toilet.peopleDensity).toBe(0.02);
  });

  it.each(['lightingPower', 'equipmentPower', 'peopleDensity'])(
    '⚠️ 명시된 0(%s)을 덮지 않는다', (key) => {
      // `||` 를 쓰면 "조명 없음(0)"이 아키타입 기본값으로 되돌아간다
      const [zone] = mapZones([{ ...OFFICE, [key]: 0 }]);
      expect(zone[key]).toBe(0);
    });

  it.each(['lightingPower', 'equipmentPower', 'peopleDensity'])(
    '값이 없으면(%s) null 로 둔다 — 백엔드가 채우게', (key) => {
      const { [key]: _drop, ...without } = OFFICE;
      expect(mapZones([without])[0][key]).toBeNull();
    });

  it('나머지 필드를 잃지 않는다', () => {
    const [zone] = mapZones([{ ...OFFICE, activityId: 1105, area: 100, floor: 2 }]);
    expect(zone).toMatchObject({ id: 'Z1', activityId: 1105, area: 100, floor: 2 });
  });
});

describe('콘센트 기본값', () => {
  it('⚠️ 기본 방식이 max 다 — sum 이면 이중계산이다', () => {
    expect(mapZones([OFFICE])[0].outletLoadType).toBe('max');
  });

  it('사용자가 고른 sum 은 유지한다', () => {
    expect(mapZones([{ ...OFFICE, outletLoadType: 'sum' }])[0].outletLoadType).toBe('sum');
  });

  it('콘센트 수가 없으면 0', () => {
    expect(mapZones([OFFICE])[0].outletCount).toBe(0);
  });

  it('명시된 콘센트 수를 유지한다', () => {
    expect(mapZones([{ ...OFFICE, outletCount: 40 }])[0].outletCount).toBe(40);
  });
});

describe('방어', () => {
  it.each([undefined, null, []])('존이 없어도(%s) 빈 배열', (input) => {
    expect(mapZones(input)).toEqual([]);
  });

  it('입력 배열을 변형하지 않는다', () => {
    const zones = [{ ...OFFICE }];
    mapZones(zones);
    expect(zones[0]).toEqual(OFFICE);
  });
});
