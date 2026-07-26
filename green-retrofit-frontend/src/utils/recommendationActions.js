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
    const hasGlass = (s) =>
      s.type === 'Window' || s.type === 'Skylight' ||
      s.glazingId != null ||
      ((s.wwr && s.wwr > 0) && /wall/i.test(s.type || ''));
    // 상향(window_upgrade)과 같은 이유로 개수는 업데이터 '밖'에서 미리 센다.
    const targets = surfaces.filter((s) => hasGlass(s) && s.glazingId !== 42);
    if (targets.length === 0) return null;
    const targetIds = new Set(targets.map((s) => s.id));
    setSurfaces((prev) =>
      prev.map((s) => (targetIds.has(s.id) ? { ...s, glazingId: 42 } : s)) // 일반 복층 유리(ID 42)로 하향
    );
    return `창호 ${targets.length}개 면을 일반 복층유리로 하향`;
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
  } else if (type === 'hvac_upgrade') {
    // 노후 냉난방 설비 → 1등급 신형 (설비 교체 토글 활성화 → 시뮬 COP 신형 적용)
    if (projectData.hvacUpgradeActive) return null;
    setProjectData((prev) => ({ ...prev, hvacUpgradeActive: true }));
    return '노후 냉난방 설비를 1등급 신형으로 교체';
  } else if (type === 'window_upgrade') {
    // 창 가진 면 전체를 고성능 Low-E+Ar 복층(ID 154, U 1.32)으로 상향 — 백엔드 변형과 동일
    const hasGlass = (s) =>
      s.type === 'Window' || s.type === 'Skylight' ||
      s.glazingId != null ||
      ((s.wwr && s.wwr > 0) && /wall/i.test(s.type || ''));
    // 개수는 setSurfaces 업데이터 '밖'에서 미리 센다. 업데이터는 나중에 실행되므로
    // 그 안에서 증가시킨 값은 여기서 읽을 수 없고(항상 0), StrictMode에선 두 번 돈다.
    const targets = surfaces.filter((s) => hasGlass(s) && s.glazingId !== 154);
    if (targets.length === 0) return null;
    const targetIds = new Set(targets.map((s) => s.id));
    setSurfaces((prev) =>
      prev.map((s) => (targetIds.has(s.id) ? { ...s, glazingId: 154 } : s))
    );
    return `창호 ${targets.length}개 면을 고성능 Low-E 복층으로 상향`;
  } else if (type === 'insulation_upgrade') {
    // 일반/저성능 단열(λ>0.045) → 중성능(high) 제품(비드법 1종 2호, ID 2)으로 상향
    const hiProduct = INSULATION_TYPES.find(p => p.tier === 'high') || INSULATION_TYPES[1];
    const newOverrides = { ...constructionOverrides };
    const updatedUValues = {};
    let changedCount = 0;

    Object.keys(newOverrides).forEach((id) => {
      if (newOverrides[id].tier === 'standard' || newOverrides[id].tier === 'basic') {
        changedCount++;
        const newOverride = { insulationId: hiProduct.id, tier: 'high', thickness: newOverrides[id].thickness || 100 };
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

    if (materials?.constructions) {
      surfaces.forEach((s) => {
        if (!newOverrides[s.id]) {
          const c_ref = s.constructionRef || s.constructionId;
          const c = materials.constructions.find(con => con.id === c_ref);
          if (c) {
            const insul = c.layers?.find(l => l.isInsulation);
            if (insul && insul.conductivity > 0.045) {
              changedCount++;
              const newOverride = { insulationId: hiProduct.id, tier: 'high', thickness: insul.thickness || 100 };
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
    return changedCount > 0 ? `단열재 ${changedCount}개 부위를 중성능 등급으로 상향` : null;
  }
  return null;
};
