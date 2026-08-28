/**
 * 대화 캡처 업로드 화면.
 *
 * 서버가 다시 검증하지만, 여기서 먼저 걸러 헛된 왕복을 줄인다.
 * 제한값은 `mdfiles/API-명세.md` 4장과 같아야 한다.
 */

import { useRef, useState } from 'react'

import { sendEvent } from '../lib/events'

import { Legal } from './Legal'

const MAX_IMAGES = 10
const MAX_IMAGE_BYTES = 5 * 1024 * 1024
const MAX_TOTAL_BYTES = 20 * 1024 * 1024
const ALLOWED = ['image/png', 'image/jpeg', 'image/webp']

interface Props {
  onStart: (files: File[]) => void
  busy: boolean
}

interface Picked {
  file: File
  url: string
}

export function Uploader({ onStart, busy }: Props) {
  const [picked, setPicked] = useState<Picked[]>([])
  const [problem, setProblem] = useState<string | null>(null)
  // 업로더가 상대방 동의를 받았는지 기술적으로 확인할 방법은 없다.
  // 확인시켜서 무엇을 하고 있는지 자각하게 하는 것이 우리가 할 수 있는 전부다.
  const [agreed, setAgreed] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function validate(files: File[]): string | null {
    if (files.length === 0) return '이미지를 한 장 이상 골라주세요.'
    if (files.length > MAX_IMAGES) return `이미지는 최대 ${MAX_IMAGES}장까지 올릴 수 있어요.`

    let total = 0
    for (const file of files) {
      if (!ALLOWED.includes(file.type)) return 'PNG, JPG, WEBP 파일만 올릴 수 있어요.'
      if (file.size > MAX_IMAGE_BYTES) return '한 장에 5MB를 넘는 이미지가 있어요.'
      total += file.size
    }
    if (total > MAX_TOTAL_BYTES) return '전체 용량이 20MB를 넘어요.'
    return null
  }

  function handleSelect(list: FileList | null) {
    if (!list) return
    const files = Array.from(list)
    const found = validate(files)
    setProblem(found)
    if (found) return

    picked.forEach((item) => URL.revokeObjectURL(item.url))
    setPicked(files.map((file) => ({ file, url: URL.createObjectURL(file) })))
    // 고르기까지 갔는지와 시작까지 갔는지는 다른 이야기다. 그 사이에서
    // 떠나는 사람이 있다면 체크박스가 걸림돌이라는 뜻이다
    void sendEvent('upload.selected')
  }

  function remove(index: number) {
    URL.revokeObjectURL(picked[index].url)
    const next = picked.filter((_, position) => position !== index)
    setPicked(next)
    setProblem(null)
  }

  return (
    <section className="panel">
      <h1 className="title">
        친구비 <span className="title-accent">측정기</span>
      </h1>
      <p className="lede">
        카카오톡 1:1 대화 캡처를 올리면 두 사람의 관계를 숫자로 보여드려요.
      </p>
      <p className="lede-note">
        단체 대화방은 분석할 수 없어요. 지표가 두 사람 사이를 전제로 하거든요.
      </p>

      <div
        className="dropzone"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault()
          handleSelect(event.dataTransfer.files)
        }}
      >
        <input
          ref={inputRef}
          type="file"
          accept={ALLOWED.join(',')}
          multiple
          hidden
          onChange={(event) => handleSelect(event.target.files)}
        />
        <div className="dropzone-icon" aria-hidden>
          🗂️
        </div>
        <p className="dropzone-text">캡처를 여기에 놓거나 눌러서 고르기</p>
        <p className="dropzone-hint">PNG · JPG · WEBP / 최대 {MAX_IMAGES}장</p>
      </div>

      {picked.length > 0 && (
        <>
          <div className="thumbs">
            {picked.map((item, index) => (
              <div className="thumb" key={item.url}>
                <img src={item.url} alt={`${index + 1}번째 캡처 미리보기`} />
                <button
                  type="button"
                  className="thumb-remove"
                  onClick={() => remove(index)}
                  aria-label={`${index + 1}번째 이미지 빼기`}
                >
                  ×
                </button>
                <span className="thumb-order">{index + 1}</span>
              </div>
            ))}
          </div>
          <p className="thumb-note">
            번호 순서대로 시간이 흐른다고 봅니다. 위에서 아래로 이어지게 올려주세요.
          </p>
        </>
      )}

      {problem && <p className="problem">{problem}</p>}

      <label className="consent">
        <input
          type="checkbox"
          checked={agreed}
          onChange={(event) => setAgreed(event.target.checked)}
        />
        <span>
          내가 참여한 1:1 대화이고, 만 14세 이상입니다.
        </span>
      </label>

      <button
        type="button"
        className="cta"
        disabled={busy || picked.length === 0 || !agreed}
        onClick={() => onStart(picked.map((item) => item.file))}
      >
        {busy ? '분석 준비 중…' : '분석 시작'}
      </button>

      <p className="privacy">
        올린 이미지는 분석이 끝나는 즉시 지워지고, 결과도 20분 뒤 자동으로 사라져요.
        계정도 기록도 남지 않습니다.
      </p>

      {/*
        부탁의 범위를 **우리가 못 지우는 것**에만 한정한다. "개인정보를
        가려주세요" 같은 넓은 부탁은 지켜지지 않는다. 재미로 써보는
        서비스에서 캡처를 일일이 편집할 사람은 거의 없고, 지키지 않을 것을
        알면서 넣는 고지는 면피용이 된다.

        이름을 부탁하지 않는 이유는 코드가 이미 지우기 때문이다
        (`OCR-Parser-명세.md` 7.1). 그 사실을 함께 밝혀 무엇이 자동이고
        무엇이 사용자 몫인지 가른다. `Frontend-명세.md` 4.5
      */}
      <p className="sensitive-note">
        캡처에 <strong>전화번호·주소·계좌번호·사진</strong>이 보이면 가리고 올려주세요.
        대화 상대의 이름은 저희가 자동으로 지웁니다.
      </p>

      <Legal />
    </section>
  )
}
