/**
 * 약관·처리방침 링크.
 *
 * `운영-보안-법적고지-명세.md` 5장이 요구하는 노출 항목이다.
 * 문서를 만들어 두는 것으로 끝나지 않고 사용자가 보는 자리에 있어야 한다.
 *
 * **앱 밖으로 내보내지 않는다.** 휴대폰에서 돌아오지 못하는 사용자가 생기고,
 * 문서가 두 벌이 되면 한쪽만 고쳐진다. `legal/` 이 단일 원본이다.
 */

import { useState } from 'react'

import type { LegalDoc } from './LegalModal'
import { LegalModal } from './LegalModal'

export function Legal() {
  const [open, setOpen] = useState<LegalDoc | null>(null)

  return (
    <>
      <p className="legal">
        <button type="button" className="linkish" onClick={() => setOpen('terms')}>
          이용약관
        </button>
        <span aria-hidden> · </span>
        <button type="button" className="linkish" onClick={() => setOpen('privacy')}>
          개인정보 처리방침
        </button>
      </p>

      {open && <LegalModal doc={open} onClose={() => setOpen(null)} />}
    </>
  )
}
