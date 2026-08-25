/**
 * 업로드 화면.
 *
 * 서버가 다시 검증하지만 여기서 먼저 걸러 헛된 왕복을 줄인다.
 * 제한값이 `API-명세.md` 4장과 어긋나면 사용자가 서버에 가서야 거절당한다.
 */

import { fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { Uploader } from './Uploader'

function file(name: string, type = 'image/png', bytes = 1024): File {
  return new File([new Uint8Array(bytes)], name, { type })
}

function renderUploader(busy = false) {
  const onStart = vi.fn()
  render(<Uploader onStart={onStart} busy={busy} />)
  const input = document.querySelector('input[type="file"]') as HTMLInputElement
  return { onStart, input }
}

/**
 * 파일 입력은 드롭존 뒤에 숨어 있어 userEvent가 건드리지 못한다.
 * accept 속성의 사전 필터도 우회하므로, 드래그 앤 드롭으로 들어오는
 * 경로(브라우저가 걸러주지 않는 경로)를 흉내 내는 셈이기도 하다.
 */
function select(input: HTMLInputElement, files: File[]) {
  fireEvent.change(input, { target: { files } })
}

describe('업로드 화면', () => {
  it('처음에는 분석 버튼이 잠겨 있다', () => {
    renderUploader()

    expect(screen.getByRole('button', { name: '분석 시작' })).toBeDisabled()
  })

  it('이미지를 고르면 미리보기와 순서가 보인다', async () => {
    const { input } = renderUploader()

    select(input, [file('a.png'), file('b.png')])

    expect(screen.getAllByRole('img')).toHaveLength(2)
    expect(screen.getByAltText('1번째 캡처 미리보기')).toBeInTheDocument()
    expect(screen.getByText('1')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '분석 시작' })).toBeEnabled()
  })

  it('올린 순서가 시간 순서라고 알려준다', async () => {
    const { input } = renderUploader()

    select(input, [file('a.png')])

    expect(screen.getByText(/번호 순서대로 시간이 흐른다/)).toBeInTheDocument()
  })

  it('고른 이미지를 뺄 수 있다', async () => {
    const { input } = renderUploader()
    select(input, [file('a.png'), file('b.png')])

    await userEvent.click(screen.getByRole('button', { name: '1번째 이미지 빼기' }))

    expect(screen.getAllByRole('img')).toHaveLength(1)
  })

  it('분석 시작을 누르면 고른 파일을 넘긴다', async () => {
    const { input, onStart } = renderUploader()
    select(input, [file('a.png')])

    await userEvent.click(screen.getByRole('button', { name: '분석 시작' }))

    expect(onStart).toHaveBeenCalledOnce()
    expect(onStart.mock.calls[0][0]).toHaveLength(1)
  })

  it('작업 중에는 버튼이 잠긴다', () => {
    renderUploader(true)

    expect(screen.getByRole('button', { name: '분석 준비 중…' })).toBeDisabled()
  })

  it('임시 저장 정책을 미리 알려준다', () => {
    renderUploader()

    expect(screen.getByText(/분석이 끝나는 즉시 지워지고/)).toBeInTheDocument()
  })
})

describe('업로드 사전 검증', () => {
  it('10장을 넘기면 막는다', async () => {
    const { input, onStart } = renderUploader()
    const many = Array.from({ length: 11 }, (_, index) => file(`${index}.png`))

    select(input, many)

    // 드롭존 안내에도 "최대 10장"이 있으므로 오류 문구만 집어서 본다
    expect(screen.getByText(/이미지는 최대 10장까지/)).toBeInTheDocument()
    expect(onStart).not.toHaveBeenCalled()
  })

  it('허용하지 않는 형식을 막는다', async () => {
    const { input } = renderUploader()

    select(input, [file('a.gif', 'image/gif')])

    expect(screen.getByText(/PNG, JPG, WEBP/)).toBeInTheDocument()
  })

  it('한 장이 5MB를 넘으면 막는다', async () => {
    const { input } = renderUploader()

    select(input, [file('big.png', 'image/png', 6 * 1024 * 1024)])

    expect(screen.getByText(/5MB를 넘는/)).toBeInTheDocument()
  })

  it('전체 20MB를 넘으면 막는다', async () => {
    const { input } = renderUploader()
    const chunks = Array.from({ length: 5 }, (_, index) =>
      file(`${index}.png`, 'image/png', 4.5 * 1024 * 1024),
    )

    select(input, chunks)

    expect(screen.getByText(/전체 용량이 20MB/)).toBeInTheDocument()
  })
})
