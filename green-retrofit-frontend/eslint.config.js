import js from '@eslint/js'
import globals from 'globals'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import { defineConfig, globalIgnores } from 'eslint/config'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{js,jsx}'],
    extends: [
      js.configs.recommended,
      reactHooks.configs.flat.recommended,
      reactRefresh.configs.vite,
    ],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
      parserOptions: {
        ecmaVersion: 'latest',
        ecmaFeatures: { jsx: true },
        sourceType: 'module',
      },
    },
    plugins: { react },
    settings: { react: { version: 'detect' } },
    rules: {
      'no-unused-vars': ['error', { varsIgnorePattern: '^[A-Z_]' }],
      // JSX 안에서만 쓰이는 식별자(<motion.div> 의 motion 등)를 '사용됨'으로 인식시킨다.
      // 이 규칙이 없으면 core no-unused-vars 가 실제 사용 중인 import 를 오탐한다.
      'react/jsx-uses-vars': 'error',
      'react/jsx-uses-react': 'error',
      // ⚠️ **core `no-undef` 는 JSX 요소 이름을 검사하지 않는다.**
      // `<AnimatePresence>` 의 import 를 빠뜨린 채로 lint·build·시험 401건이 전부
      // 통과했고, 결과 화면이 열리는 순간 ReferenceError 로 **흰 화면**이 됐다.
      // 번들러에게는 미정의 전역일 뿐이라 컴파일도 막지 못한다.
      // App.jsx 를 쪼갤 때 JSX 만 옮기고 import 를 두고 오면 반복되는 유형이라 규칙으로 막는다.
      'react/jsx-no-undef': 'error',
    },
  },
])
