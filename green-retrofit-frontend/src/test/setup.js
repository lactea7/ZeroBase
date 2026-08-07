// 프런트 시험 공통 설정.
//
// ⚠️ 여기서 하는 mock 은 **브라우저 전용 API 를 대신하는 것뿐**이다. 앱 로직을
// mock 하면 시험이 아무것도 지키지 못한다. 하나 늘릴 때마다 "이게 브라우저
// 기능인가, 우리 코드인가"를 먼저 물을 것.
import '@testing-library/jest-dom/vitest';
import { vi } from 'vitest';

// jsdom 에 없는 브라우저 API — 없으면 컴포넌트가 마운트조차 못 한다.
if (!window.matchMedia) {
  window.matchMedia = (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => false,
  });
}

if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

if (!window.scrollTo) {
  window.scrollTo = () => {};
}

// WebGL 이 없어 three.js 캔버스는 jsdom 에서 못 돈다.
// ⚠️ 3D 뷰어 **자체**는 이 시험들이 검증하지 않는다. 나머지 화면을 보기 위한
// 대역일 뿐이므로, 뷰어 회귀는 여전히 눈으로 확인해야 한다.
vi.mock('@react-three/fiber', () => ({
  Canvas: ({ children }) => children ?? null,
  useFrame: () => {},
  useThree: () => ({ camera: {}, gl: {}, scene: {} }),
  extend: () => {},
}));

vi.mock('@react-three/drei', () => new Proxy({}, {
  get: () => ({ children }) => children ?? null,
}));
