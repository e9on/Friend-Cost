import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * 개발 중에는 백엔드를 프록시로 붙인다.
 * 배포는 정적 호스팅 + 별도 백엔드이므로 VITE_API_BASE 로 절대 주소를 준다.
 */
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
