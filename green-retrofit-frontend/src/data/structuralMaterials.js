// data/structuralMaterials.js - 외장재, 구조체, 내장재 데이터베이스 (에너지플러스 호환)

export const STRUCTURAL_MATERIALS = [
  // ── 바깥 외벽 (Outer Finish) ──
  { id: 'O1', name: '적벽돌 (Brickwork)', category: 'OUTER', conductivity: 0.84, density: 1700, specificHeat: 800, defaultThickness: 90 },
  { id: 'O2', name: '외장 시멘트 렌더 (External Rendering)', category: 'OUTER', conductivity: 0.50, density: 1300, specificHeat: 1000, defaultThickness: 15 },
  { id: 'O3', name: '석재 마감 (Stone Finish)', category: 'OUTER', conductivity: 1.50, density: 2500, specificHeat: 800, defaultThickness: 30 },
  { id: 'O4', name: '아스팔트 슁글/마감', category: 'OUTER', conductivity: 0.70, density: 2100, specificHeat: 1000, defaultThickness: 10 },
  { id: 'O5', name: '알루미늄 복합 패널', category: 'OUTER', conductivity: 200.0, density: 2700, specificHeat: 900, defaultThickness: 5 }, // 열전도율이 매우 높아 R값이 거의 0에 수렴
  { id: 'O6', name: '스타코 마감 (Stucco)', category: 'OUTER', conductivity: 0.72, density: 1850, specificHeat: 840, defaultThickness: 20 },
  { id: 'O7', name: '징크 패널 (Zinc Panel)', category: 'OUTER', conductivity: 110.0, density: 7140, specificHeat: 390, defaultThickness: 2 },
  { id: 'O8', name: '목재 사이딩 (Wood Siding)', category: 'OUTER', conductivity: 0.14, density: 600, specificHeat: 1200, defaultThickness: 15 },
  { id: 'O9', name: '화강석 패널 (Granite)', category: 'OUTER', conductivity: 2.80, density: 2600, specificHeat: 1000, defaultThickness: 30 },
  { id: 'O10', name: '스틸 패널 (Steel Panel)', category: 'OUTER', conductivity: 50.0, density: 7800, specificHeat: 450, defaultThickness: 3 },
  
  // ── 구조체 (Core Structure) ──
  { id: 'C1', name: '일반 철근 콘크리트', category: 'CORE', conductivity: 1.13, density: 2000, specificHeat: 1000, defaultThickness: 200 },
  { id: 'C2', name: '고밀도 콘크리트', category: 'CORE', conductivity: 1.40, density: 2100, specificHeat: 840, defaultThickness: 200 },
  { id: 'C3', name: '중공 콘크리트 블록', category: 'CORE', conductivity: 0.51, density: 1400, specificHeat: 1000, defaultThickness: 150 },
  { id: 'C4', name: '구조용 목재 (Timber)', category: 'CORE', conductivity: 0.14, density: 650, specificHeat: 1200, defaultThickness: 100 },
  { id: 'C5', name: '조적조 (구조용 벽돌)', category: 'CORE', conductivity: 0.84, density: 1700, specificHeat: 800, defaultThickness: 190 },
  { id: 'C6', name: 'ALC 블록 (경량기포콘크리트)', category: 'CORE', conductivity: 0.11, density: 500, specificHeat: 1000, defaultThickness: 200 },
  { id: 'C7', name: '프리캐스트 콘크리트 (PC)', category: 'CORE', conductivity: 1.63, density: 2200, specificHeat: 840, defaultThickness: 150 },
  { id: 'C8', name: '경량 철골조 (Light Gauge Steel)', category: 'CORE', conductivity: 50.0, density: 7800, specificHeat: 450, defaultThickness: 100 },
  { id: 'C9', name: '황토/흙벽돌', category: 'CORE', conductivity: 0.60, density: 1600, specificHeat: 850, defaultThickness: 150 },

  // ── 내장재 (Inner Finish) ──
  { id: 'I1', name: '석고보드 (Gypsum Board)', category: 'INNER', conductivity: 0.25, density: 900, specificHeat: 1000, defaultThickness: 9.5 },
  { id: 'I2', name: '내부 시멘트 미장', category: 'INNER', conductivity: 0.40, density: 1000, specificHeat: 1000, defaultThickness: 10 },
  { id: 'I3', name: '시멘트 모르타르 (Screed)', category: 'INNER', conductivity: 0.41, density: 1200, specificHeat: 840, defaultThickness: 30 },
  { id: 'I4', name: '목재 패널 (Wood Flooring/Panel)', category: 'INNER', conductivity: 0.14, density: 650, specificHeat: 1200, defaultThickness: 15 },
  { id: 'I5', name: '타일 마감 (Ceramic Tile)', category: 'INNER', conductivity: 1.20, density: 2300, specificHeat: 840, defaultThickness: 10 },
  { id: 'I6', name: '합판 (Plywood)', category: 'INNER', conductivity: 0.13, density: 540, specificHeat: 1210, defaultThickness: 12 },
  { id: 'I7', name: '대리석 타일 (Marble)', category: 'INNER', conductivity: 2.80, density: 2600, specificHeat: 800, defaultThickness: 20 },
  { id: 'I8', name: '흡음 텍스 (Acoustic Tile)', category: 'INNER', conductivity: 0.06, density: 300, specificHeat: 1300, defaultThickness: 15 },
  { id: 'I9', name: '벽지 마감 (Wallpaper)', category: 'INNER', conductivity: 0.10, density: 600, specificHeat: 1200, defaultThickness: 2 }
];

export const getMaterialsByCategory = (category) => {
  return STRUCTURAL_MATERIALS.filter(m => m.category === category);
};
