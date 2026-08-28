/**
 * 이벤트가 실제 화면에서 나가는가.
 *
 * 보내는 함수만 있고 아무도 부르지 않으면 아무것도 모은 것이 없다.
 * 그 상태를 배포하고 한 달 뒤에 알아차리는 것이 최악이다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const events = vi.hoisted(() => ({ sendEvent: vi.fn() }))
vi.mock('./events', () => events)

const share = vi.hoisted(() => ({
  drawResultCard: vi.fn(),
  saveCard: vi.fn().mockResolvedValue('downloaded'),
  shareCard: vi.fn().mockResolvedValue('shared'),
}))
vi.mock('./shareImage', () => share)

import { ConsentGate, CONSENT_KEY } from '../components/ConsentGate'
import { Result } from '../components/Result'
import type { AnalysisResult } from '../api/types'

const RESULT: AnalysisResult = {
  jobId: 'j',
  expiresAt: Math.floor(Date.now() / 1000) + 600,
  scores: {
    friendFee: -79000, intimacy: 64, breakupRisk: 8, firstContactRatio: 0.333,
    avgReplySeconds: { me: 16, peer: 5 }, contactBalance: 62,
  },
  report: { headline: 'H', summary: 'S', sections: [], advice: 'A', disclaimer: 'D' },
  meta: { messageCount: 120, imageCount: 5, sampled: false, spanSeconds: 349380 },
}

describe('이벤트 연결', () => {
  beforeEach(() => {
    events.sendEvent.mockClear()
    window.localStorage.clear()
  })

  it('동의를 마치면 보낸다', async () => {
    render(<ConsentGate><p>안</p></ConsentGate>)

    for (const box of screen.getAllByRole('checkbox')) await userEvent.click(box)
    await userEvent.click(screen.getByRole('button', { name: /시작/ }))

    await waitFor(() => expect(events.sendEvent).toHaveBeenCalledWith('consent.agreed'))
  })

  it('이미 동의한 사람에게는 다시 보내지 않는다', () => {
    window.localStorage.setItem(CONSENT_KEY, 'true')

    render(<ConsentGate><p>안</p></ConsentGate>)

    expect(events.sendEvent).not.toHaveBeenCalledWith('consent.agreed')
  })

  it('결과 화면에 도달하면 보낸다', async () => {
    render(<Result result={RESULT} onRestart={vi.fn()} />)

    await waitFor(() => expect(events.sendEvent).toHaveBeenCalledWith('result.viewed'))
  })

  it('공유와 저장을 구분해서 보낸다', async () => {
    render(<Result result={RESULT} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /친구에게 공유/ }))
    await waitFor(() => expect(events.sendEvent).toHaveBeenCalledWith('result.shared'))

    await userEvent.click(screen.getByRole('button', { name: '결과 이미지 저장' }))
    await waitFor(() => expect(events.sendEvent).toHaveBeenCalledWith('result.saved'))
  })
})

describe('진입과 업로드', () => {
  beforeEach(() => {
    events.sendEvent.mockClear()
    window.localStorage.clear()
  })

  it('앱이 뜨면 진입을 보낸다', async () => {
    // 동의 화면에서 떠난 사람도 세어야 이탈 지점을 안다
    const { default: App } = await import('../App')
    vi.doMock('../hooks/useAnalysis', () => ({
      useAnalysis: () => ({
        phase: 'idle', stage: null, result: null, error: null,
        start: vi.fn(), reset: vi.fn(),
      }),
    }))

    render(<App />)

    await waitFor(() => expect(events.sendEvent).toHaveBeenCalledWith('page.view'))
  })

  it('이미지를 고르면 보낸다', async () => {
    const { Uploader } = await import('../components/Uploader')
    render(<Uploader onStart={vi.fn()} busy={false} />)
    const input = document.querySelector('input[type="file"]') as HTMLInputElement

    const { fireEvent } = await import('@testing-library/react')
    fireEvent.change(input, {
      target: { files: [new File([new Uint8Array(64)], 'a.png', { type: 'image/png' })] },
    })

    await waitFor(() => expect(events.sendEvent).toHaveBeenCalledWith('upload.selected'))
  })
})
