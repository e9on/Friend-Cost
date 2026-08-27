/**
 * 약관·처리방침 링크.
 *
 * `운영-보안-법적고지-명세.md` 5장이 요구하는 노출 항목이다. 문서를 만들어
 * 두는 것으로 끝나지 않고 사용자가 보는 자리에 있어야 한다.
 */

import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'

import { Legal } from './Legal'

describe('약관 링크', () => {
  it('두 문서를 모두 열 수 있다', () => {
    render(<Legal />)

    expect(screen.getByRole('button', { name: '이용약관' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '개인정보 처리방침' })).toBeInTheDocument()
  })

  it('"준비 중"이라고 하지 않는다', () => {
    // 초안은 이미 있다. 준비 중이라고 두면 공개 직전에 잊는다
    render(<Legal />)

    expect(screen.queryByText(/준비 중/)).not.toBeInTheDocument()
  })

  it('앱 안에서 전문을 보여준다', async () => {
    // 앱 밖으로 내보내면 휴대폰에서 돌아오지 못하는 사용자가 생긴다
    render(<Legal />)

    await userEvent.click(screen.getByRole('button', { name: '이용약관' }))

    expect(screen.getByRole('dialog', { name: '이용약관' })).toBeInTheDocument()
  })

  it('초안이라는 사실을 감추지 않는다', async () => {
    // 법률 검토 전이다. 표기를 지우면 검토받은 문서인 척하는 것이 된다
    render(<Legal />)

    await userEvent.click(screen.getByRole('button', { name: '이용약관' }))

    expect(screen.getAllByText(/초안/).length).toBeGreaterThan(0)
  })
})
