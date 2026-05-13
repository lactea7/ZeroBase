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

export const runSimulation = async (payload) => {
  // 💡 시뮬레이션은 대형 건물 기준 최대 10분까지 소요 가능
  const response = await apiClient.post('/api/simulate', payload, {
    timeout: 600000, // 10분
  });
  return response.data;
};

export default apiClient;
