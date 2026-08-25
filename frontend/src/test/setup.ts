import '@testing-library/jest-dom/vitest'
import { afterEach, vi } from 'vitest'
import { cleanup } from '@testing-library/react'

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

// jsdom에는 아래 API가 없다. 실제 브라우저에서는 모두 존재한다.
if (!URL.createObjectURL) {
  let counter = 0
  URL.createObjectURL = vi.fn(() => `blob:test/${counter++}`) as never
  URL.revokeObjectURL = vi.fn() as never
}

// 캔버스 구현도 없다. 결과 카드 그리기는 별도로 검증한다
HTMLCanvasElement.prototype.getContext = vi.fn(() => null) as never
HTMLCanvasElement.prototype.toBlob = vi.fn((callback: BlobCallback) => {
  callback(new Blob(['png'], { type: 'image/png' }))
}) as never
