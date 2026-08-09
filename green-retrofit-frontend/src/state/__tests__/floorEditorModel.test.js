/**
 * state/floorEditorModel.js — 평면도 편집기 파생값.
 *
 * ⚠️ **존 면적은 백엔드와 같은 기준이어야 한다.** 백엔드는 gbXML 선언 면적을
 * 우선하는데 여기서 기하 합산을 쓰면 화면과 시뮬레이션이 갈린다 — 실제로 층간
 * 슬래브가 이중 계산돼 104 존이 프런트 223.22㎡ / 백엔드 107.22㎡ 로 **2배**
 * 차이났다. 유효성 임계값도 같아야 그 사이 면적의 존에서 또 갈리지 않는다.
 */
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_FLOORS, MIN_ZONE_AREA,
  buildDisplayFloors, buildZoneFloorAreaById, deriveFloorEditorModel,
  isVirtualFloor, selectSurface,
} from '../floorEditorModel.js';

/** 한 변 `n` 인 정사각형 바닥. */
const square = (n) => [[0, 0, 0], [n, 0, 0], [n, n, 0], [0, n, 0]];
const floorOf = (zone, verts) => ({ id: `F-${zone}`, zone, type: 'InteriorFloor', vertices: verts });

// ── 존 면적 ──────────────────────────────────────────────

describe('buildZoneFloorAreaById', () => {
  it('⚠️ 선언 면적을 기하 합산보다 우선한다', () => {
    // 백엔드가 그렇게 한다 — 안 맞추면 화면과 시뮬레이션이 갈린다
    const areas = buildZoneFloorAreaById(
      [{ id: 'Z1', declaredArea: 107.22 }], [floorOf('Z1', square(15))]);  // 기하=225
    expect(areas.Z1).toBe(107.22);
  });

  it('declaredArea 가 없으면 area 를 쓴다', () => {
    expect(buildZoneFloorAreaById([{ id: 'Z1', area: 80 }], []).Z1).toBe(80);
  });

  it.each([0, -5, NaN, null, undefined, '', 'abc'])(
    '⚠️ 유효하지 않은 선언 면적(%s)은 다음 후보로 넘어간다', (bad) => {
      // 유효성 기준은 백엔드(양수)와 같아야 한다
      const areas = buildZoneFloorAreaById(
        [{ id: 'Z1', declaredArea: bad }], [floorOf('Z1', square(10))]);
      expect(areas.Z1).toBe(100);
    });

  it('숫자 문자열도 면적으로 인정한다', () => {
    expect(buildZoneFloorAreaById([{ id: 'Z1', area: '75.5' }], []).Z1).toBe(75.5);
  });

  it('바닥·슬래브만 합산한다', () => {
    const areas = buildZoneFloorAreaById([{ id: 'Z1' }], [
      floorOf('Z1', square(10)),
      { id: 'W', zone: 'Z1', type: 'ExteriorWall', vertices: square(20) },
    ]);
    expect(areas.Z1).toBe(100);
  });

  it('같은 존의 여러 바닥을 합친다', () => {
    const areas = buildZoneFloorAreaById([{ id: 'Z1' }], [
      { ...floorOf('Z1', square(6)), id: 'F1' },
      { ...floorOf('Z1', square(8)), id: 'F2' },
    ]);
    expect(areas.Z1).toBe(36 + 64);
  });

  it.each([
    ['기하가 하한 미만', square(0.5)],   // 0.25㎡
    ['정점이 부족', [[0, 0, 0], [1, 0, 0]]],
    ['정점 없음', []],
  ])('⚠️ %s 이면 하한으로 (0 을 내면 나눗셈이 깨진다)', (_why, verts) => {
    expect(buildZoneFloorAreaById([{ id: 'Z1' }], [floorOf('Z1', verts)]).Z1)
      .toBe(MIN_ZONE_AREA);
  });

  it('하한 경계(1㎡)에서 기하를 인정한다', () => {
    expect(buildZoneFloorAreaById([{ id: 'Z1' }], [floorOf('Z1', square(1))]).Z1)
      .toBe(MIN_ZONE_AREA);
  });

  it('면이 없는 존은 하한을 받는다', () => {
    expect(buildZoneFloorAreaById([{ id: 'Z1' }], []).Z1).toBe(MIN_ZONE_AREA);
  });

  it('⚠️ 프로토타입 이름 존에서도 안전하다', () => {
    // 평범한 `{}` 였다면 `constructor` 가 함수를 돌려준다
    const areas = buildZoneFloorAreaById([{ id: 'constructor', area: 50 }], []);
    expect(areas.constructor).toBe(50);
    expect(areas.toString).toBeUndefined();
  });

  it('빈 입력에도 깨지지 않는다', () => {
    expect(buildZoneFloorAreaById(undefined, undefined)).toEqual({});
    expect(buildZoneFloorAreaById([], [])).toEqual({});
  });

  it('존에 안 붙은 면은 무시한다', () => {
    const areas = buildZoneFloorAreaById([{ id: 'Z1' }],
      [{ id: 'F', type: 'Floor', vertices: square(10) }]);   // zone 없음
    expect(areas.Z1).toBe(MIN_ZONE_AREA);
  });
});

