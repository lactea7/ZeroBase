/**
 * api/client.js — 시뮬레이션 실행의 비동기 계약.
 *
 * ⚠️ 이 코드에는 시험이 하나도 없었다. 그런데 사용자가 30분을 기다리는 경로이고,
 * 여기서 상태 하나를 잘못 읽으면 **성공을 실패로, 실패를 무한 대기로** 만든다.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('axios', () => {
  const instance = { post: vi.fn(), get: vi.fn() };
  return { default: { create: () => instance }, __instance: instance };
});

const axios = await import('axios');
const http = axios.__instance;
const { runSimulation, uploadGbxml } = await import('../client.js');

/** 폴링의 5초 대기를 건너뛴다 — 실제로 기다리면 시험이 못 끝난다. */
function skipPollingDelay() {
  vi.spyOn(globalThis, 'setTimeout').mockImplementation((fn) => {
    fn();
    return 0;
  });
}

const PAYLOAD = { projectData: {}, zones: [], surfaces: [] };
const accepted = { data: { status: 'accepted', task_id: 'T1' } };

beforeEach(() => {
  vi.restoreAllMocks();
  http.post.mockReset();
  http.get.mockReset();
  skipPollingDelay();
});

// ── 정상 경로 ────────────────────────────────────────────

describe('runSimulation', () => {
  it('accepted → running → success 를 끝까지 따라간다', async () => {
    http.post.mockResolvedValue(accepted);
    http.get
      .mockResolvedValueOnce({ data: { status: 'running', stage: 'retrofit' } })
      .mockResolvedValueOnce({ data: { status: 'success', result: { summary: {} } } });

    const out = await runSimulation(PAYLOAD);
    expect(out.status).toBe('success');
    expect(http.get).toHaveBeenCalledTimes(2);
  });

  it('작업 id 로 상태를 조회한다', async () => {
    http.post.mockResolvedValue(accepted);
    http.get.mockResolvedValue({ data: { status: 'success' } });

    await runSimulation(PAYLOAD);
    expect(http.get).toHaveBeenCalledWith('/api/simulate/T1');
  });

  it('진행 단계를 화면에 전달한다', async () => {
    http.post.mockResolvedValue(accepted);
    http.get
      .mockResolvedValueOnce({ data: { status: 'queued' } })
      .mockResolvedValueOnce({ data: { status: 'running', stage: 'baseline' } })
      .mockResolvedValueOnce({ data: { status: 'success' } });

    const stages = [];
    await runSimulation(PAYLOAD, (s) => stages.push(s));
    // ⚠️ 단계가 안 오면 사용자는 30분간 아무 표시 없는 화면을 본다
    expect(stages).toEqual(['queued', 'baseline']);
  });
});

// ── 실패 경로 ────────────────────────────────────────────
// ⚠️ 여기가 핵심이다. 실패를 못 알아채면 사용자는 30분을 기다린 뒤에야 안다.

describe('runSimulation 실패 처리', () => {
  it('failed 상태를 즉시 오류로 올린다', async () => {
    http.post.mockResolvedValue(accepted);
    http.get.mockResolvedValue({
      data: { status: 'failed', error: '기상(.epw) 파일을 찾을 수 없습니다' },
    });

    await expect(runSimulation(PAYLOAD)).rejects.toThrow('기상(.epw) 파일을 찾을 수 없습니다');
  });

  it('failed 인데 사유가 없어도 빈 오류를 내지 않는다', async () => {
    http.post.mockResolvedValue(accepted);
    http.get.mockResolvedValue({ data: { status: 'failed' } });

    await expect(runSimulation(PAYLOAD)).rejects.toThrow(/오류/);
  });

  it('백엔드가 알려준 혼잡(429) 사유를 그대로 전달한다', async () => {
    http.post.mockRejectedValue({
      response: { data: { detail: '동시 실행 한도를 초과했습니다' } },
    });

    await expect(runSimulation(PAYLOAD)).rejects.toThrow('동시 실행 한도를 초과했습니다');
  });

  it('사유가 없는 네트워크 오류는 원래 메시지를 쓴다', async () => {
    http.post.mockRejectedValue(new Error('Network Error'));
    await expect(runSimulation(PAYLOAD)).rejects.toThrow('Network Error');
  });

  it('accepted 가 아니면 폴링을 시작하지 않는다', async () => {
    http.post.mockResolvedValue({ data: { status: 'rejected' } });

    await expect(runSimulation(PAYLOAD)).rejects.toThrow();
    expect(http.get).not.toHaveBeenCalled();
  });

  it('끝나지 않는 작업은 30분 뒤 시간 초과로 끝낸다', async () => {
    http.post.mockResolvedValue(accepted);
    http.get.mockResolvedValue({ data: { status: 'running' } });

    await expect(runSimulation(PAYLOAD)).rejects.toThrow(/초과/);
    // ⚠️ "유한하다"만 보면 재시도 횟수가 1 로 줄어도 통과한다. 실제 계약은
    // **5초 × 360회 = 30분** 이다. 전/후 2회 실행 + 대기열을 감당해야 하므로
    // 이 숫자가 줄면 정상 작업이 시간 초과로 죽는다.
    expect(http.get).toHaveBeenCalledTimes(360);
  });
});

// ── 업로드 ───────────────────────────────────────────────

describe('uploadGbxml', () => {
  it('파일을 multipart 로 보낸다', async () => {
    http.post.mockResolvedValue({ data: { zones: [], surfaces: [] } });
    const file = new File(['<gbXML/>'], 'a.xml', { type: 'text/xml' });

    await uploadGbxml(file);
    const [url, body] = http.post.mock.calls[0];
    expect(url).toBe('/api/upload-gbxml');
    expect(body).toBeInstanceOf(FormData);
    expect(body.get('file')).toBe(file);
  });
});
