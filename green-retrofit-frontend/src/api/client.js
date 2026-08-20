// api/client.js - API 통신 레이어

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// ⚠️ 요청마다 성격이 다르므로 **하나의 타임아웃을 공유하지 않는다.**
// 예전엔 전부 60초였는데, 배포(Render 무료)에서 실측한 콜드 스타트가 **32.7초**다.
// 첫 업로드가 콜드 스타트와 겹치면 파싱 시간까지 60초 안에 끝나야 해서 아슬아슬했다.
const TIMEOUT = {
  // 업로드·파싱: 콜드 스타트 + 대용량 파일 파싱(회의실 1,230면)까지 감당해야 한다.
  upload: 180000,
  // 시뮬레이션 시작: 작업 ID 만 받고 즉시 반환된다. 길 이유가 없지만 콜드 스타트는 탄다.
  start: 120000,
  // 상태 조회: 짧아야 한다. 한 번 늦어도 다음 주기에 다시 물으면 된다.
  poll: 20000,
};

const apiClient = axios.create({ baseURL: API_BASE_URL });

export const uploadGbxml = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post('/api/upload-gbxml', formData, {
    timeout: TIMEOUT.upload,
  });
  return response.data;
};

// 폴링 간격(ms)과 최대 대기 시간. 30분은 전/후 2회 실행 + 대안 재시뮬레이션 + 대기열 몫이다.
const POLL_INTERVAL_MS = 5000;
const MAX_WAIT_MS = 30 * 60 * 1000;

// ⚠️ 상태 조회가 **연속으로** 이만큼 실패하면 그때 포기한다.
// 예전에는 한 번만 실패해도 예외가 루프 밖으로 나가 **진행 중인 작업을 통째로
// 버렸다.** 서버는 계속 돌고 있는데 사용자 화면만 실패로 끝나는 것이라,
// 수 분짜리 계산이 네트워크 한 번 끊긴 것으로 사라졌다.
// 서버가 잠들었다 깨는 경우(콜드 스타트)도 여기에 걸린다.
const MAX_CONSECUTIVE_POLL_FAILURES = 6;   // 6 × 5초 = 30초

export const runSimulation = async (payload, onStage) => {
  // 1. 시뮬레이션 작업 시작 요청 (비동기)
  //    ⚠️ 서버가 잠들어 있으면 여기서 30초 넘게 걸린다. 그동안 화면이 비면
  //    사용자는 멈춘 줄 안다 — 단계 문구를 먼저 띄운다.
  if (onStage) onStage('waking');

  let startResponse;
  try {
    startResponse = await apiClient.post('/api/simulate', payload, {
      timeout: TIMEOUT.start,
    });
  } catch (e) {
    // 429(혼잡)·422(모델 오류) 등 백엔드가 알려준 원인을 그대로 전달
    throw new Error(e?.response?.data?.detail || e.message);
  }

  if (startResponse.data.status !== 'accepted') {
    throw new Error('시뮬레이션 시작에 실패했습니다.');
  }

  const taskId = startResponse.data.task_id;

  // 2. 상태 폴링
  //
  // ⚠️ 종료 조건을 **시각과 횟수 둘 다** 둔다. 시각만으로 끝내면 `Date.now()` 가
  // 진행하지 않는 환경(가짜 타이머, 즉시 해소되는 목)에서 루프가 끝나지 않고
  // 프라미스가 쌓여 **힙이 터진다** — 실제로 시험 실행기가 그렇게 죽었다.
  // 예전 구현이 횟수 기준이었던 이유가 이것이다.
  const deadline = Date.now() + MAX_WAIT_MS;
  const maxPolls = Math.ceil(MAX_WAIT_MS / POLL_INTERVAL_MS);
  let consecutiveFailures = 0;
  let polls = 0;

  while (polls < maxPolls && Date.now() < deadline) {
    polls += 1;
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));

    let statusData;
    try {
      const statusResponse = await apiClient.get(`/api/simulate/${taskId}`, {
        timeout: TIMEOUT.poll,
      });
      statusData = statusResponse.data;
      consecutiveFailures = 0;
    } catch (e) {
      // ⚠️ 404 는 재시도해도 소용없다 — 작업이 정리됐거나 서버가 재시작된 것이다.
      if (e?.response?.status === 404) {
        throw new Error('시뮬레이션 작업을 찾을 수 없습니다. 서버가 재시작되었을 수 있습니다.');
      }
      consecutiveFailures += 1;
      if (consecutiveFailures >= MAX_CONSECUTIVE_POLL_FAILURES) {
        throw new Error('서버와 연결이 끊겼습니다. 잠시 후 다시 시도해주세요.');
      }
      if (onStage) onStage('reconnecting');
      continue;   // 진행 중인 작업을 버리지 않는다
    }

    if (statusData.status === 'success') {
      return statusData;
    }
    if (statusData.status === 'failed') {
      throw new Error(statusData.error || '시뮬레이션 중 오류가 발생했습니다.');
    }

    // 진행 단계(대기열/개선 전/개선 후)를 로딩 화면에 전달
    if (onStage) onStage(statusData.status === 'queued' ? 'queued' : statusData.stage || null);
  }

  throw new Error('시뮬레이션 시간이 초과되었습니다. (30분 이상 소요)');
};

export default apiClient;
