/**
 * App 렌더 스모크 — **리팩터링 안전망**.
 *
 * `App.jsx` 는 1,963줄 / useState 30개다. 이걸 pages/reducer 로 쪼개는 동안
 * "화면이 아예 안 뜨는" 회귀를 잡을 최소한의 그물이 필요하다.
 *
 * ⚠️ 예전 App.jsx 분해 때 JSX 만 옮기고 컴포넌트 안에 남은 const/아이콘 때문에
 * **백지 화면**이 된 적이 있다. 빌드가 통과해도 안 잡힌다 — 렌더해야 잡힌다.
 *
 * 여기서 확인하는 것은 "뜨는가"와 "첫 단계 전환이 되는가"뿐이다.
 * 화면 내용 검증은 각 컴포넌트 시험의 몫이다.
 */
import { describe, expect, it, vi } from 'vitest';
import { render, waitFor } from '@testing-library/react';

vi.mock('../api/client.js', () => ({
  default: { post: vi.fn(), get: vi.fn() },
  uploadGbxml: vi.fn(),
  runSimulation: vi.fn(),
}));

const App = (await import('../App.jsx')).default;

describe('App 첫 화면', () => {
  it('예외 없이 마운트된다', () => {
    // ⚠️ 이 한 줄이 백지 화면 회귀를 잡는다. 빌드 통과로는 안 잡힌다.
    expect(() => render(<App />)).not.toThrow();
  });

  it('랜딩이 실제로 그려진다', () => {
    const { container } = render(<App />);
    // ⚠️ `textContent.length > 0` 만 보면 안 된다 — App 은 거대한 <style> 블록을
    // 렌더하므로 UI 가 하나도 없어도 통과한다. 실제 요소를 찾는다.
    expect(container.querySelector('#zb-cta-start')).toBeTruthy();
    expect(container.textContent).toContain('시뮬레이션 시작');
  });

  it('렌더를 깨는 콘솔 오류가 없다', () => {
    const errors = [];
    const spy = vi.spyOn(console, 'error').mockImplementation((...a) => errors.push(a));
    render(<App />);
    spy.mockRestore();
    const fatal = errors.filter(([m]) =>
      typeof m === 'string' && /is not a function|Cannot read|undefined is not/.test(m));
    expect(fatal).toEqual([]);
  });
});

describe('랜딩 → 업로드 전환', () => {
  it('시작하면 gbXML 업로드 입력이 나타난다', async () => {
    const { container } = render(<App />);
    // 랜딩 단계에는 업로드 입력이 없다
    expect(container.querySelector('input[type="file"]')).toBeNull();

    container.querySelector('#zb-cta-start').click();

    // ⚠️ 이 전환이 깨지면 사용자는 **아무것도 시작할 수 없다.**
    await waitFor(() => {
      expect(container.querySelector('input[type="file"]')).toBeTruthy();
    });
    expect(container.textContent).toContain('gbXML 모델 업로드');
  });

  it('업로드 입력은 gbXML 확장자만 받는다', async () => {
    const { container } = render(<App />);
    container.querySelector('#zb-cta-start').click();

    await waitFor(() => expect(container.querySelector('input[type="file"]')).toBeTruthy());
    expect(container.querySelector('input[type="file"]').accept).toBe('.xml,.gbxml');
  });
});
