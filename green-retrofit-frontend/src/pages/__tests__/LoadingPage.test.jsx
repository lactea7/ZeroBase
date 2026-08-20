/**
 * LoadingPage — 30분짜리 대기 화면.
 *
 * ⚠️ 진행 표시가 사라지면 사용자는 멈춘 것인지 도는 것인지 알 수 없어 창을 닫는다.
 * 그러면 30분이 버려지고 백엔드 작업도 헛돈다.
 */
import { describe, expect, it } from 'vitest';
import { render } from '@testing-library/react';
import LoadingPage from '../LoadingPage.jsx';
import { stageMessage } from '../../utils/loadingStage.js';

const THEME = { textMain: 'text-main', textSub: 'text-sub' };

describe('stageMessage', () => {
  it.each([
    ['queued', /대기열/],
    ['baseline', /개선 전/],
    ['retrofit', /개선안/],
    ['alt:window', /대안/],
    ['alt:insulation_upgrade', /대안/],
  ])('백엔드 단계 %s 를 사용자 문구로 옮긴다', (stage, pattern) => {
    expect(stageMessage(stage)).toMatch(pattern);
  });

  it.each([undefined, null, '', 'running', '알수없는단계'])(
    '⚠️ 단계를 몰라도(%s) 빈 문구를 내지 않는다', (stage) => {
      // 비면 멈춘 것처럼 보인다
      expect(stageMessage(stage).trim().length).toBeGreaterThan(0);
    });

  it('개선 전과 개선 후를 구분한다', () => {
    // ⚠️ 같은 문구면 사용자가 두 번 도는 이유를 모른다
    expect(stageMessage('baseline')).not.toBe(stageMessage('retrofit'));
  });
});

describe('LoadingPage 렌더', () => {
  it('진행 단계 문구를 보여준다', () => {
    const { container } = render(
      <LoadingPage theme={THEME} loadingMsgIdx={0} loadingStage="baseline" />);
    expect(container.textContent).toContain(stageMessage('baseline'));
  });

  it('단계가 없어도 안내 문구가 나온다', () => {
    const { container } = render(
      <LoadingPage theme={THEME} loadingMsgIdx={0} loadingStage={null} />);
    expect(container.textContent).toContain('EnergyPlus');
  });

  it('로딩 애니메이션이 있다', () => {
    const { container } = render(
      <LoadingPage theme={THEME} loadingMsgIdx={0} loadingStage={null} />);
    expect(container.querySelector('.loading-wrapper')).toBeTruthy();
  });

  it('⚠️ 메시지 인덱스가 범위를 벗어나도 깨지지 않는다', () => {
    // 타이머가 계속 도는 동안 인덱스가 커진다 — 여기서 죽으면 로딩 화면이 백지가 된다
    expect(() => render(
      <LoadingPage theme={THEME} loadingMsgIdx={9999} loadingStage={null} />)).not.toThrow();
  });
});

// ── 배포 환경의 대기 단계 (Render 콜드 스타트) ───────────────────────────────
describe('배포 환경 단계 문구', () => {
  it.each([
    ['waking', /깨우는 중/],
    ['reconnecting', /계속 진행/],
  ])('⚠️ %s 단계에 문구가 있어야 한다 — 비면 사용자가 창을 닫는다', (stage, pattern) => {
    expect(stageMessage(stage)).toMatch(pattern);
  });

  it('⚠️ 재연결 문구는 실패처럼 읽히면 안 된다', () => {
    // 계산은 서버에서 계속 돈다. '실패'로 읽히면 사용자가 창을 닫아 그걸 버린다.
    const msg = stageMessage('reconnecting');
    expect(msg).not.toMatch(/실패|오류|중단/);
  });
});
