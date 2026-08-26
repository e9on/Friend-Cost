import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

/**
 * 개발 중에는 백엔드를 프록시로 붙인다.
 * 배포는 정적 호스팅 + 별도 백엔드이므로 VITE_API_BASE 로 절대 주소를 준다.
 *
 * 포트를 박아두면 8000이 이미 쓰이고 있을 때 손댈 곳이 없다. 실제로 예전에
 * 띄워둔 stub 설정 백엔드가 그 자리를 잡고 있어서, 프론트가 조용히 가짜
 * 결과를 받는 상황이 나왔다. 오류가 나지 않으므로 눈치채기 어렵다.
 */
const BACKEND_PORT = process.env.BACKEND_PORT ?? '8000'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/v1': {
        target: `http://127.0.0.1:${BACKEND_PORT}`,
        changeOrigin: true,
      },
    },
  },
})
