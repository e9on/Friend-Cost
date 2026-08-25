/**
 * 결과 카드 그리기와 저장.
 *
 * 서버에 다운로드 엔드포인트를 두지 않기로 했으므로(기준 명세 11장)
 * 여기가 깨지면 사용자는 결과를 가져갈 방법이 없다.
 *
 * jsdom에는 캔버스 구현이 없다. 실제 픽셀 대신 **어떤 명령이 어떤 순서로
 * 나갔는지**를 본다. 폰트나 색을 검사하지 않고, 값이 실제로 그려지는지만 본다.
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { drawResultCard, saveCard } from './shareImage'
import type { AnalysisResult } from '../api/types'

interface FakeContext {
  texts: string[]
  fillText: ReturnType<typeof vi.fn>
  measureText: ReturnType<typeof vi.fn>
  fillRect: ReturnType<typeof vi.fn>
  beginPath: ReturnType<typeof vi.fn>
  moveTo: ReturnType<typeof vi.fn>
  arcTo: ReturnType<typeof vi.fn>
  closePath: ReturnType<typeof vi.fn>
  fill: ReturnType<typeof vi.fn>
  font: string
  fillStyle: string
}

function fakeContext(): FakeContext {
  const texts: string[] = []
  return {
    texts,
    fillText: vi.fn((text: string) => texts.push(text)),
    measureText: vi.fn((text: string) => ({ width: text.length * 20 })),
    fillRect: vi.fn(),
    beginPath: vi.fn(),
    moveTo: vi.fn(),
    arcTo: vi.fn(),
    closePath: vi.fn(),
    fill: vi.fn(),
    font: '',
    fillStyle: '',
  }
}

function canvasWith(context: FakeContext | null): HTMLCanvasElement {
  const canvas = document.createElement('canvas')
  canvas.getContext = vi.fn(() => context) as never
  return canvas
}

const RESULT: AnalysisResult = {
  jobId: 'job-1',
  scores: {
    friendFee: 45000,
    intimacy: 64,
    breakupRisk: 38,
    firstContactRatio: 0.63,
    avgReplySeconds: { me: 420, peer: 1860 },
    contactBalance: 74,
    confidence: 'high',
  },
  report: {
    headline: '서로 챙기지만 균형이 조금 기운 사이',
    summary: '연락은 이어지지만 시작하는 쪽이 한쪽으로 쏠려 있다.',
    sections: [
      { title: '연락의 흐름', body: '본문' },
      { title: '지켜볼 지점', body: '본문' },
    ],
    advice: '다음 약속은 날짜부터 정해 보자.',
    disclaimer: '이 결과는 재미를 위한 추정입니다.',
  },
  meta: { messageCount: 184, imageCount: 5, sampled: false, spanSeconds: 1209600 },
  expiresAt: 2000,
}

describe('drawResultCard', () => {
  it('친구비를 카드에 새긴다', () => {
    const context = fakeContext()

    drawResultCard(canvasWith(context), RESULT)

    expect(context.texts).toContain('45,000원')
  })

  it('여섯 지표를 모두 새긴다', () => {
    const context = fakeContext()

    drawResultCard(canvasWith(context), RESULT)

    for (const label of [
      '친밀도',
      '손절 위험도',
      '연락 균형도',
      '먼저 연락',
      '내 답장',
      '상대 답장',
    ]) {
      expect(context.texts).toContain(label)
    }
  })

  it('고지 문구를 빠뜨리지 않는다', () => {
    const context = fakeContext()

    drawResultCard(canvasWith(context), RESULT)

    expect(context.texts).toContain(RESULT.report.disclaimer)
  })

  it('긴 문장은 줄바꿈해서 넣는다', () => {
    const context = fakeContext()

    drawResultCard(canvasWith(context), RESULT)

    // 요약은 한 줄에 다 들어가지 않으므로 여러 조각으로 나뉜다
    const joined = context.texts.join(' ')
    expect(joined).toContain('연락은')
    expect(context.fillText.mock.calls.length).toBeGreaterThan(10)
  })

  it('캔버스 크기를 내용에 맞춰 잡는다', () => {
    const canvas = canvasWith(fakeContext())

    drawResultCard(canvas, RESULT)

    expect(canvas.width).toBe(1080)
    expect(canvas.height).toBeGreaterThan(1000)
  })

  it('2D 컨텍스트가 없어도 터지지 않는다', () => {
    // 아주 오래된 브라우저나 캔버스가 막힌 환경이 있다
    expect(() => drawResultCard(canvasWith(null), RESULT)).not.toThrow()
  })
})

describe('saveCard', () => {
  let canvas: HTMLCanvasElement

  beforeEach(() => {
    canvas = document.createElement('canvas')
    canvas.toBlob = vi.fn((callback: BlobCallback) => {
      callback(new Blob(['png'], { type: 'image/png' }))
    }) as never
    vi.stubGlobal('URL', {
      createObjectURL: vi.fn(() => 'blob:test'),
      revokeObjectURL: vi.fn(),
    })
  })

  it('공유가 가능하면 공유 시트를 먼저 연다', async () => {
    // 모바일에서는 <a download> 가 무시되는 경우가 있다
    const share = vi.fn().mockResolvedValue(undefined)
    vi.stubGlobal('navigator', { canShare: vi.fn(() => true), share })

    const outcome = await saveCard(canvas)

    expect(outcome).toBe('shared')
    expect(share).toHaveBeenCalledOnce()
  })

  it('공유를 취소하면 저장으로 넘어간다', async () => {
    vi.stubGlobal('navigator', {
      canShare: vi.fn(() => true),
      share: vi.fn().mockRejectedValue(new Error('cancelled')),
    })

    const outcome = await saveCard(canvas)

    expect(outcome).toBe('downloaded')
  })

  it('공유를 못 쓰면 바로 내려받는다', async () => {
    vi.stubGlobal('navigator', {})

    const outcome = await saveCard(canvas)

    expect(outcome).toBe('downloaded')
    expect(URL.revokeObjectURL).toHaveBeenCalled()
  })

  it('이미지를 만들지 못하면 실패를 알린다', async () => {
    canvas.toBlob = vi.fn((callback: BlobCallback) => callback(null)) as never
    vi.stubGlobal('navigator', {})

    expect(await saveCard(canvas)).toBe('failed')
  })
})
