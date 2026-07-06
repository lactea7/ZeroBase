// utils/format.js - 포맷팅 및 범용 유틸리티 함수

export const LOADING_MESSAGES = [
  'Python 백엔드로 시뮬레이션 Payload(JSON) 전송 중...',
  'EnergyPlus 모델(IDF) 동적 생성 및 양면 구조체(Twin-Surface) 변환 중...',
  '선택한 지역의 기상 파일(.epw) 매핑 및 맵 데이터 연동 중...',
  '사용자 정의 HVAC 시스템 및 내부 발열/공조 존 맵핑 중...',
  'EnergyPlus 8760시간 열역학 시뮬레이션 가동 중 (Simulating)...',
];

export const DIR_MAP = {
  South: '남향',
  North: '북향',
  East: '동향',
  West: '서향',
  Roof: '지붕',
  Floor: '바닥',
};

export const groupBy = (array, keyFn) => {
  return array.reduce((result, item) => {
    const key = keyFn(item);
    if (!result[key]) {
      result[key] = [];
    }
    result[key].push(item);
    return result;
  }, {});
};

// 숫자를 원화(만 원) 포맷으로 변환하는 유틸
export const formatWon = (val) => {
  if (!val) return '0 원';
  return Math.round(val / 10000).toLocaleString() + ' 만 원';
};

// 차트 축용 짧은 원화 표기 — 값 크기에 맞는 단위(억/천만/백만/만)를 고른다.
// (단위를 천만으로 고정하면 ±1천만 이내 값이 전부 '0천만'으로 뭉개진다)
export const formatWonShort = (val) => {
  const abs = Math.abs(val);
  if (abs >= 100_000_000) {
    const eok = val / 100_000_000;
    return `${Number.isInteger(eok) ? eok : eok.toFixed(1)}억`;
  }
  if (abs >= 10_000_000) return `${Math.round(val / 10_000_000)}천만`;
  if (abs >= 1_000_000) return `${Math.round(val / 1_000_000)}백만`;
  if (abs >= 10_000) return `${Math.round(val / 10_000)}만`;
  return val === 0 ? '0' : `${Math.round(val).toLocaleString()}원`;
};
