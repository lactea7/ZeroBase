// utils/recommendationActions.js - 비용 절감 제안(백엔드 recommendations)의 프론트 적용 로직
// 제안 1건의 상태 변경만 수행하고, 무엇을 바꿨는지 요약 문자열을 반환한다(변경 없으면 null).
// alert/화면이동은 호출하는 쪽(App)에서 일괄 처리 → 여러 제안을 한 번에 적용 가능.
import { INSULATION_TYPES } from '../data/insulation';

export const applyRecommendation = (type, ctx) => {
  const {
    surfaces, zones, projectData, constructionOverrides, materials,
    setSurfaces, setZones, setProjectData, setConstructionOverrides,
    calculateUpdatedUValue,
  } = ctx;

  if (type === 'window') {
    // gbXML 모델은 별도 Window 면이 없고 벽면의 WWR/glazingId로 창을 표현한다.
    // 따라서 Window/Skylight 면뿐 아니라 '창을 가진 면'(glazingId 지정 or wwr>0)도 하향해야
    // 백엔드 창호비가 실제로 줄어든다. (기존엔 type 체크만 해 gbXML에서 무반응이었음)
    let changed = 0;
    setSurfaces((prev) =>
      prev.map((s) => {
        const hasGlass =
          s.type === 'Window' || s.type === 'Skylight' ||
          s.glazingId != null ||
          ((s.wwr && s.wwr > 0) && /wall/i.test(s.type || ''));
        if (hasGlass && s.glazingId !== 42) {
          changed++;
          return { ...s, glazingId: 42 }; // 일반 복층 유리(ID 42)로 하향
        }
        return s;
      })
    );
    return changed > 0 ? `창호 ${changed}개 면을 일반 복층유리로 하향` : null;
  } else if (type === 'insulation') {
    // 모든 구조체의 단열재를 일반 등급 제품(비드법 1종 1호, ID 1)으로 일괄 교체
    const stdProduct = INSULATION_TYPES.find(p => p.tier === 'standard') || INSULATION_TYPES[0];

    const newOverrides = { ...constructionOverrides };
    const updatedUValues = {};

    let changedCount = 0;

    // 1. 기존 오버라이드 중 고성능 다운그레이드
    Object.keys(newOverrides).forEach((id) => {
      if (newOverrides[id].tier === 'premium' || newOverrides[id].tier === 'high') {
        changedCount++;
        const newOverride = { insulationId: stdProduct.id, tier: 'standard', thickness: newOverrides[id].thickness || 100 };

        const s = surfaces.find(surf => surf.id === id);
        if (s && materials?.constructions) {
          const c_ref = s.constructionRef || s.constructionId;
          const c = materials.constructions.find(con => con.id === c_ref);
          if (c) {
            const newU = calculateUpdatedUValue(c, newOverride);
            newOverride.uValue = newU;
            updatedUValues[id] = newU;
          }
        }
        newOverrides[id] = newOverride;
      }
    });

    // 2. 오버라이드가 없는 원본 고성능 벽체 추가
    if (materials?.constructions) {
      surfaces.forEach((s) => {
        if (!newOverrides[s.id]) {
          const c_ref = s.constructionRef || s.constructionId;
          const c = materials.constructions.find(con => con.id === c_ref);
          if (c) {
            const insul = c.layers?.find(l => l.isInsulation);
            if (insul && insul.conductivity <= 0.045) {
              changedCount++;
              const newOverride = { insulationId: stdProduct.id, tier: 'standard', thickness: insul.thickness || 100 };
              const newU = calculateUpdatedUValue(c, newOverride);
              newOverride.uValue = newU;
              updatedUValues[s.id] = newU;
              newOverrides[s.id] = newOverride;
            }
          }
        }
      });
    }

    setConstructionOverrides(newOverrides);
    if (Object.keys(updatedUValues).length > 0) {
      setSurfaces(prevSurfaces => prevSurfaces.map(s =>
        updatedUValues[s.id] !== undefined ? { ...s, uValue: updatedUValues[s.id] } : s
      ));
    }

    return changedCount > 0 ? `단열재 ${changedCount}개 외벽을 일반 등급(EPS/미네랄울)으로 하향` : null;
  } else if (type === 'hvac') {
    // 지열이면 지열 해제, 아니면 고효율 설비를 표준 개별 냉난방기(Generic, id 5)로 하향
    if (projectData.geothermalApplied) {
      setProjectData((prev) => ({ ...prev, geothermalApplied: false }));
      return '지열(Geothermal) 시스템 도입 취소';
    }
    const targets = zones.filter((z) => z.isConditioned !== false && z.hvacSystemId !== 5);
    if (targets.length === 0) return null;
    setZones((prev) =>
      prev.map((z) =>
        z.isConditioned !== false && z.hvacSystemId !== 5 ? { ...z, hvacSystemId: 5 } : z
      )
    );
    return `냉난방 설비 ${targets.length}개 존을 표준 설비로 변경`;
  } else if (type === 'hvac_scope') {
    // 비거주 구역(계단실·창고·기계실 등)을 설비 설치 범위에서 제외
    if (projectData.hvacExcludeNonHabitable) return null;
    setProjectData((prev) => ({ ...prev, hvacExcludeNonHabitable: true }));
    return '비거주 구역(계단실·창고 등) 냉난방 설비 제외';
  } else if (type === 'led') {
    const manualZones = zones.filter((z) => z.ledFixtureCount > 0);
    if (manualZones.length > 0) {
      const reducedCount = manualZones.reduce(
        (acc, z) => acc + (z.ledFixtureCount - Math.floor(z.ledFixtureCount * 0.5)),
        0
      );
      setZones((prev) =>
        prev.map((z) =>
          z.ledFixtureCount > 0 ? { ...z, ledFixtureCount: Math.floor(z.ledFixtureCount * 0.5) } : z
        )
      );
      return `LED 교체 수량 ${reducedCount}개 축소`;
    }
    if (projectData.ledReductionActive) return null; // 이미 적용됨 → 변경 없음
    setProjectData((prev) => ({ ...prev, ledReductionActive: true }));
    return '비필수 구역 LED 교체 제외';
  }
  return null;
};
