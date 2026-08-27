/**
 * 최초 입장 동의.
 *
 * 「개인정보 보호법」제22조는 각 동의 사항을 **구분해 각각** 받으라고 한다.
 * 하나로 묶은 체크박스는 그 요건을 채우지 못한다.
 *
 * `Frontend-명세.md` 2.1
 */

import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ConsentGate, CONSENT_KEY } from './ConsentGate'

function child() {
  return <p>업로드 화면</p>
}

describe('최초 입장 동의', () => {
  beforeEach(() => {
    window.localStorage.clear()
  })

  it('처음 들어오면 동의를 먼저 받는다', () => {
    render(<ConsentGate>{child()}</ConsentGate>)

    expect(screen.queryByText('업로드 화면')).not.toBeInTheDocument()
  })

  it('네 가지를 구분해서 받는다', () => {
    // 하나로 묶으면 제22조의 "구분하여 각각" 요건을 못 채운다
    render(<ConsentGate>{child()}</ConsentGate>)

    expect(screen.getAllByRole('checkbox')).toHaveLength(4)
  })

  it('하나라도 빠지면 들어갈 수 없다', async () => {
    render(<ConsentGate>{child()}</ConsentGate>)
    const boxes = screen.getAllByRole('checkbox')

    for (const box of boxes.slice(0, 3)) await userEvent.click(box)

    expect(screen.getByRole('button', { name: /시작/ })).toBeDisabled()
  })

  it('넷 다 체크하면 들어간다', async () => {
    render(<ConsentGate>{child()}</ConsentGate>)

    for (const box of screen.getAllByRole('checkbox')) await userEvent.click(box)
    await userEvent.click(screen.getByRole('button', { name: /시작/ }))

    await waitFor(() => expect(screen.getByText('업로드 화면')).toBeInTheDocument())
  })

  it('모두 동의 버튼은 편의일 뿐 개별 체크박스를 없애지 않는다', async () => {
    render(<ConsentGate>{child()}</ConsentGate>)

    await userEvent.click(screen.getByRole('button', { name: '모두 동의' }))

    for (const box of screen.getAllByRole('checkbox')) {
      expect(box).toBeChecked()
    }
  })

  it('한 번 동의하면 다시 묻지 않는다', () => {
    window.localStorage.setItem(CONSENT_KEY, 'true')

    render(<ConsentGate>{child()}</ConsentGate>)

    expect(screen.getByText('업로드 화면')).toBeInTheDocument()
  })

  it('키에 버전이 붙어 있다', () => {
    // 약관이 바뀌면 다시 받아야 한다. 버전이 없으면 방법이 없다
    expect(CONSENT_KEY).toMatch(/v\d+$/)
  })

  it('거부해도 된다는 사실을 알린다', () => {
    // 거부권 고지는 의무다
    render(<ConsentGate>{child()}</ConsentGate>)

    expect(screen.getByText(/거부할 수 있으나/)).toBeInTheDocument()
  })

  it('수집 항목과 보유 기간을 모달 안에 직접 보여준다', () => {
    // 링크만 걸면 알렸다고 보기 어렵다
    render(<ConsentGate>{child()}</ConsentGate>)

    // IP 는 수집 항목과 보유 기간 두 곳에 나온다. 개수가 아니라 존재를 본다
    for (const word of ['대화 캡처', 'IP', '20분']) {
      expect(screen.getAllByText(new RegExp(word)).length).toBeGreaterThan(0)
    }
  })

  it('국외 이전 대상을 밝힌다', () => {
    render(<ConsentGate>{child()}</ConsentGate>)

    expect(screen.getByText(/미국/)).toBeInTheDocument()
    expect(screen.getByText(/Groq/)).toBeInTheDocument()
  })

  it('localStorage 를 못 써도 앱이 죽지 않는다', () => {
    // 사파리 프라이빗 모드 등. 동의를 매번 받게 되지만 화면은 뜬다
    const boom = () => {
      throw new Error('denied')
    }
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(boom)
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(boom)

    expect(() => render(<ConsentGate>{child()}</ConsentGate>)).not.toThrow()

    vi.restoreAllMocks()
  })
})
