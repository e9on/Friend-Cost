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

/** 동의 체크. 분석 시작의 전제 조건이다. */
async function agree() {
  await userEvent.click(screen.getByRole('checkbox'))
}

describe('업로드 화면', () => {
  it('처음에는 분석 버튼이 잠겨 있다', () => {
    renderUploader()

    expect(screen.getByRole('button', { name: '분석 시작' })).toBeDisabled()
  })

  it('이미지를 고르면 미리보기와 순서가 보인다', async () => {
    const { input } = renderUploader()

    select(input, [file('a.png'), file('b.png')])
    await agree()

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
    await agree()

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

describe('법적 고지', () => {
  it('본인 대화와 연령을 확인시킨다', () => {
    // 업로더가 상대방 동의를 받았는지 기술로 확인할 방법은 없다.
    // 무엇을 하고 있는지 자각하게 하는 것이 우리가 할 수 있는 전부다
    renderUploader()

    expect(
      screen.getByText(/내가 참여한 1:1 대화이고, 만 14세 이상입니다/),
    ).toBeInTheDocument()
  })

  it('동의하지 않으면 이미지를 골라도 시작할 수 없다', async () => {
    const { input } = renderUploader()

    select(input, [file('a.png')])

    expect(screen.getByRole('button', { name: '분석 시작' })).toBeDisabled()
  })

  it('동의만 하고 이미지가 없어도 시작할 수 없다', async () => {
    renderUploader()

    await agree()

    expect(screen.getByRole('button', { name: '분석 시작' })).toBeDisabled()
  })

  it('동의를 되돌리면 다시 잠긴다', async () => {
    const { input } = renderUploader()
    select(input, [file('a.png')])
    await agree()
    expect(screen.getByRole('button', { name: '분석 시작' })).toBeEnabled()

    await agree()

    expect(screen.getByRole('button', { name: '분석 시작' })).toBeDisabled()
  })

  it('약관과 처리방침을 열 수 있다', () => {
    // 문서를 만들어 두는 것으로 끝나지 않는다. 사용자가 보는 자리에 있어야
    // 한다. `운영-보안-법적고지-명세.md` 5장
    renderUploader()

    expect(screen.getByRole('button', { name: '이용약관' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '개인정보 처리방침' })).toBeInTheDocument()
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

describe('지원 범위 안내', () => {
  /**
   * 단체방은 감지되면 거절한다. 그 사실을 결과에서야 알려주면 사용자는
   * 캡처를 고르고 올리는 수고를 다 한 뒤에 실패를 본다.
   *
   * 실제로 단체방 캡처를 올려 GROUP_CHAT_DETECTED 로 거절된 일이 있었다.
   * 화면 어디에도 안 된다는 말이 없었다.
   */
  it('단체방은 안 된다고 미리 알려준다', () => {
    render(<Uploader onStart={() => undefined} busy={false} />)

    expect(screen.getByText(/단체(방| 대화)/)).toBeInTheDocument()
  })
})

describe('캡처에 남는 민감한 것', () => {
  it('우리가 못 지우는 것만 부탁한다', () => {
    // "개인정보를 가려주세요" 같은 넓은 부탁은 지켜지지 않는다.
    // 재미로 써보는 서비스에서 캡처를 편집할 사람은 거의 없다
    render(<Uploader onStart={vi.fn()} busy={false} />)

    const notice = screen.getByText(/가리고 올려주세요/)
    for (const word of ['전화번호', '주소', '계좌번호', '사진']) {
      expect(notice.textContent).toContain(word)
    }
  })

  it('이름은 자동으로 지운다고 밝힌다', () => {
    // 부탁 대신 보장할 수 있는 것은 부탁하지 않는다.
    // 무엇이 자동이고 무엇이 사용자 몫인지 갈라준다
    render(<Uploader onStart={vi.fn()} busy={false} />)

    expect(screen.getByText(/이름은 저희가 자동으로 지웁니다/)).toBeInTheDocument()
  })
})
