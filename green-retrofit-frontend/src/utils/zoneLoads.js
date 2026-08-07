// utils/zoneLoads.js — 존 기기부하(콘센트 포함) 산정.
//
// ⚠️ **백엔드와 같은 산식을 두 언어로 복제한 코드다.**
//   · 콘센트 밀도 → `ep_simulator.calc_outlet_power_density`
//   · 합산 방식   → `domain/zone_loads.resolve`
// 갈라지면 화면의 "시뮬레이션 반영 기기 부하"와 실제 계산이 달라진다. 사용자는
// 화면 숫자를 믿고 판단하므로 조용히 어긋나면 안 된다.
// `src/utils/__tests__/zoneLoads.test.js` 가 백엔드와 같은 값이 나오는지 고정한다.

import { OUTLET_W_PER_ACTIVITY } from '../data/constants';

const OFFICE = [1105, 1106, 1103, 1113, 1116, 1119, 1122];
const RESIDENTIAL = [1440, 1441, 1442, 1443, 1444, 1114, 1115, 1107, 1112, 1120, 1121, 1445];
const LAB = [1447, 1448, 1449, 1104, 1457, 1458, 1452];
const RESTAURANT = [1108, 1109, 1117, 1118];

export const DIVERSITY = 0.5;        // NREL/TP-7A40-54466 권장 동시사용률
export const UTILIZATION = 0.7;      // IEC 60364-8-1 ku 평균 이용률
export const MAX_OUTLET_W_M2 = 25;   // ASHRAE 90.1 상한

/** 기본 합산 방식. ⚠️ 백엔드 `DEFAULT_OUTLET_LOAD_TYPE` 와 같아야 한다. */
export const DEFAULT_OUTLET_LOAD_TYPE = 'max';

export function getActivityCategory(activityId) {
  const id = Number(activityId);
  if (OFFICE.includes(id)) return 'office';
  if (RESIDENTIAL.includes(id)) return 'residential';
  if (LAB.includes(id)) return 'lab';
  if (RESTAURANT.includes(id)) return 'restaurant';
  return 'default';
}

/** 콘센트 개수 → 면적당 부하밀도 (W/㎡). */
export function calcOutletPower(zone, floorArea) {
  const count = Number(zone?.outletCount || 0);
  if (count <= 0) return 0;
  const category = getActivityCategory(zone?.activityId);
  const wPerOutlet = OUTLET_W_PER_ACTIVITY[category] ?? OUTLET_W_PER_ACTIVITY.default;
  const area = floorArea > 0 ? floorArea : 1;
  const density = (count * wPerOutlet * DIVERSITY * UTILIZATION) / area;
  // ⚠️ **계산 단계에서 반올림하지 않는다.** 예전에는 `parseFloat(toFixed(2))` 로
  // 두 자리까지 잘라, 사무실 5구/20㎡ 에서 백엔드 13.125 vs 프런트 13.13 으로
  // 갈렸다. 화면에 보이는 값이 실제 계산과 다르면 사용자가 잘못 판단한다.
  // 반올림은 **표시할 때만** 한다.
  return Math.min(density, MAX_OUTLET_W_M2);
}

/**
 * 시뮬레이션에 실제로 반영되는 기기부하 (W/㎡).
 *
 * ⚠️ 기본은 **큰 쪽만**이다. `equipmentPower`(아키타입 기본값 포함)와 콘센트
 * 추정값은 **같은 물리량의 서로 다른 추정치**라 — ASHRAE/DOE 기기부하의 정의가
 * 곧 콘센트(plug) 부하다 — 더하면 이중계산이다.
 * `sum` 은 `equipmentPower` 가 콘센트를 **제외한** 공정·특수기기 부하임을
 * 사용자가 명시적으로 고른 경우에만 쓴다.
 */
export function resolveEquipmentPower(zone, floorArea) {
  const base = Number(zone?.equipmentPower || 0);
  const outlet = calcOutletPower(zone, floorArea);
  const loadType = zone?.outletLoadType === 'sum' ? 'sum' : DEFAULT_OUTLET_LOAD_TYPE;
  return loadType === 'sum' ? base + outlet : Math.max(base, outlet);
}
