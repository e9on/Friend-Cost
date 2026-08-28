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
import type { AnalysisResult } from '../api/types'

const share = vi.hoisted(() => ({
  drawResultCard: vi.fn(),
  saveCard: vi.fn(),
  shareCard: vi.fn(),
}))

vi.mock('../lib/shareImage', () => share)

function result(overrides: Partial<AnalysisResult> = {}): AnalysisResult {
  return {
    jobId: 'job-1',
    scores: {
      friendFee: 63000,
      intimacy: 64,
      breakupRisk: 38,
      firstContactRatio: 0.63,
      avgReplySeconds: { me: 420, peer: 1860 },
      contactBalance: 74,
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

    expect(screen.getByText('63,000원')).toBeInTheDocument()
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

describe('표본이 적을 때의 안내', () => {
  it('메시지가 적으면 알려준다', () => {
    const payload = result()
    payload.meta.messageCount = 20

    render(<Result result={payload} onRestart={vi.fn()} />)

    expect(screen.getByText(/분석한 대화가 적어/)).toBeInTheDocument()
  })

  it('충분하면 붙이지 않는다', () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.queryByText(/분석한 대화가 적어/)).not.toBeInTheDocument()
  })

  it('신뢰도 등급은 화면에 없다', () => {
    // 재미로 읽는 결과에 정확도 등급을 붙이면 사용자는 그것을
    // 자기 관계에 대한 평가로 읽는다
    const { container } = render(<Result result={result()} onRestart={vi.fn()} />)

    expect(container.textContent).not.toContain('신뢰도')
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

describe('친구에게 공유', () => {
  beforeEach(() => {
    share.shareCard.mockReset().mockResolvedValue('shared')
  })

  it('공유 버튼을 누르면 이미지와 문구와 링크를 넘긴다', async () => {
    render(<Result result={result()} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /친구에게 공유/ }))

    await waitFor(() => expect(share.shareCard).toHaveBeenCalledOnce())
    const [, text, url] = share.shareCard.mock.calls[0]
    expect(text).toContain('63,000원')
    expect(url).toBe(window.location.origin)
  })

  it('링크는 결과가 아니라 서비스 첫 화면을 가리킨다', async () => {
    // 결과 링크를 뿌리면 5분 TTL 과 열람 권한 문제가 따라온다.
    // 친구에게 필요한 것은 "너도 해봐"이지 내 결과 열람이 아니다
    render(<Result result={result()} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /친구에게 공유/ }))

    await waitFor(() => expect(share.shareCard).toHaveBeenCalledOnce())
    expect(share.shareCard.mock.calls[0][2]).not.toContain('job-1')
  })

  it('공유를 못 써서 링크만 복사됐으면 그렇게 알린다', async () => {
    share.shareCard.mockResolvedValue('copied')
    render(<Result result={result()} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /친구에게 공유/ }))

    await waitFor(() => expect(screen.getByText(/링크를 복사/)).toBeInTheDocument())
  })

  it('공유에 실패하면 대안을 안내한다', async () => {
    share.shareCard.mockResolvedValue('failed')
    render(<Result result={result()} onRestart={vi.fn()} />)

    await userEvent.click(screen.getByRole('button', { name: /친구에게 공유/ }))

    await waitFor(() =>
      expect(screen.getByText(/화면을 캡처해 주세요/)).toBeInTheDocument(),
    )
  })
})

describe('지표 색', () => {
  function toneOf(container: HTMLElement, label: string): string {
    const card = Array.from(container.querySelectorAll('.metric')).find((el) =>
      el.querySelector('.metric-label')?.textContent === label,
    )
    return card?.className ?? ''
  }

  it('손절 위험도는 낮을수록 좋은 쪽으로 칠한다', () => {
    // 8점은 잘 나온 것이다. 방향을 고정하면 뜻이 정반대가 된다
    const { container } = render(
      <Result result={result({ scores: { breakupRisk: 8 } as never })} onRestart={vi.fn()} />,
    )

    expect(toneOf(container, '손절 위험도')).toContain('tone-good')
  })

  it('손절 위험도가 높으면 주의로 칠한다', () => {
    const { container } = render(
      <Result result={result({ scores: { breakupRisk: 90 } as never })} onRestart={vi.fn()} />,
    )

    expect(toneOf(container, '손절 위험도')).toContain('tone-risk')
  })

  it('친밀도는 높을수록 좋은 쪽으로 칠한다', () => {
    const { container } = render(
      <Result result={result({ scores: { intimacy: 90 } as never })} onRestart={vi.fn()} />,
    )

    expect(toneOf(container, '친밀도')).toContain('tone-good')
  })

  it('답장 속도에는 색을 주지 않는다', () => {
    // 빨리 답한다고 좋은 관계라는 근거가 없다
    const { container } = render(<Result result={result()} onRestart={vi.fn()} />)

    expect(toneOf(container, '내 답장')).toContain('tone-none')
    expect(toneOf(container, '상대 답장')).toContain('tone-none')
  })

  it('색을 빼도 숫자와 라벨이 그대로 남는다', () => {
    // 색을 구분하지 못하는 사용자에게 색은 아무 정보도 아니다
    render(<Result result={result()} onRestart={vi.fn()} />)

    expect(screen.getByText('손절 위험도')).toBeInTheDocument()
    expect(screen.getByText('38')).toBeInTheDocument()
  })
})
