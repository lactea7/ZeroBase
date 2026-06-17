// data/insulation.js - 한국 에너지절약설계기준 기반 단열재 제품 데이터베이스

/**
 * 단열재 제품 목록
 * - conductivity: 열전도율 λ (W/m·K) — 값이 낮을수록 고성능
 * - density: 밀도 (kg/m³)
 * - category: 제품 카테고리 코드
 * - tier: cost_analyzer.py의 INSULATION_TIERS와 매칭되는 성능 등급
 * - defaultThickness: 일반적으로 많이 사용하는 두께 (mm)
 */
export const INSULATION_TYPES = [
  // ── 비드법 보온판 (EPS) ──
  { id: 1,  name: '비드법 1종 1호',      conductivity: 0.036, density: 30,  category: 'EPS', tier: 'standard', defaultThickness: 100 },
  { id: 2,  name: '비드법 1종 2호',      conductivity: 0.031, density: 25,  category: 'EPS', tier: 'high',     defaultThickness: 100 },
  { id: 3,  name: '비드법 2종 1호',      conductivity: 0.034, density: 25,  category: 'EPS', tier: 'standard', defaultThickness: 100 },
  { id: 4,  name: '비드법 2종 2호',      conductivity: 0.029, density: 20,  category: 'EPS', tier: 'high',     defaultThickness: 100 },

  // ── 압출법 보온판 (XPS) ──
  { id: 5,  name: 'XPS 1종',            conductivity: 0.028, density: 35,  category: 'XPS', tier: 'high',     defaultThickness: 50  },
  { id: 6,  name: 'XPS 2종',            conductivity: 0.026, density: 30,  category: 'XPS', tier: 'premium',  defaultThickness: 50  },
  { id: 7,  name: 'XPS 3종',            conductivity: 0.024, density: 28,  category: 'XPS', tier: 'premium',  defaultThickness: 50  },

  // ── 경질 우레탄폼 (PUR/PIR) ──
  { id: 8,  name: 'PUR 1종 1호',        conductivity: 0.024, density: 35,  category: 'PUR', tier: 'premium',  defaultThickness: 80  },
  { id: 9,  name: 'PUR 1종 2호',        conductivity: 0.020, density: 40,  category: 'PUR', tier: 'premium',  defaultThickness: 80  },
  { id: 10, name: 'PIR 보온판',          conductivity: 0.022, density: 32,  category: 'PUR', tier: 'premium',  defaultThickness: 80  },

  // ── 글라스울 (Glass Wool) ──
  { id: 11, name: '글라스울 24K',        conductivity: 0.038, density: 24,  category: 'GW',  tier: 'standard', defaultThickness: 100 },
  { id: 12, name: '글라스울 32K',        conductivity: 0.035, density: 32,  category: 'GW',  tier: 'high',     defaultThickness: 100 },
  { id: 13, name: '글라스울 48K',        conductivity: 0.032, density: 48,  category: 'GW',  tier: 'high',     defaultThickness: 100 },

  // ── 미네랄울 / 암면 (Mineral Wool) ──
  { id: 14, name: '미네랄울 1호',        conductivity: 0.040, density: 40,  category: 'MW',  tier: 'standard', defaultThickness: 100 },
  { id: 15, name: '미네랄울 2호',        conductivity: 0.035, density: 60,  category: 'MW',  tier: 'high',     defaultThickness: 100 },
  { id: 16, name: '미네랄울 3호',        conductivity: 0.030, density: 80,  category: 'MW',  tier: 'high',     defaultThickness: 100 },

  // ── 페놀폼 (Phenol Foam) ──
  { id: 17, name: '페놀폼 1종 1호',     conductivity: 0.021, density: 30,  category: 'PF',  tier: 'premium',  defaultThickness: 60  },
  { id: 18, name: '페놀폼 1종 2호',     conductivity: 0.019, density: 35,  category: 'PF',  tier: 'premium',  defaultThickness: 60  },

  // ── 셀룰로오스 ──
  { id: 19, name: '셀룰로오스 단열재',   conductivity: 0.042, density: 55,  category: 'CLU', tier: 'standard', defaultThickness: 150 },

  // ── 펄라이트 ──
  { id: 20, name: '펄라이트 보온판',     conductivity: 0.050, density: 150, category: 'PLT', tier: 'basic',    defaultThickness: 100 },

  // ── 진공단열재 (VIP) ──
  { id: 21, name: '진공단열재 (VIP)',    conductivity: 0.005, density: 180, category: 'VIP', tier: 'premium',  defaultThickness: 25  },
];

/**
 * 단열재 카테고리 이름 매핑
 */
export const INSULATION_CATEGORIES = {
  EPS: '비드법 보온판 (EPS)',
  XPS: '압출법 보온판 (XPS)',
  PUR: '경질 우레탄 (PUR/PIR)',
  GW:  '글라스울 (Glass Wool)',
  MW:  '미네랄울 (Mineral Wool)',
  PF:  '페놀폼 (Phenol Foam)',
  CLU: '셀룰로오스',
  PLT: '펄라이트',
  VIP: '진공단열재 (VIP)',
};

/**
 * 카테고리별 대표 색상 (시각화에 사용)
 */
export const INSULATION_COLORS = {
  EPS: { bg: '#fbbf24', border: '#f59e0b', text: '#92400e' },  // amber
  XPS: { bg: '#60a5fa', border: '#3b82f6', text: '#1e3a5f' },  // blue
  PUR: { bg: '#f472b6', border: '#ec4899', text: '#831843' },  // pink
  GW:  { bg: '#a78bfa', border: '#8b5cf6', text: '#4c1d95' },  // violet
  MW:  { bg: '#fb923c', border: '#f97316', text: '#7c2d12' },  // orange
  PF:  { bg: '#34d399', border: '#10b981', text: '#064e3b' },  // emerald
  CLU: { bg: '#86efac', border: '#22c55e', text: '#14532d' },  // green
  PLT: { bg: '#d4d4d8', border: '#a1a1aa', text: '#3f3f46' },  // zinc
  VIP: { bg: '#e879f9', border: '#d946ef', text: '#701a75' },  // fuchsia
};

/**
 * 레이어 타입별 시각화 색상 (단열재가 아닌 구조체 레이어용)
 */
export const LAYER_COLORS = {
  concrete:  { bg: '#94a3b8', border: '#64748b', label: '콘크리트' },
  brick:     { bg: '#d97706', border: '#b45309', label: '벽돌' },
  gypsum:    { bg: '#e2e8f0', border: '#cbd5e1', label: '석고보드' },
  plaster:   { bg: '#fef3c7', border: '#fde68a', label: '마감재' },
  default:   { bg: '#cbd5e1', border: '#94a3b8', label: '기타' },
};

/**
 * 레이어 이름으로 시각화 색상을 결정하는 유틸 함수
 */
export const getLayerColor = (layerName, isInsulation, category) => {
  if (isInsulation && category) {
    return INSULATION_COLORS[category] || INSULATION_COLORS.EPS;
  }
  if (isInsulation) {
    return { bg: '#fb923c', border: '#f97316', text: '#7c2d12' }; // default insulation orange
  }

  const name = (layerName || '').toLowerCase();
  if (name.includes('concrete') || name.includes('콘크리트')) return LAYER_COLORS.concrete;
  if (name.includes('brick') || name.includes('벽돌')) return LAYER_COLORS.brick;
  if (name.includes('gypsum') || name.includes('석고')) return LAYER_COLORS.gypsum;
  if (name.includes('plaster') || name.includes('마감') || name.includes('finish')) return LAYER_COLORS.plaster;
  return LAYER_COLORS.default;
};
