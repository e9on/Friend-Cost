/**
 * 실패 화면.
 *
 * 오류마다 무엇을 해야 하는지 다르다. "알 수 없는 오류"만 보여주면
 * 사용자는 고칠 방법을 알 수 없다.
 */

import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { Failure } from './Failure'
import type { ErrorBody } from '../api/types'

function error(code: string, retryable = false): ErrorBody {
  return { code, message: '', retryable }
}

describe('서비스 쪽 사정으로 막힌 경우', () => {
  it('전체 분량이 찼을 때 내 잘못이라고 하지 않는다', () => {
    // 전역 상한에 걸린 사용자는 자기 몫을 쓴 적이 없다.
    // "네가 다 썼다"고 하면 사실과 다른 말이 된다
    render(<Failure error={error('SERVICE_DAILY_LIMIT')} onRestart={vi.fn()} />)

    expect(screen.getByText(/전체 분량/)).toBeInTheDocument()
    expect(screen.queryByText(/모두 썼어요/)).not.toBeInTheDocument()
  })

  it('운영이 끝났으면 다시 시도하라고 하지 않는다', () => {
    // 끝난 서비스에 재시도를 권하면 헛되이 붙잡는 일이다
    render(<Failure error={error('SERVICE_ENDED')} onRestart={vi.fn()} />)

    expect(screen.getByText(/종료/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '다시 시도하기' })).not.toBeInTheDocument()
  })

  it('개인 할당량과 문구가 다르다', () => {
    render(<Failure error={error('DAILY_LIMIT_EXCEEDED')} onRestart={vi.fn()} />)
    const mine = screen.getByRole('heading').textContent

    render(<Failure error={error('SERVICE_DAILY_LIMIT')} onRestart={vi.fn()} />)
    const ours = screen.getAllByRole('heading').at(-1)?.textContent

    expect(mine).not.toBe(ours)
  })
})

describe('모르는 오류', () => {
  it('재시도 가능 여부를 서버 응답에서 가져온다', () => {
    render(<Failure error={error('SOMETHING_NEW', true)} onRestart={vi.fn()} />)

    expect(screen.getByRole('button', { name: '다시 시도하기' })).toBeInTheDocument()
  })
})