// ── 층 목록 ──────────────────────────────────────────────

describe('buildDisplayFloors', () => {
  it('층이 없는 면은 1층으로 센다 (원래 동작)', () => {
    // ⚠️ 층 정보 없는 면을 버리면 그 면이 어느 화면에도 안 나온다
    expect(buildDisplayFloors([], [{ id: 'S', type: 'Floor' }])).toEqual([1]);
  });

  it('존과 면의 층을 합쳐 오름차순으로 낸다', () => {
    expect(buildDisplayFloors([{ floor: 3 }, { floor: 1 }], [{ floor: 2 }])).toEqual([1, 2, 3]);
  });

  it('중복을 없앤다', () => {
    expect(buildDisplayFloors([{ floor: 1 }, { floor: 1 }], [{ floor: 1 }])).toEqual([1]);
  });

  it('층이 없으면 1층으로 본다', () => {
    expect(buildDisplayFloors([{ id: 'Z' }], [])).toEqual([1]);
  });

  it.each(['2', 2.0])('숫자 문자열 층(%s)도 층으로 센다', (f) => {
    expect(buildDisplayFloors([{ floor: f }], [])).toEqual([2]);
  });

  it('⚠️ 층 정보가 아예 없으면 기본 층을 보인다 — 빈 화면을 내지 않는다', () => {
    expect(buildDisplayFloors([], [])).toEqual(DEFAULT_FLOORS);
  });

  it('기본 층 배열을 공유하지 않는다', () => {
    const a = buildDisplayFloors([], []);
    a.push(99);
    expect(buildDisplayFloors([], [])).toEqual(DEFAULT_FLOORS);
  });
});

// ── 가상 층 ──────────────────────────────────────────────

describe('isVirtualFloor', () => {
  it.each([[4, 3, true], [3, 3, false], [1, 3, false]])(
    '층 %s / 실제 %s → %s', (floor, real, expected) => {
      expect(isVirtualFloor(floor, real)).toBe(expected);
    });

  it('⚠️ 실제 층수를 모르면 가상으로 보지 않는다', () => {
    // 모른다고 전부 특수공간으로 표시하면 사용자가 실제 층을 못 찾는다
    expect(isVirtualFloor(9, 0)).toBe(false);
  });
});

// ── 선택된 면 ────────────────────────────────────────────

describe('selectSurface', () => {
  const S = [{ id: 'S1' }, { id: 'S2' }];

  it('면 모드에서 선택된 면을 찾는다', () => {
    expect(selectSurface(S, 'surface', 'S2')).toEqual({ id: 'S2' });
  });

  it('⚠️ 존 모드에서는 면을 돌려주지 않는다', () => {
    // 존을 편집하는데 면 패널이 열리면 안 된다
    expect(selectSurface(S, 'zone', 'S1')).toBeNull();
  });

  it.each([null, undefined, '없는면'])('선택이 %s 면 null', (id) => {
    expect(selectSurface(S, 'surface', id)).toBeNull();
  });
});

