/**
 * 결과 화면.
 *
 * 서버가 준 값을 사용자에게 전하는 마지막 지점이다. 여기서 뭉개지면
 * 백엔드가 아무리 정확해도 소용이 없다.
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { Result } from './Result'
import type { AnalysisResult, Confidence } from '../api/types'

const share = vi.hoisted(() => ({
  drawResultCard: vi.fn(),
  saveCard: vi.fn(),
}))

vi.mock('../lib/shareImage', () => share)

function result(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    jobId: 'job-1',
    scores: {
      friendFee: 45000,
      intimacy: 64,
      breakupRisk: 38,
      firstContactRatio: 0.63,
      avgReplySeconds: { me: 420, peer: 1860 },
      contactBalance: 74,
      confidence: 'high',
      ...overrides.scores,
    },
    report: {
      headline: '서로 챙기지만 균형이 조금 기운 사이',
      summary: '연락은 이어지지만 시작하는 쪽이 한쪽으로 쏠려 있다.',
      sections: [
        { title: '연락의 흐름', body: '먼저 말을 거는 쪽이 정해져 있다.' },
        { title: '지켜볼 지점', body: '약속이 미뤄지는 일이 반복된다.' },
      ],
      advice: '다음 약속은 날짜부터 정해 보자.',
      disclaimer: '이 결과는 재미를 위한 추정입니다.',
      ...overrides.report,
    },
    meta: {
      messageCount: 184,
      imageCount: 5,
      sampled: false,
      spanSeconds: 1209600,
      ...overrides.meta,
    },
    expiresAt: Math.floor(Date.now() / 1000) + 1200,
    ...('expiresAt' in overrides ? { expiresAt: overrides.expiresAt! } : {}),
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  share.saveCard.mockResolvedValue('downloaded')
})

describe('결과 표시', () => {
  it('친구비를 원 단위로 크게 보여준다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.getByText('45,000원')).toBeInTheDocument()
  })

  it('리포트 본문을 모두 보여준다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.getByText('서로 챙기지만 균형이 조금 기운 사이')).toBeInTheDocument()
    expect(screen.getByText('연락의 흐름')).toBeInTheDocument()
    expect(screen.getByText('지켜볼 지점')).toBeInTheDocument()
    expect(screen.getByText('다음 약속은 날짜부터 정해 보자.')).toBeInTheDocument()
  })

  it('여섯 지표를 모두 보여준다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.getByText('친밀도')).toBeInTheDocument()
    expect(screen.getByText('손절 위험도')).toBeInTheDocument()
    expect(screen.getByText('연락 균형도')).toBeInTheDocument()
    expect(screen.getByText('63%')).toBeInTheDocument()
    expect(screen.getByText('7분')).toBeInTheDocument()
    expect(screen.getByText('31분')).toBeInTheDocument()
  })

  it('표본이 없는 답장 속도를 0으로 뭉개지 않는다', () => {
    const payload = result()
    payload.scores.avgReplySeconds = { me: null, peer: null }

    render(<Result result={payload} onRestart={vi.fn()} />)

    expect(screen.getAllByText('알 수 없음')).toHaveLength(2)
  })

  it('고지 문구를 반드시 보여준다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.getByText(/재미를 위한 추정/)).toBeInTheDocument()
  })
})

describe('신뢰도 안내', () => {
  it.each([
    ['medium' as Confidence, /대화량이 넉넉하지 않아/],
    ['low' as Confidence, /분석할 대화가 적어/],
  ])('신뢰도가 %s면 경고를 덧붙인다', (confidence, pattern) => {
    const payload = result()
    payload.scores.confidence = confidence

    render(<Result result={payload} onRestart={vi.fn()} />)

    expect(screen.getByText(pattern)).toBeInTheDocument()
  })

  it('신뢰도가 높으면 경고를 붙이지 않는다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.queryByText(/대화량이 넉넉하지 않아/)).not.toBeInTheDocument()
  })

  it('일부만 분석했으면 그 사실을 알린다', () => {
    const payload = result()
    payload.meta.sampled = true

    render(<Result result={payload} onRestart={vi.fn()} />)

    expect(screen.getByText(/일부만 골라 분석했어요/)).toBeInTheDocument()
  })
})

describe('결과 이미지 저장', () => {
  it('화면에 그릴 때 카드도 함께 그린다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(share.drawResultCard).toHaveBeenCalledOnce()
  })

  it('저장 버튼을 누르면 카드를 내보낸다', async () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '결과 이미지 저장' }))

    await waitFor(() => expect(share.saveCard).toHaveBeenCalledOnce())
  })

  it('저장에 실패하면 대안을 안내한다', async () => {
    share.saveCard.mockResolvedValue('failed')
    render(<Result result={result()} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: '결과 이미지 저장' }))

    await waitFor(() =>
      expect(screen.getByText(/화면을 캡처해 주세요/)).toBeInTheDocument(),
    )
  })
})

describe('만료 안내', () => {
  it('남은 시간을 보여준다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.getByText(/뒤 서버에서 자동 삭제됩니다/)).toBeInTheDocument()
  })

  it('만료되면 저장한 이미지는 남는다고 알려준다', () => {
    const payload = result({ expiresAt: Math.floor(Date.now() / 1000) - 10 })

    render(<Result result={payload} onRestart={vi.fn()} />)

    expect(screen.getByText(/저장한 이미지는 그대로 남아 있습니다/)).toBeInTheDocument()
  })
})

describe('다시 하기', () => {
  it('버튼을 누르면 초기화를 요청한다', async () => {
    const onRestart = vi.fn()
    render(<Result result={result()} onRestart={onRestart} />)

    await userEvent.click(screen.getByRole('button', { name: '다른 대화 분석하기' }))

    expect(onRestart).toHaveBeenCalledOnce()
  })
})
