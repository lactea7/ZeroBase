import { describe, it, expect } from 'vitest';

// ⚠️ 뷰어가 "시뮬레이션에 들어가는 면"을 가리는 기준은 **백엔드와 같아야 한다.**
// 백엔드(`simulation/geometry.emit_surfaces`):
//   z_id = s['zone'].replace(" ", "_")
//   if z_id == "Unknown" or z_id not in valid_zone_ids: skipped
// 이 시험은 그 계약을 문서화한다. 뷰어 내부 구현과 같은 식을 쓴다.
const normZone = (v) => (v || '').replaceAll(' ', '_');
const makeInSimulation = (zones) => {
  const ids = new Set((zones || []).map((z) => normZone(z.id)));
  return (s) => {
    const z = normZone(s.zone);
    return z !== '' && z !== 'Unknown' && ids.has(z);
  };
};

describe('시뮬레이션 포함 판정', () => {
  const zones = [{ id: '501 계단실' }, { id: '204 사무 공간' }];
  const inSim = makeInSimulation(zones);

  it('유효 존에 붙은 면은 포함', () => {
    expect(inSim({ zone: '501 계단실' })).toBe(true);
  });

  it('⚠️ 공백이 둘 이상인 존 이름 — JS `replace` 는 첫 하나만 바꾼다', () => {
    // 파이썬 `str.replace` 는 전부 바꾸므로 백엔드는 이 존을 포함한다.
    // `replaceAll` 이 아니면 여기서 프런트만 제외해 화면과 계산이 갈린다.
    expect(inSim({ zone: '204 사무 공간' })).toBe(true);
    expect('204 사무 공간'.replace(' ', '_')).not.toBe(normZone('204 사무 공간'));
  });

  it('존이 없거나 Unknown 이면 제외 — 타입은 보지 않는다', () => {
    expect(inSim({ zone: 'Unknown', type: 'Shade' })).toBe(false);
    expect(inSim({ zone: '', type: 'ExteriorWall' })).toBe(false);
    expect(inSim({ zone: undefined })).toBe(false);
  });

  it('⚠️ 타입이 Shade 라도 유효 존에 붙으면 **포함**한다', () => {
    // 타입으로 거르면 이 면이 화면에서만 사라진다 — 백엔드는 계산에 넣는다.
    expect(inSim({ zone: '501 계단실', type: 'Shade' })).toBe(true);
  });

  it('⚠️ 타입이 Shade 가 아니어도 존이 없으면 **제외**한다', () => {
    // 고아 surface. 타입 기준 필터는 이걸 화면에 남겨 계산 대상처럼 보이게 한다.
    expect(inSim({ zone: 'Unknown', type: 'Roof' })).toBe(false);
  });
});
