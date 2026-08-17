/**
 * ResultDashboard — 결과 화면이 **뜨기는 하는가**.
 *
 * ⚠️ 이 시험이 없어서 흰 화면 사고가 났다. `<AnimatePresence>` 의 import 를
 * 빠뜨린 채 lint·build·시험 401건이 전부 통과했고, 시뮬레이션이 끝나 결과 화면이
 * 열리는 순간 `ReferenceError` 로 트리 전체가 무너졌다.
 *
 * ⚠️ 번들러는 이걸 못 잡는다 — 미정의 JSX 요소는 컴파일 오류가 아니라 **런타임**
 * 오류다. eslint `react/jsx-no-undef` 로도 막았지만, 렌더가 실제로 되는지는
 * 렌더해 봐야 안다.
 *
 * 그래서 이 시험은 값을 검증하지 않는다. **컴포넌트가 예외 없이 마운트되는지**만 본다.
 */
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import ResultDashboard from '../ResultDashboard.jsx';

// 3D 뷰어는 WebGL 을 요구한다 — jsdom 에 없으므로 대체한다.
vi.mock('../../viewer/BuildingViewer', () => ({
  default: () => <div data-testid="viewer" />,
}));

const THEME = {
  textMain: 'text-main', textSub: 'text-sub', card: 'card',
  border: 'border', bg: 'bg', input: 'input',
};

const RES = {
  eui: 120, totalEnergy: 100000, floorArea: 1000,
  breakdown: { 난방: 40, 냉방: 30, 조명: 10, 기기: 10, 급탕: 5, 환기: 5, 신재생: 0 },
  monthly: [], zones: [], assumptions: [],
};

const baseProps = {
  theme: THEME,
  res: RES,
  isDarkMode: true,
  lccAnalysis: null,
  zones: [],
  surfaces: [],
  setStep: vi.fn(),
  handleApplyRecommendations: vi.fn(),
  getZebGradeInfo: () => ({ grade: '1++', color: '#0f0', label: '1++' }),
  getAnnualChartData: () => [],
  viewMode: 'default',
  setViewMode: vi.fn(),
  sunMonth: 6, setSunMonth: vi.fn(),
  sunHour: 12, setSunHour: vi.fn(),
  latitude: 37.56,
  selectedRegion: 'KOR_SO_Seoul',
  projectData: { name: 'T' },
};

describe('ResultDashboard 마운트', () => {
  it('결과가 있을 때 예외 없이 렌더된다', () => {
    expect(() => render(<ResultDashboard {...baseProps} />)).not.toThrow();
  });

  it('⚠️ 경제성 결과가 아직 없어도 죽지 않는다', () => {
    expect(() => render(<ResultDashboard {...baseProps} lccAnalysis={null} />)).not.toThrow();
  });

  it('⚠️ 가정 목록이 비어 있어도 죽지 않는다', () => {
    const res = { ...RES, assumptions: [] };
    expect(() => render(<ResultDashboard {...baseProps} res={res} />)).not.toThrow();
  });
});
