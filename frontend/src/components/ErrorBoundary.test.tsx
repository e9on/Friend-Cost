/**
 * 에러 바운더리.
 *
 * 이게 없으면 컴포넌트 하나가 던졌을 때 화면이 하얘진다.
 */

import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ErrorBoundary } from './ErrorBoundary'

function Exploding(): never {
  throw new Error('대화 내용이 섞인 오류 메시지 hunter2')
}

beforeEach(() => {
  // React가 잡힌 오류를 콘솔에 다시 뱉는다. 테스트 출력을 어지럽히지 않는다
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

describe('ErrorBoundary', () => {
  it('평소에는 자식을 그대로 보여준다', () => {
    render(
      <ErrorBoundary>
        <p>정상 화면</p>
      </ErrorBoundary>,
    )

    expect(screen.getByText('정상 화면')).toBeInTheDocument()
  })

  it('자식이 던지면 안내를 보여준다', () => {
    render(
      <ErrorBoundary>
        <Exploding />
      </ErrorBoundary>,
    )

    expect(screen.getByText('화면을 그리지 못했어요')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '새로고침' })).toBeInTheDocument()
  })

  it('오류 원문을 화면에 노출하지 않는다', () => {
    // 오류 메시지에 대화 내용이 섞여 나올 수 있다
    const { container } = render(
      <ErrorBoundary>
        <Exploding />
      </ErrorBoundary>,
    )

    expect(container.textContent).not.toContain('hunter2')
  })

  it('임시 데이터가 어떻게 되는지 알려준다', () => {
    render(
      <ErrorBoundary>
        <Exploding />
      </ErrorBoundary>,
    )

    expect(screen.getByText(/서버에서 이미 지워졌거나/)).toBeInTheDocument()
  })
})
