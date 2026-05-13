// api/client.js - API 통신 레이어

import axios from 'axios';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 60000, // 60초 타임아웃 (대형 파일 파싱 대비)
});

export const uploadGbxml = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  const response = await apiClient.post('/api/upload-gbxml', formData);
  return response.data;
};

export const runSimulation = async (payload) => {
  const response = await apiClient.post('/api/simulate', payload);
  return response.data;
};

export default apiClient;
