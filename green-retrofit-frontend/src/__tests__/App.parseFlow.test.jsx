/**
 * 업로드 흐름이 **실행 상태머신을 실제로 쓰는지**.
 *
 * ⚠️ `ExecAction.PARSE_*` 를 만들고 전이 시험까지 붙였는데, App 은 여전히
 * `setStep('parsing')` 을 부르고 있었다 — **상태머신이 죽은 코드였다**(codex 지적).
 * reducer 시험은 통과하는데 앱은 그 규칙을 안 따르는 상태였다.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';

const uploadGbxml = vi.fn();
vi.mock('../api/client.js', () => ({
  default: { post: vi.fn(), get: vi.fn() },
  uploadGbxml: (...a) => uploadGbxml(...a),
  runSimulation: vi.fn(),
}));

const App = (await import('../App.jsx')).default;

const OK = { data: { zones: [{ id: 'Z1', floor: 1, area: 100 }], surfaces: [{ id: 'S1', zone: 'Z1' }] } };
const FILE = () => new File(['<gbXML/>'], 'b.xml', { type: 'text/xml' });

async function upload() {
  const view = render(<App />);
  await userEvent.click(view.container.querySelector('#zb-cta-start'));
  await waitFor(() => expect(view.container.querySelector('input[type="file"]')).toBeTruthy());
  await userEvent.upload(view.container.querySelector('input[type="file"]'), FILE());
  return view;
}

beforeEach(() => {
  uploadGbxml.mockReset();
  // 앱이 파싱 오류를 일부러 콘솔에 남긴다 — 시험 출력에서는 가린다.
  vi.spyOn(console, 'error').mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

describe('파싱 단계 전이', () => {
  it('성공하면 업로드 화면으로 돌아가 모델을 보여준다', async () => {
    uploadGbxml.mockResolvedValue(OK);
    const { container } = await upload();
    await waitFor(() => expect(container.textContent).toContain('b.xml'));
    // 오류 화면 문구가 없어야 한다
    expect(container.textContent).not.toMatch(/연결 실패/);
  });

  it('⚠️ 실패하면 오류 화면에 머문다', async () => {
    // upload 로 넘기면 사용자가 아무 안내도 못 받고 튕긴다
    uploadGbxml.mockRejectedValue({ response: { data: { detail: '존이 없습니다' } } });
    const { container } = await upload();
    await waitFor(() => expect(container.textContent).toContain('존이 없습니다'));
    // 드롭존(업로드 화면)이 아니라 오류 화면이어야 한다
    expect(container.querySelector('input[type="file"]')).toBeNull();
  });

  it('실패 후 "다시 업로드 시도"로 돌아갈 수 있다', async () => {
    uploadGbxml.mockRejectedValue(new Error('boom'));
    const { container } = await upload();
    await waitFor(() => expect(container.textContent).toMatch(/실패|응답이 없/));
    const retry = [...container.querySelectorAll('button')]
      .find((b) => /다시 업로드/.test(b.textContent));
    await userEvent.click(retry);
    await waitFor(() =>
      expect(container.querySelector('input[type="file"]')).toBeTruthy());
  });
});
