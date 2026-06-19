// data/hvac.js - HVAC 시스템, 연료, 환기 타입 상수 데이터

export const HVAC_SYSTEMS = [
  { id: 1, name: '공기조화기 (Air handling unit)' },
  { id: 2, name: '개별 히트펌프 (Unitary heat pump - EHP/GHP)' },
  { id: 3, name: '팬코일유닛 (Unitary heat cool - FCU)' },
  { id: 5, name: '일반 개별 냉난방기 (Generic unitary)' },
];

export const FUEL_TYPES = [
  { id: 2, name: '전기 (Electricity)' },
  { id: 11, name: '지역 난방 (District Heating)' },
];

export const VENT_TYPES = [
  { id: 1, name: '정풍량 제어 (Constant volume - CAV)' },
  { id: 2, name: '변풍량 제어 (Variable volume - VAV)' },
  { id: 3, name: '단순 On/Off 제어 (On/Off)' },
];
