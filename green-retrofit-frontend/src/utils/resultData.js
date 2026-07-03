// utils/resultData.js - 결과 대시보드용 순수 데이터 변환 (시뮬레이션 res → 차트/지표)

// ZEB(제로에너지건축물) 인증 등급: 에너지 자립률 기준
export const getZebGradeInfo = (rate) => {
  const r = Number(rate) || 0;
  if (r >= 100) return '1등급';
  if (r >= 80) return '2등급';
  if (r >= 60) return '3등급';
  if (r >= 40) return '4등급';
  if (r >= 20) return '5등급';
  return '등급 외';
};

// 연간 에너지 매트릭스 → 요구량/소요량/1차 소요량 스택 차트 데이터
export const buildAnnualChartData = (res) => {
  if (!res || !res.matrix) return [];
  const m = res.matrix;
  const categoriesList = [
    { id: 'heating', name: '난방', color: '#F87171' },
    { id: 'cooling', name: '냉방', color: '#60A5FA' },
    { id: 'hotwater', name: '급탕', color: '#FB923C' },
    { id: 'lighting', name: '조명', color: '#FACC15' },
    { id: 'ventilation', name: '환기', color: '#4ADE80' },
    { id: 'equipment', name: '기기', color: '#A78BFA' },
    { id: 'renewable', name: '신재생', color: '#2DD4BF' },
  ];

  return [
    {
      name: '요구량',
      ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.req || 0) }), {}),
    },
    {
      name: '소요량',
      ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.con || 0) }), {}),
    },
    {
      name: '1차 소요량',
      ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.con || 0) * 2.75 }), {}),
    },
    {
      name: '등급용 1차',
      ...categoriesList.reduce((acc, c) => ({
        ...acc,
        [c.name]: c.id === 'equipment' ? 0 : Number(m[c.id]?.con || 0) * 2.1
      }), {}),
    },
  ];
};

// 💡 LCC(현금흐름) 차트 데이터 계산 로직
export const buildCashFlowData = (res) => {
  if (!res || !res.financial) return [];

  // 백엔드에서 계산된 값이 넘어오면 그것을 우선 사용
  const f = res.financial;
  const retrofitRunningCost = f.total_energy_bill;
  const capitalCost = f.capital_cost;
  // 기준 건물 운영비: 백엔드 baseline_assumptions와 단일 소스로 공유 → 차트/NPV/IRR 일관.
  //   실측 입력 시 base_running_cost가 내려오고, 없으면 1.6배 추정으로 환산.
  const ba = f.baseline_assumptions || {};
  const baseMultiplier = ba.running_cost_multiplier || 1.6;
  const baseRunningCost = ba.base_running_cost > 0 ? ba.base_running_cost : retrofitRunningCost * baseMultiplier;
  const annualSavings = baseRunningCost - retrofitRunningCost;

  const params = f.lcc_parameters || { inflation_rate: 2, lifecycle_years: 15 };
  const inflationRate = params.inflation_rate / 100;
  const years = params.lifecycle_years || 20;

  const data = [];
  let cumulativeBase = 0;
  let cumulativeRetrofit = -capitalCost;

  for (let year = 0; year <= years; year++) {
    if (year > 0) {
      cumulativeBase -= baseRunningCost * Math.pow(1 + inflationRate, year - 1);
      cumulativeRetrofit -= retrofitRunningCost * Math.pow(1 + inflationRate, year - 1);
    }

    data.push({
      year: `${year}년차`,
      '기존 노후건물 유지': Math.round(cumulativeBase),
      '친환경 리모델링 (투자+운영)': Math.round(cumulativeRetrofit),
      '누적 순이익 (ROI)': Math.round(cumulativeRetrofit - cumulativeBase),
    });
  }

  // 고급 재무 지표
  const npv = f.npv || 0;
  const irr = f.irr || 0;

  // payback 추산 (수익이 0을 돌파하는 시점)
  let paybackYears = capitalCost / annualSavings;
  let exactPayback = data.findIndex(d => d['누적 순이익 (ROI)'] >= 0);
  if (exactPayback > 0) {
    // 선형 보간으로 소수점 연도 추정
    const prev = data[exactPayback - 1]['누적 순이익 (ROI)'];
    const curr = data[exactPayback]['누적 순이익 (ROI)'];
    paybackYears = (exactPayback - 1) + Math.abs(prev) / (curr - prev);
  } else {
    paybackYears = 0;
  }

  return { data, annualSavings, paybackYears, npv, irr, params, baselineAssumptions: f.baseline_assumptions };
};
