import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

import { legalAlias } from './legal.alias.ts'

export default defineConfig({
  plugins: [react()],
  // 별칭 정의는 `legal.alias.ts` 한 곳뿐이다. 두 config 가 함께 쓴다
  resolve: { alias: legalAlias },
  // 법률 문서가 frontend/ 밖에 있다. 읽기를 열어주지 않으면 Denied ID 가 난다
  server: { fs: { allow: ['..'] } },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    css: false,
  },
})
