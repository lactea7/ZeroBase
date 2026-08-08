// state/floorEditorModel.js — 평면도 편집기가 쓰는 파생값. **순수 함수다.**
//
// ⚠️ 여기에 JSX·스타일·이벤트 핸들러가 들어오면 안 된다. 입력에서 계산되는
// **데이터**만 낸다 — 그래야 화면 없이 시험할 수 있다.

import { calculateSurfaceArea } from '../utils/geometry';

//: 존 면적을 못 구했을 때의 최후 기본값(㎡).
export const FALLBACK_ZONE_AREA = 100.0;
//: 기하 합산 결과를 유효하다고 볼 최소 면적(㎡).
export const MIN_GEOMETRY_AREA = 1.0;
//: 층 정보가 전혀 없을 때 보여줄 층.
export const DEFAULT_FLOORS = [1, 2, 3];

/**
 * 존별 바닥면적 map.
 *
 * ⚠️ **백엔드와 같은 기준이어야 한다.** 백엔드는 gbXML 선언 면적(`declaredArea`)을
 * 우선하는데 여기서 기하 합산을 쓰면 화면과 시뮬레이션이 갈린다 — 층간 슬래브가
 * 아래층 존에 바닥·천장으로 이중 계산돼 104 존이 프런트 223.22㎡ /
 * 백엔드 107.22㎡ 로 **2배** 차이났다.
 * 유효성 기준(유한한 양수)도 백엔드 `gbxml_parser` 와 같게 둔다 — 임계값이
 * 어긋나면 그 사이 면적의 존에서 또 갈린다.
 *
 * ⚠️ 존 id 가 객체 키가 되므로 `Object.create(null)` 을 쓴다. 평범한 `{}` 는
 * `constructor` 같은 이름의 존에서 프로토타입 속성과 충돌한다.
 */
export function buildZoneFloorAreaById(zones, surfaces) {
  const byZone = Object.create(null);

  // ⚠️ 존마다 `surfaces.filter()` 를 돌면 존×면 이다. **한 번만 순회**한다.
  const geometrySum = Object.create(null);
  for (const surface of surfaces || []) {
    const type = (surface?.type || '').toLowerCase();
    if (!type.includes('floor') && !type.includes('slab')) continue;
    const zoneId = surface?.zone;
    if (zoneId == null) continue;
    geometrySum[zoneId] = (geometrySum[zoneId] || 0) + calculateSurfaceArea(surface.vertices);
  }

  for (const zone of zones || []) {
    const declared = Number(zone?.declaredArea ?? zone?.area ?? 0);
    if (Number.isFinite(declared) && declared > 0) {
      byZone[zone.id] = declared;
      continue;
    }
    const summed = geometrySum[zone.id] || 0;
    byZone[zone.id] = summed >= MIN_GEOMETRY_AREA ? summed : FALLBACK_ZONE_AREA;
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
