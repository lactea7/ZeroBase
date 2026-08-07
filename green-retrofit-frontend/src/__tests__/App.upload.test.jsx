/**
 * 업로드 → 설정 진입: **화면 간 계약**.
 *
 * `App.jsx` 를 pages/reducer 로 쪼개는 동안, 각 화면의 세부 UI 가 아니라
 * "화면과 화면 사이에 무엇이 오가는가"를 지킨다. 세부는 추출된 페이지의 몫이다.
 *
 * ⚠️ 특히 **응답 매핑**이 중요하다. 백엔드가 용도별 아키타입으로 채워 내려준
 * 내부발열을 프런트가 덮어쓰면, 화장실·계단실에도 사무실 부하가 들어가 백엔드의
 * 용도별 구분이 통째로 무력화된다. 그건 화면에 안 보이고 결과 숫자로만 나타난다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const uploadGbxml = vi.fn();
const runSimulation = vi.fn();

vi.mock('../api/client.js', () => ({
  default: { post: vi.fn(), get: vi.fn() },
  uploadGbxml: (...a) => uploadGbxml(...a),
  runSimulation: (...a) => runSimulation(...a),
}));

const App = (await import('../App.jsx')).default;

const ZONE = {
  id: 'Z1', name: '사무실', floor: 1, area: 100, height: 3,
  activityId: 1105, isConditioned: true,
};

function parseResponse(overrides = {}) {
  return {
    data: {
      zones: [ZONE],
      surfaces: [{ id: 'S1', type: 'ExteriorWall', zone: 'Z1', uValue: 0.5 }],
      ...overrides,
    },
  };
}

/** 랜딩 → 업로드 화면까지 진행하고 파일 입력을 돌려준다. */
async function reachUpload() {
  const view = render(<App />);
  await userEvent.click(view.container.querySelector('#zb-cta-start'));
  await waitFor(() => expect(view.container.querySelector('input[type="file"]')).toBeTruthy());
  return view;
}

const FILE = () => new File(['<gbXML/>'], 'b.xml', { type: 'text/xml' });

beforeEach(() => {
  uploadGbxml.mockReset();
  runSimulation.mockReset();
});

describe('업로드 성공', () => {
  it('파일을 백엔드로 보낸다', async () => {
    uploadGbxml.mockResolvedValue(parseResponse());
    const { container } = await reachUpload();

    await userEvent.upload(container.querySelector('input[type="file"]'), FILE());
    await waitFor(() => expect(uploadGbxml).toHaveBeenCalledTimes(1));
    expect(uploadGbxml.mock.calls[0][0]).toBeInstanceOf(File);
  });

  it('파싱된 존이 화면에 반영된다', async () => {
    uploadGbxml.mockResolvedValue(parseResponse());
    const { container } = await reachUpload();

    await userEvent.upload(container.querySelector('input[type="file"]'), FILE());
    await waitFor(() => expect(container.textContent).toContain('b.xml'));
  });

  it('면 갭 경고를 삼키지 않는다', async () => {
    // ⚠️ 경고가 사라지면 사용자는 기하가 깨진 모델을 그대로 돌린다
    uploadGbxml.mockResolvedValue(parseResponse({
      warnings: [{ id: 'S9', message: '면 갭 발견' }],
    }));
    const { container } = await reachUpload();

    await userEvent.upload(container.querySelector('input[type="file"]'), FILE());
    await waitFor(() => expect(uploadGbxml).toHaveBeenCalled());
    await waitFor(() => expect(container.textContent).toMatch(/경고|갭/));
  });
});

describe('업로드 실패', () => {
  it('백엔드가 알려준 사유를 그대로 보여준다', async () => {
    // ⚠️ "서버 응답 없음"으로 뭉개면 사용자가 파일을 고칠 수 없다
    uploadGbxml.mockRejectedValue({
      response: { data: { detail: 'Space 에 Surface 참조가 없습니다' } },
    });
    const { container } = await reachUpload();

    await userEvent.upload(container.querySelector('input[type="file"]'), FILE());
    await waitFor(() =>
      expect(container.textContent).toContain('Space 에 Surface 참조가 없습니다'));
  });

  it('사유가 없어도 빈 화면이 아니라 안내를 낸다', async () => {
    uploadGbxml.mockRejectedValue(new Error('Network Error'));
    const { container } = await reachUpload();

    await userEvent.upload(container.querySelector('input[type="file"]'), FILE());
    await waitFor(() => expect(container.textContent).toMatch(/실패|응답이 없/));
  });

  it('오류 화면에서 다시 시도할 수 있다', async () => {
    uploadGbxml.mockRejectedValue(new Error('boom'));
    const { container } = await reachUpload();

    await userEvent.upload(container.querySelector('input[type="file"]'), FILE());
    await waitFor(() => expect(container.textContent).toMatch(/실패|응답이 없/));

    // ⚠️ 막다른 길이면 안 된다 — 되돌아갈 버튼이 있어야 한다
    const retry = [...container.querySelectorAll('button')]
      .find((b) => /다시 업로드/.test(b.textContent));
    expect(retry).toBeTruthy();

    await userEvent.click(retry);
    await waitFor(() =>
      expect(container.querySelector('input[type="file"]')).toBeTruthy());
  });
});

// 응답 매핑(내부발열 보존·명시된 0)은 `utils/__tests__/parseResponse.test.js` 에서
// **값으로** 검증한다. 여기서 렌더로 보려 했더니 "사무실 문구가 없다" 수준이라
// 값이 덮여도 통과했다 — 화면에 안 보이고 결과 숫자로만 나타나는 회귀다.
