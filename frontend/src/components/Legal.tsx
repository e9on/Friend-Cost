/**
 * 약관·처리방침 링크.
 *
 * `운영-보안-법적고지-명세.md` 5장이 요구하는 노출 항목이다.
 * 문서를 만들어 두는 것으로 끝나지 않고 사용자가 보는 자리에 있어야 한다.
 *
 * 링크 대상 페이지는 법률 검토 후 작성한다. 그때까지 자리를 비워두면
 * 공개 직전에 잊어버리므로, 아직 준비 중임을 명시적으로 드러낸다.
 */

const TERMS_URL = import.meta.env.VITE_TERMS_URL ?? ''
const PRIVACY_URL = import.meta.env.VITE_PRIVACY_URL ?? ''

export function Legal() {
  if (!TERMS_URL || !PRIVACY_URL) {
    return (
      <p className="legal legal-pending">
        이용약관과 개인정보 처리방침은 준비 중입니다.
      </p>
    )
  }

  return (
    <p className="legal">
      <a href={TERMS_URL} target="_blank" rel="noreferrer">
        이용약관
      </a>
      <span aria-hidden> · </span>
      <a href={PRIVACY_URL} target="_blank" rel="noreferrer">
        개인정보 처리방침
      </a>
    </p>
  )
}
