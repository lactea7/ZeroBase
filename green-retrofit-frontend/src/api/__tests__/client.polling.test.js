/**
 * runSimulation 폴링 복원력.
 *
 * ⚠️ 예전에는 상태 조회가 **한 번만** 실패해도 예외가 루프 밖으로 나가
 * 진행 중인 작업을 통째로 버렸다. 서버는 계속 계산하고 있는데 사용자 화면만
 * 실패로 끝나는 것이라, 수 분짜리 계산이 네트워크 한 번 끊긴 것으로 사라졌다.
 *
 * ⚠️ 배포(Render 무료)는 15분 무요청이면 잠든다 — 콜드 스타트 실측 32.7초.
 * 그 사이의 실패도 여기에 걸린다.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('axios', () => {
  const inst = { post: vi.fn(), get: vi.fn() };
  return { default: { create: () => inst, __inst: inst } };
});

const axios = (await import('axios')).default;
const inst = axios.__inst;
const { runSimulation } = await import('../client.js');

const accepted = { data: { status: 'accepted', task_id: 'T1' } };
const done = { data: { status: 'success', eui: 100 } };

beforeEach(() => {
  vi.useFakeTimers();
  inst.post.mockReset();
  inst.get.mockReset();
});
afterEach(() => {
  // ⚠️ 남은 타이머를 비우고 실시간으로 되돌린다. 정리하지 않으면 파일이 통과한
  // 뒤 실행기 정리 단계에서 힙이 터진다(실측: 이 파일 하나만 돌려도 재현).
  vi.clearAllTimers();
  vi.useRealTimers();
  vi.restoreAllMocks();
});

/** 대기(setTimeout)를 건너뛰며 프라미스가 **확정될 때까지만** 돌린다.
 *  ⚠️ 확정 후에도 타이머를 계속 돌리면 미처리 거부(unhandled rejection)가 뜬다. */
async function run(promise) {
  let settled = false;
  promise.then(() => { settled = true; }, () => { settled = true; });
  for (let i = 0; i < 400 && !settled; i++) {
    await vi.advanceTimersByTimeAsync(5000);
  }
  return promise;
}

describe('폴링 복원력 (배포 환경)', () => {
  it('⚠️ 일시적 조회 실패를 넘기고 계속 기다린다 — 작업을 버리지 않는다', async () => {
    inst.post.mockResolvedValue(accepted);
    inst.get
      .mockRejectedValueOnce(new Error('Network Error'))
      .mockRejectedValueOnce(new Error('timeout of 20000ms exceeded'))
      .mockResolvedValue(done);
    await expect(run(runSimulation({}, () => {}))).resolves.toMatchObject({ status: 'success' });
  });

  it('실패가 이어지면 그때 포기한다', async () => {
    inst.post.mockResolvedValue(accepted);
    inst.get.mockRejectedValue(new Error('Network Error'));
    await expect(run(runSimulation({}, () => {}))).rejects.toThrow(/연결이 끊/);
  });

  it('⚠️ 404 는 재시도하지 않는다 — 작업이 사라진 것이라 기다려도 소용없다', async () => {
    inst.post.mockResolvedValue(accepted);
    inst.get.mockRejectedValue({ response: { status: 404 } });
    await expect(run(runSimulation({}, () => {}))).rejects.toThrow(/찾을 수 없/);
  });

  it('재시도 중에는 reconnecting 단계를 알린다', async () => {
    inst.post.mockResolvedValue(accepted);
    inst.get.mockRejectedValueOnce(new Error('Network Error')).mockResolvedValue(done);
    const stages = [];
    await run(runSimulation({}, (s) => stages.push(s)));
    expect(stages).toContain('reconnecting');
  });

  it('⚠️ 시작 직후 waking 단계를 알린다 — 콜드 스타트 동안 화면이 비면 안 된다', async () => {
    inst.post.mockResolvedValue(accepted);
    inst.get.mockResolvedValue(done);
    const stages = [];
    await run(runSimulation({}, (s) => stages.push(s)));
    expect(stages[0]).toBe('waking');
  });

  it('요청마다 다른 타임아웃을 쓴다 — 조회는 짧고 업로드·시작은 길다', async () => {
    inst.post.mockResolvedValue(accepted);
    inst.get.mockResolvedValue(done);
    await run(runSimulation({}, () => {}));
    expect(inst.post.mock.calls[0][2].timeout).toBeGreaterThanOrEqual(120000);
    expect(inst.get.mock.calls[0][1].timeout).toBeLessThanOrEqual(30000);
  });
});
