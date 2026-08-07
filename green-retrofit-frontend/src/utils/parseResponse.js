// utils/parseResponse.js — gbXML 파싱 응답 → 화면 상태.
//
// ⚠️ **백엔드가 채워 내려준 값을 프런트 기본값으로 덮으면 안 된다.** 백엔드는
// 용도별 아키타입으로 내부발열을 채운다(사무실 9/12, 화장실·계단 4/1). 여기서
// 덮으면 화장실·계단실에도 사무실 부하가 들어가 용도 구분이 통째로 무력화되고,
// 그건 **화면에 안 보이고 결과 숫자로만** 나타난다.

/**
 * 존 목록 정규화.
 *
 * ⚠️ `||` 가 아니라 `??` 다. `||` 는 사용자가 명시한 **0**(조명 없는 창고 등)까지
 * 덮어써서 아키타입 기본값으로 되돌린다.
 */
export function mapZones(zones) {
  return (zones || []).map((z) => ({
    ...z,
    peopleDensity: z.peopleDensity ?? null,
    lightingPower: z.lightingPower ?? null,
    equipmentPower: z.equipmentPower ?? null,
    outletCount: z.outletCount ?? 0,
    // ⚠️ 백엔드 `DEFAULT_OUTLET_LOAD_TYPE` 와 같아야 한다. 'sum' 이면 이중계산이다.
    outletLoadType: z.outletLoadType ?? 'max',
  }));
}
