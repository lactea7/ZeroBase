// state/floorEditorModel.js — 평면도 편집기가 쓰는 파생값. **순수 함수다.**
//
// ⚠️ 여기에 JSX·스타일·이벤트 핸들러가 들어오면 안 된다. 입력에서 계산되는
// **데이터**만 낸다 — 그래야 화면 없이 시험할 수 있다.

import { calculateSurfaceArea } from '../utils/geometry';

//: 존 면적의 **최후 하한**(㎡).
//
// ⚠️ 예전 프런트는 100㎡ 였다. 백엔드는 그 값이 **한겨울에 냉방이 도는 왜곡**을
// 만들어 1㎡ 로 바꿨다 — 실면적 ~5㎡ 샤프트·설비존에 100㎡ 분 내부발열을 주입했기
// 때문이다. 프런트가 100 을 쓰면 화면 면적과 시뮬레이션 면적이 20배 갈린다.
export const MIN_ZONE_AREA = 1.0;

//: 층 정보가 전혀 없을 때 보여줄 층.
export const DEFAULT_FLOORS = [1, 2, 3];

/**
 * 존별 바닥면적 map.
 *
 * ⚠️ **백엔드 `ep_simulator.compute_zone_floor_areas` 와 같은 순서여야 한다.**
 * 갈라지면 화면 면적과 시뮬레이션 면적이 달라진다.
 *
 *   declaredArea → geometricArea → area → 바닥/슬래브 합 → 천장/지붕 합 → 1㎡
 *
 * ⚠️ `geometricArea` 를 빠뜨리면 안 된다. 파서가 층간면 귀속을 보정한 값인데,
 * 단순 합산으로 대체하면 101 화장실이 12.42 vs 24.84 로 **2배** 갈린다.
 *
 * ⚠️ 존 id 가 객체 키가 되므로 `Object.create(null)` 을 쓴다. 평범한 `{}` 는
 * `constructor` 같은 이름의 존에서 프로토타입 속성과 충돌한다.
 */
export function buildZoneFloorAreaById(zones, surfaces) {
  const byZone = Object.create(null);

  // ⚠️ 존마다 `surfaces.filter()` 를 돌면 존×면 이다. **한 번만 순회**한다.
  const floorSum = Object.create(null);
  const ceilingSum = Object.create(null);
  for (const surface of surfaces || []) {
    const zoneId = surface?.zone;
    if (zoneId == null) continue;
    const type = (surface?.type || '').toLowerCase();
    const bucket = (type.includes('floor') || type.includes('slab')) ? floorSum
      : (type.includes('ceiling') || type.includes('roof')) ? ceilingSum : null;
    if (!bucket) continue;
    bucket[zoneId] = (bucket[zoneId] || 0) + calculateSurfaceArea(surface.vertices);
  }

  for (const zone of zones || []) {
    const declared = Number(zone?.declaredArea) || 0;
    if (declared > 0) {
      byZone[zone.id] = declared;
      continue;
    }
    // 파서가 계산한 값을 그다음으로 쓴다 — 여기서 다시 합산하면 층간면 귀속
    // 보정이 사라진다.
    const parsed = (Number(zone?.geometricArea) || 0) || (Number(zone?.area) || 0);
    if (parsed > 0) {
      byZone[zone.id] = parsed;
      continue;
    }
    const floors = floorSum[zone.id] || 0;
    // 바닥 폴리곤이 없거나 퇴화된 존(샤프트·설비존, 바닥면 누락 화장실)은
    // 천장/지붕으로 대체하고, 그래도 없으면 하한만 적용한다.
    byZone[zone.id] = floors >= MIN_ZONE_AREA
      ? floors
      : Math.max(floors, ceilingSum[zone.id] || 0, MIN_ZONE_AREA);
  }
  return byZone;
}

/** 화면에 보일 층 목록. 층 정보가 없으면 기본 3개 층을 보인다. */
export function buildDisplayFloors(zones, surfaces) {
  const floors = new Set();
  for (const s of surfaces || []) floors.add(Number(s?.floor) || 1);
  for (const z of zones || []) floors.add(Number(z?.floor) || 1);
  const sorted = [...floors].filter(Number.isFinite).sort((a, b) => a - b);
  return sorted.length > 0 ? sorted : [...DEFAULT_FLOORS];
}

/**
 * 가상 층(창고·샤프트 등 특수 공간)인가.
 *
 * ⚠️ 함수로 남긴다 — 층 번호 하나로 즉시 판정되는 값이라 map 을 만들 이유가 없다.
 */
export function isVirtualFloor(floor, realFloorCount) {
  return realFloorCount > 0 && floor > realFloorCount;
}

/** 편집 중인 면. 존 모드에서는 없다. */
export function selectSurface(surfaces, editMode, selectedId) {
  if (editMode !== 'surface' || selectedId == null) return null;
  return (surfaces || []).find((s) => s.id === selectedId) || null;
}

/**
 * 평면도 편집기 파생값 묶음.
 *
 * ⚠️ `useMemo` 는 여기가 아니라 **호출부**에서 건다(codex 조언) — 입력 참조를
 * 전부 dependency 에 넣어야 하는데, 그건 호출부만 안다.
 */
export function deriveFloorEditorModel({ surfaces, zones, realFloorCount, edit }) {
  const { editMode, selectedId } = edit || {};
  return {
    zoneFloorAreaById: buildZoneFloorAreaById(zones, surfaces),
    displayFloors: buildDisplayFloors(zones, surfaces),
    selectedSurfaceData: selectSurface(surfaces, editMode, selectedId),
    realFloorCount: realFloorCount || 0,
  };
}
