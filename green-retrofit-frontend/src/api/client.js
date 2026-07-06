// api/client.js - API 통신 레이어

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60초 (파일 업로드/파싱용)
});

export const uploadGbxml = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post('/api/upload-gbxml', formData);
  return response.data;
};

export const runSimulation = async (payload, onStage) => {
  // 1. 시뮬레이션 작업 시작 요청 (비동기)
  let startResponse;
  try {
    startResponse = await apiClient.post('/api/simulate', payload);
  } catch (e) {
    // 429(혼잡) 등 백엔드가 알려준 원인을 그대로 전달
    throw new Error(e?.response?.data?.detail || e.message);
  }

  if (startResponse.data.status !== 'accepted') {
    throw new Error('시뮬레이션 시작에 실패했습니다.');
  }

  const taskId = startResponse.data.task_id;

  // 2. 5초 간격으로 상태 폴링 (최대 30분 — 전/후 2회 실행 + 대기열 고려)
  const maxRetries = 360; // 360 * 5초 = 30분
  let retries = 0;

  while (retries < maxRetries) {
    await new Promise(resolve => setTimeout(resolve, 5000));

    const statusResponse = await apiClient.get(`/api/simulate/${taskId}`);
    const statusData = statusResponse.data;

    if (statusData.status === 'success') {
      return statusData;
    } else if (statusData.status === 'failed') {
      throw new Error(statusData.error || '시뮬레이션 중 오류가 발생했습니다.');
    }

    // 진행 단계(대기열/개선 전/개선 후)를 로딩 화면에 전달
    if (onStage) onStage(statusData.status === 'queued' ? 'queued' : statusData.stage || null);

    // 'running' 상태면 계속 대기
    retries++;
  }

  throw new Error('시뮬레이션 시간이 초과되었습니다. (30분 이상 소요)');
};

export default apiClient;
