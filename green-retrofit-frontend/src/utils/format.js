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