// ── 묶음 ─────────────────────────────────────────────────

describe('deriveFloorEditorModel', () => {
  it('필요한 값을 한 번에 낸다', () => {
    const m = deriveFloorEditorModel({
      surfaces: [{ ...floorOf('Z1', square(10)), floor: 2 }],
      zones: [{ id: 'Z1', floor: 2 }],
      realFloorCount: 1, edit: { editMode: 'surface', selectedId: 'F-Z1' },
    });
    expect(m.zoneFloorAreaById.Z1).toBe(100);
    expect(m.displayFloors).toEqual([2]);
    expect(m.selectedSurfaceData.id).toBe('F-Z1');
    expect(m.realFloorCount).toBe(1);
  });

  it('빈 상태에서도 깨지지 않는다', () => {
    const m = deriveFloorEditorModel({ surfaces: [], zones: [], edit: {} });
    expect(m.displayFloors).toEqual(DEFAULT_FLOORS);
    expect(m.selectedSurfaceData).toBeNull();
    expect(m.realFloorCount).toBe(0);
  });

  it('⚠️ 순수 데이터만 낸다 — JSX·핸들러가 섞이면 화면 없이 못 시험한다', () => {
    const m = deriveFloorEditorModel({ surfaces: [], zones: [], edit: {} });
    for (const v of Object.values(m)) {
      expect(typeof v).not.toBe('function');
    }
  });
});

// ── 백엔드 면적 계약과 일치 ──────────────────────────────
// ⚠️ 순서가 어긋나면 화면 면적과 시뮬레이션 면적이 갈린다.
//   declaredArea → geometricArea → area → 바닥/슬래브 → 천장/지붕 → 1㎡

import reference from '../../utils/__tests__/backendGeometryReference.json';

describe('백엔드 compute_zone_floor_areas 와 일치', () => {
  it.each(reference.zoneAreas)('$label', ({ zones, surfaces, expected }) => {
    expect(buildZoneFloorAreaById(zones, surfaces)).toEqual(expected);
  });
});

describe('백엔드가 고친 결함을 프런트도 따른다', () => {
  it('⚠️ 최후 하한이 1㎡ 다 (100㎡ 가 아니다)', () => {
    // 100㎡ 폴백은 실면적 ~5㎡ 샤프트에 100㎡ 분 내부발열을 주입해
    // **한겨울에도 냉방이 도는** 왜곡을 만들었다(백엔드가 이미 고친 결함).
    expect(buildZoneFloorAreaById([{ id: 'Z1' }], []).Z1).toBe(1.0);
  });

  it('⚠️ geometricArea 를 area 보다 우선한다', () => {
    // 파서가 층간면 귀속을 보정한 값이다. 빠뜨리면 101 화장실이
    // 12.42 vs 24.84 로 **2배** 갈린다.
    expect(buildZoneFloorAreaById([{ id: 'Z1', geometricArea: 12.42, area: 24.84 }], []).Z1)
      .toBe(12.42);
  });

  it('⚠️ 바닥이 없으면 천장/지붕으로 대체한다', () => {
    // 바닥면이 누락된 화장실·샤프트가 실제로 있다
    const areas = buildZoneFloorAreaById([{ id: 'Z1' }],
      [{ id: 'C', zone: 'Z1', type: 'Ceiling', vertices: square(7) }]);
    expect(areas.Z1).toBe(49);
  });

  it('선언 면적이 0 이면 area 로 넘어간다', () => {
    expect(buildZoneFloorAreaById([{ id: 'Z1', declaredArea: 0, area: 55.5 }], []).Z1)
      .toBe(55.5);
  });
});
