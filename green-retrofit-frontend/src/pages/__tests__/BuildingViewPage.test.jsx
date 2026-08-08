/**
 * BuildingViewPage — 전체 건물 3D + 층 선택.
 *
 * ⚠️ **3D 뷰어만 있는 화면이 아니다.** 층 버튼이 유일한 상세 편집 진입점이라,
 * 여기가 깨지면 사용자는 평면도 편집으로 갈 수 없다.
 *
 * `BuildingViewer` 는 raw three(WebGLRenderer)라 jsdom 에서 못 돈다. **이 파일에서만**
 * mock 한다(전역 setup 에 두면 다른 시험까지 조용히 가린다). 실제 WebGL 렌더는
 * 브라우저에서 확인할 몫이고, 여기서는 **네비게이션과 배선**을 지킨다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const viewerProps = vi.fn();
vi.mock('../../components/viewer/BuildingViewer', () => ({
  default: (props) => {
    viewerProps(props);
    return <div data-testid="viewer" />;
  },
}));

const BuildingViewPage = (await import('../BuildingViewPage.jsx')).default;

const SURFACES = [{ id: 'S1', zone: 'Z1' }];
const ZONES = [{ id: 'Z1', floor: 1 }];

function props(overrides = {}) {
  return {
    isDarkMode: false,
    setStep: vi.fn(), setActiveFloor: vi.fn(), setSelectedId: vi.fn(),
    surfaces: SURFACES, zones: ZONES,
    displayFloors: [1, 2, 99],
    isVirtualFloor: (f) => f === 99,
    viewMode: 'solid', setViewMode: vi.fn(),
    sunMonth: 6, setSunMonth: vi.fn(),
    sunHour: 12, setSunHour: vi.fn(),
    res: null, latitude: 37.5,
    selectedRegion: { name: '서울' },
    ...overrides,
  };
}

beforeEach(() => viewerProps.mockReset());

describe('층 선택', () => {
  it('층마다 버튼이 하나씩 있다', () => {
    const { container } = render(<BuildingViewPage {...props()} />);
    const buttons = [...container.querySelectorAll('button')];
    expect(buttons).toHaveLength(3);
    expect(buttons.map((b) => b.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining('1F')]));
  });

  it('⚠️ 가상층(특수공간)을 구분해 표시한다', () => {
    // 구분이 없으면 사용자가 실제 층으로 오해한다
    const { container } = render(<BuildingViewPage {...props()} />);
    const virtual = [...container.querySelectorAll('button')]
      .find((b) => b.textContent.includes('99F'));
    expect(virtual.textContent).toContain('특수공간');
  });

  it('⚠️ 층을 누르면 평면도 편집으로 간다', async () => {
    // 이 경로가 유일한 상세 편집 진입점이다
    const p = props();
    const { container } = render(<BuildingViewPage {...p} />);
    const floor2 = [...container.querySelectorAll('button')]
      .find((b) => b.textContent.includes('2F'));

    await userEvent.click(floor2);
    expect(p.setActiveFloor).toHaveBeenCalledWith(2);
    expect(p.setStep).toHaveBeenCalledWith('floorView');
  });

  it('⚠️ 층을 옮기면 이전 선택을 지운다', async () => {
    // 안 지우면 다른 층의 면이 선택된 채로 편집 화면이 열린다
    const p = props();
    const { container } = render(<BuildingViewPage {...p} />);
    await userEvent.click(container.querySelectorAll('button')[0]);
    expect(p.setSelectedId).toHaveBeenCalledWith(null);
  });

  it('층이 없어도 깨지지 않는다', () => {
    expect(() => render(
      <BuildingViewPage {...props({ displayFloors: [] })} />)).not.toThrow();
  });
});

describe('뷰어 배선', () => {
  it('모델과 위치 정보를 그대로 넘긴다', () => {
    render(<BuildingViewPage {...props()} />);
    expect(viewerProps).toHaveBeenCalledWith(expect.objectContaining({
      surfaces: SURFACES, zones: ZONES, latitude: 37.5, locationName: '서울',
    }));
  });

  it('⚠️ 태양 경로 상태를 넘긴다 — 없으면 음영 분석이 고정된다', () => {
    render(<BuildingViewPage {...props()} />);
    expect(viewerProps).toHaveBeenCalledWith(expect.objectContaining({
      sunMonth: 6, sunHour: 12,
    }));
  });

  it('전체 건물 화면이므로 층 필터 없이 전부 보여준다', () => {
    render(<BuildingViewPage {...props()} />);
    expect(viewerProps.mock.calls[0][0].activeFloor).toBe('all');
  });

  it('결과가 있으면 뷰어에 전달한다 (표면 오버레이용)', () => {
    const res = { surfaceThermal: {} };
    render(<BuildingViewPage {...props({ res })} />);
    expect(viewerProps.mock.calls[0][0].res).toBe(res);
  });
});
