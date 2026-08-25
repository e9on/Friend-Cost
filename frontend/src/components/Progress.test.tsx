/**
 * 진행 화면과 실패 화면.
 *
 * 진행 화면은 "멈춘 것처럼 보이지 않게" 하는 것이 목적이고,
 * 실패 화면은 사용자가 다음에 무엇을 할지 알려주는 것이 목적이다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Failure } from './Failure'
import { Progress } from './Progress'
import { STAGE_LABELS } from '../api/types'

describe('진행 화면', () => {
  it('업로드 중임을 알려준다', () => {
    render(<Progress stage={null} phase="uploading" />)

    expect(screen.getByText('캡처를 올리는 중')).toBeInTheDocument()
  })

  it('서버가 준 단계를 그대로 보여준다', () => {
    render(<Progress stage="analyzing" phase="running" />)

    expect(
      screen.getByRole('heading', { name: STAGE_LABELS.analyzing }),
    ).toBeInTheDocument()
  })

  it('단계가 진행되면 진행률이 오른다', () => {
    const { rerender } = render(<Progress stage="ocr" phase="running" />)
    const early = Number(
      screen.getByRole('progressbar').getAttribute('aria-valuenow'),
    )

    rerender(<Progress stage="reporting" phase="running" />)
    const late = Number(
      screen.getByRole('progressbar').getAttribute('aria-valuenow'),
    )

    expect(late).toBeGreaterThan(early)
  })

  it('단계를 모르는 동안에도 멈춰 보이지 않는다', () => {
    render(<Progress stage={null} phase="running" />)

    const percent = Number(
      screen.getByRole('progressbar').getAttribute('aria-valuenow'),
    )
    expect(percent).toBeGreaterThan(0)
  })

  it('다섯 단계를 모두 나열한다', () => {
    render(<Progress stage="scoring" phase="running" />)

    for (const label of Object.values(STAGE_LABELS)) {
      expect(screen.getAllByText(label).length).toBeGreaterThan(0)
    }
  })

  it('지난 단계에 완료 표시를 한다', () => {
    const { container } = render(<Progress stage="reporting" phase="running" />)

    expect(container.querySelectorAll('.step-done')).toHaveLength(4)
  })
})

describe('실패 화면', () => {
  it('대화가 짧으면 다시 시도를 권하지 않는다', async () => {
    // 같은 캡처로 재시도하면 같은 결과만 반복된다
    render(
      <Failure
        error={{ code: 'TOO_FEW_MESSAGES', message: '짧음', retryable: false }}
        onRestart={vi.fn()}
      />,
    )

    expect(screen.getByText('대화가 너무 짧아요')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '처음으로' })).toBeInTheDocument()
  })

  it('일시적인 오류에는 다시 시도를 권한다', () => {
    render(
      <Failure
        error={{ code: 'RATE_LIMITED', message: '잦음', retryable: true }}
        onRestart={vi.fn()}
      />,
    )

    expect(screen.getByRole('button', { name: '다시 시도하기' })).toBeInTheDocument()
  })

  it.each([
    ['GROUP_CHAT_DETECTED', '단체방은 분석할 수 없어요'],
    ['SPEAKER_DETECTION_FAILED', '누가 보낸 말인지 구분하지 못했어요'],
    ['JOB_EXPIRED', '결과가 만료되었어요'],
    ['DAILY_LIMIT_EXCEEDED', '오늘은 여기까지예요'],
    ['NETWORK_ERROR', '서버에 연결하지 못했어요'],
  ])('%s 에 맞는 안내를 고른다', (code, title) => {
    render(
      <Failure error={{ code, message: '', retryable: false }} onRestart={vi.fn()} />,
    )

    expect(screen.getByText(title)).toBeInTheDocument()
  })

  it('모르는 코드에도 화면이 깨지지 않는다', () => {
    render(
      <Failure
        error={{ code: '처음보는코드', message: '', retryable: true }}
        onRestart={vi.fn()}
      />,
    )

    expect(screen.getByText('분석에 실패했어요')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '다시 시도하기' })).toBeInTheDocument()
  })

  it('문의에 쓸 수 있게 오류 코드를 남긴다', () => {
    render(
      <Failure
        error={{ code: 'OCR_FAILED', message: '', retryable: true }}
        onRestart={vi.fn()}
      />,
    )

    expect(screen.getByText(/OCR_FAILED/)).toBeInTheDocument()
  })

  it('버튼을 누르면 초기화를 요청한다', async () => {
    const onRestart = vi.fn()
    render(
      <Failure
        error={{ code: 'OCR_FAILED', message: '', retryable: true }}
        onRestart={onRestart}
      />,
    )

    await userEvent.click(screen.getByRole('button'))

    expect(onRestart).toHaveBeenCalledOnce()
  })
})
