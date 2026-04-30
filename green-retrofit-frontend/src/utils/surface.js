// utils/surface.js - 표면/존/유리 관련 유틸리티 함수

export const getSurfaceGroupName = (type) => {
  const t = (type || '').toLowerCase();
  if (t.includes('exterior') || t === 'wall') return '외벽 (Exterior Wall)';
  if (t.includes('interiorwall') || t.includes('internalwall')) return '내벽 (Interior Wall)';
  if (t.includes('roof')) return '지붕 (Roof)';
  if (t.includes('floor') || t.includes('slab') || t.includes('ground') || t.includes('ceiling')) return '바닥 및 천장 (Floor & Ceiling)';
  if (t.includes('interior') || t.includes('internal')) return '내벽 (Interior Wall)'; // Fallback
  return `기타 (${type})`;
};

export const getZoneGroupName = (zone) => {
  return zone.isConditioned ? '공조 구역 (Conditioned)' : '비공조 구역 (Unconditioned)';
};

export const getPanesCategory = (name) => {
  if (!name) return 'Double';
  if (name.includes('Sgl')) return 'Single';
  if (name.includes('Trp')) return 'Triple';
  if (name.includes('Quadruple') || name.includes('Quad')) return 'Quadruple';
  return 'Double';
};

export const getCoatingType = (name) => {
  if (!name) return 'Clear/Tinted';
  if (name.includes('LoE')) return 'Low-E';
  if (name.includes('Elec')) return 'Smart';
  return 'Clear/Tinted';
};
