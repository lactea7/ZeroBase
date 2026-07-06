// data/hvac.js - HVAC 시스템, 연료, 환기 타입 상수 데이터

export const HVAC_SYSTEMS = [
  { id: 1, name: '공기조화기 (Air handling unit)' },
  { id: 2, name: '개별 히트펌프 (Unitary heat pump - EHP/GHP)' },
  { id: 3, name: '팬코일유닛 (Unitary heat cool - FCU)' },
  { id: 5, name: '일반 개별 냉난방기 (Generic unitary)' },
];

export const FUEL_TYPES = [
  { id: 1, name: '가스보일러 (Natural Gas)' },
  { id: 2, name: '전기 (Electricity)' },
  { id: 4, name: '등유보일러 (Fuel Oil)' },
  { id: 11, name: '지역 난방 (District Heating)' },
];

// 냉방기(에어컨) 등급/연식 — 백엔드 COOLING_COP_BY_GRADE와 키 일치
export const COOLING_GRADES = [
  { id: 'grade1', name: '1등급 신형' },
  { id: 'grade3', name: '일반 (3등급)' },
  { id: 'grade5', name: '5등급' },
  { id: 'old10', name: '10년 노후' },
  { id: 'old15', name: '15년 이상 노후' },
];

// 난방기(보일러·히트펌프) 연식 — 백엔드 HEATING_EFF_FACTOR_BY_AGE와 키 일치
export const HEATING_AGES = [
  { id: 'new', name: '신형 (5년 이내)' },
  { id: 'mid', name: '보통 (5~10년, 효율 −7%)' },
  { id: 'old', name: '노후 (10년 이상, 효율 −15%)' },
];

export const VENT_TYPES = [
  { id: 1, name: '정풍량 제어 (Constant volume - CAV)' },
  { id: 2, name: '변풍량 제어 (Variable volume - VAV)' },
  { id: 3, name: '단순 On/Off 제어 (On/Off)' },
];
