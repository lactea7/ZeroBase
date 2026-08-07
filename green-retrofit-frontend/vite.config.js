import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  // ⚠️ 시험 파일의 JSX 도 자동 런타임으로 변환한다. 없으면
  // 'React is not defined' 로 시험만 깨진다(앱 빌드는 멀쩡하다).
  esbuild: { jsx: 'automatic' },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.js'],
    // 3D 뷰어(three/@react-three)는 jsdom 에서 WebGL 이 없어 못 돈다.
    // 렌더 스모크는 그것을 mock 한 뒤에만 의미가 있다 — setup.js 참조.
    css: false,
  },
})
