/**
 * 마법사 페이지 렌더 스모크.
 *
 * ⚠️ App 스모크는 landing→upload 만 지난다. 나머지 단계는 UI 경로가 길어(업로드
 * →설정→…) App 시험으로는 안 닿는다. 추출한 페이지를 **직접 렌더**해 백지 화면
 * 회귀를 잡는다 — 아이콘·헬퍼 import 누락은 **빌드로는 안 잡히고 런타임에만**
 * 죽는다(이번 추출에서 실제로 두 번 발생했다).
 */
import { describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';

import BudgetPage from '../BudgetPage.jsx';
import FinancialPage from '../FinancialPage.jsx';
import ProjectInfoPage from '../ProjectInfoPage.jsx';
import RenewablePage from '../RenewablePage.jsx';
import UploadPage from '../UploadPage.jsx';

const THEME = {
  bg: '', card: 'card', panel: '', textMain: 'main', textSub: 'sub', input: 'input',
  tableHeader: '', tableBorder: '', chartText: '#000', chartGrid: '#000', pieBg: '#000',
};

// ⚠️ **App 의 초기 `projectData` 모양을 그대로 따른다.** 페이지의 계약은 그
// 상태이고, 여기서 임의로 줄이면 있지도 않은 결함을 쫓게 된다(실제로 그랬다).
const PROJECT = {
  name: '테스트', activityId: 1105, location: 'KOR_SO_Seoul',
  pvCapacity: 0, heatSource: 11, geothermalApplied: false,
  promoteGroundFloors: false, hvacUpgradeActive: false, orientation: 0,
  targetBudget: 0, ledFixtureCount: 0,
  baselineActual: { mode: 'bill', elecBill: '', heatBill: '', elecKwh: '', heatKwh: '' },
  lccParameters: {
    discountRate: 5.0, inflationRate: 3.0, utilityInflation: 4.0, lifecycleYears: 20,
  },
  customSchedule: { useCustom: false, mode: 'simplified', holidays: [] },
};

const common = () => ({
  theme: THEME, isDarkMode: false, setStep: vi.fn(),
  projectData: PROJECT, setProjectData: vi.fn(),
});

const PAGES = [
  ['UploadPage', UploadPage, {
    ...common(), setShowGuide: vi.fn(), surfaces: [], zones: [], uploadedFile: null,
    fileInputRef: { current: null },
    handleFileUpload: vi.fn(), handleStartWithSample: vi.fn(),
    setSurfaces: vi.fn(), setZones: vi.fn(), setUploadedFile: vi.fn(),
    setMaterials: vi.fn(), setConstructionOverrides: vi.fn(),
  }],
  ['ProjectInfoPage', ProjectInfoPage, {
    ...common(), scheduleEditorRef: { current: null },
  }],
  ['RenewablePage', RenewablePage, {
    ...common(), zones: [{ id: 'Z1', area: 100 }],
    groundEligible: { count: 0, area: 0 },
  }],
  ['BudgetPage', BudgetPage, common()],
  ['FinancialPage', FinancialPage, common()],
];

describe.each(PAGES)('%s', (name, Page, props) => {
  it('예외 없이 렌더된다', () => {
    // ⚠️ import 누락은 빌드를 통과하고 여기서만 죽는다
    expect(() => render(<Page {...props} />)).not.toThrow();
  });

  it('빈 화면이 아니다', () => {
    const { container } = render(<Page {...props} />);
    expect(container.textContent.trim().length).toBeGreaterThan(10);
  });

  it('렌더를 깨는 콘솔 오류가 없다', () => {
    const errors = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...a) => errors.push(a));
    render(<Page {...props} />);
    spy.mockRestore();
    const fatal = errors.filter(([m]) =>
      typeof m === 'string' && /is not defined|is not a function|Cannot read/.test(m));
    expect(fatal).toEqual([]);
  });
});

describe('빈 데이터 방어', () => {
  it('⚠️ RenewablePage 는 존이 없어도 깨지지 않는다', () => {
    // 파싱 직후 존이 비어 있을 수 있다
    expect(() => render(
      <RenewablePage {...common()} zones={[]} groundEligible={{ count: 0, area: 0 }} />
    )).not.toThrow();
  });

  it('⚠️ 예산 미설정(0)도 정상 표시한다', () => {
    // 0 은 "제한 없음"이지 오류가 아니다
    const { container } = render(
      <BudgetPage {...common()} projectData={{ ...PROJECT, targetBudget: 0 }} />);
    expect(container.textContent).toMatch(/미설정|제한없음/);
  });
});
