// 프런트 시험 공통 설정.
//
// ⚠️ 여기에는 **브라우저 전용 API 대역만** 둔다. 앱 로직이나 앱이 쓰는 라이브러리를
// 여기서 전역 mock 하면 시험이 조용히 무력해진다. 하나 늘릴 때마다
// "이게 브라우저 기능인가, 우리 코드인가"를 먼저 물을 것.
//
// ⚠️ 예전에 `@react-three/fiber`·`drei` 를 전역 mock 했는데, **앱은 그 패키지를
// 쓰지 않는다**(`BuildingViewer` 가 raw `three` 의 WebGLRenderer 를 직접 쓴다).
// 아무것도 가리지 않으면서 3D 단계 렌더를 가능하게 해주지도 않는 죽은 mock 이었다.
// 3D 화면이 필요한 시험은 `BuildingViewer` 를 **그 시험 파일 안에서** mock 할 것.
import '@testing-library/jest-dom/vitest';

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
