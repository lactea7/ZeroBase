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
    // 1차에너지 계수는 열원마다 다르다(전기 2.75 / 지역난방 0.728 / 가스·등유 1.10).
    // 백엔드가 항목별로 계산해 matrix 에 담아 주므로 그대로 쓴다.
    {
      name: '1차 소요량',
      ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.primary || 0) }), {}),
    },
    {
      name: '등급용 1차',
      ...categoriesList.reduce((acc, c) => ({ ...acc, [c.name]: Number(m[c.id]?.gradePrimary || 0) }), {}),
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

  // ⚠️ IRR 은 **null 일 수 있다** — 현금흐름이 부호를 바꾸지 않으면 IRR 이 존재하지
  // 않는다(회수 불가 또는 투자 없음). 예전엔 `f.irr || 0` 으로 0 을 넣어 "IRR 0%"로
  // 표시했는데, "정의되지 않음"과 "0%"는 전혀 다른 뜻이다.
  const irr = f.irr ?? null;

  // ⚠️ 회수기간은 **백엔드 값을 그대로 쓴다.** 여기서 다시 계산하면 할인율·
  // 요금상승률·유지비·10년차 LED 교체·15년차 HVAC 교체가 빠져 백엔드 NPV/IRR 과
  // 다른 답이 나온다(차트와 지표가 서로 어긋난다).
  // null = 분석기간 내 미회수. 예전엔 0 을 넣어 '즉시 회수'처럼 보였다.
  const paybackYears = f.simple_payback_years ?? null;

  return { data, annualSavings, paybackYears, npv, irr, params, baselineAssumptions: f.baseline_assumptions };
};
