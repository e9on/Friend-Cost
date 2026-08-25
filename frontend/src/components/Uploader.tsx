/**
 * 대화 캡처 업로드 화면.
 *
 * 서버가 다시 검증하지만, 여기서 먼저 걸러 헛된 왕복을 줄인다.
 * 제한값은 `mdfiles/API-명세.md` 4장과 같아야 한다.
 */

import { useRef, useState } from 'react'

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

      <button
        type="button"
        className="cta"
        disabled={busy || picked.length === 0}
        onClick={() => onStart(picked.map((item) => item.file))}
      >
        {busy ? '분석 준비 중…' : '분석 시작'}
      </button>

      <p className="privacy">
        올린 이미지는 분석이 끝나는 즉시 지워지고, 결과도 20분 뒤 자동으로 사라져요.
        계정도 기록도 남지 않습니다.
      </p>
    </section>
  )
}
