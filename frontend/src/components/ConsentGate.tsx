/**
 * 최초 입장 동의.
 *
 * 「개인정보 보호법」제22조는 **각 동의 사항을 구분하여 각각** 받으라고 한다.
 * 하나로 묶은 체크박스는 그 요건을 채우지 못한다. 그래서 넷으로 나눈다.
 *
 * 선택 동의는 두지 않는다. 광고도 마케팅도 하지 않으므로 선택 항목이 없고,
 * 그래서 "선택 동의를 강요했다"는 문제가 생길 여지도 없다.
 *
 * `Frontend-명세.md` 2.1
 */

import { useState, type ReactNode } from 'react'

import { sendEvent } from '../lib/events'
import type { LegalDoc } from './LegalModal'
import { LegalModal } from './LegalModal'

/**
 * 키에 버전을 붙인다. 약관이 바뀌면 다시 받아야 하는데 버전이 없으면 방법이
 * 없다. 문서를 고칠 때 이 숫자를 함께 올린다.
 */
export const CONSENT_KEY = 'fc.consent.v1'

interface Item {
  id: string
  label: string
  doc?: LegalDoc
}

const ITEMS: Item[] = [
  { id: 'age', label: '만 14세 이상입니다' },
  { id: 'terms', label: '이용약관에 동의합니다', doc: 'terms' },
  { id: 'privacy', label: '개인정보 수집·이용에 동의합니다', doc: 'privacy' },
  { id: 'transfer', label: '개인정보를 미국(Groq, Inc.)으로 이전하는 데 동의합니다' },
]

/** 저장소를 못 쓰는 환경(사파리 프라이빗 등)에서 앱이 죽지 않게 삼킨다. */
function readAgreed(): boolean {
  try {
    return window.localStorage.getItem(CONSENT_KEY) === 'true'
  } catch {
    return false
  }
}

function writeAgreed(): void {
  try {
    window.localStorage.setItem(CONSENT_KEY, 'true')
  } catch {
    // 못 남기면 다음에 다시 묻는다. 앱을 멈출 일은 아니다
  }
}

export function ConsentGate({ children }: { children: ReactNode }) {
  const [agreed, setAgreed] = useState(readAgreed)
  const [checked, setChecked] = useState<Record<string, boolean>>({})
  const [openDoc, setOpenDoc] = useState<LegalDoc | null>(null)

  if (agreed) return <>{children}</>

  const all = ITEMS.every((item) => checked[item.id])

  function toggle(id: string) {
    setChecked((prev) => ({ ...prev, [id]: !prev[id] }))
  }

  function agreeAll() {
    setChecked(Object.fromEntries(ITEMS.map((item) => [item.id, true])))
  }

  function enter() {
    writeAgreed()
    // 이미 동의한 사람에게는 보내지 않는다. 여기는 처음 동의할 때만 지난다
    void sendEvent('consent.agreed')
    setAgreed(true)
  }

  return (
    <>
      <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label="이용 동의">
        <div className="modal modal-consent">
          <h2 className="modal-title">시작하기 전에</h2>

          <p className="consent-lead">
            이 서비스는 <strong>재미로 보는 결과</strong>를 보여줍니다. 아래 항목에 모두 동의해야
            이용할 수 있습니다.
          </p>

          {/*
            링크만 걸면 "알렸다"고 보기 어렵다. 수집 항목과 보유 기간은
            모달 안에 직접 적는다.
          */}
          <dl className="consent-summary">
            <div>
              <dt>수집 항목</dt>
              <dd>대화 캡처 이미지, 추출된 대화 텍스트, 접속 IP</dd>
            </div>
            <div>
              <dt>이용 목적</dt>
              <dd>관계 지표 산출과 결과 제공</dd>
            </div>
            <div>
              <dt>보유 기간</dt>
              <dd>20분 뒤 자동 삭제 (IP는 저장하지 않음)</dd>
            </div>
          </dl>

          <ul className="consent-items">
            {ITEMS.map((item) => (
              <li key={item.id}>
                <label>
                  <input
                    type="checkbox"
                    checked={Boolean(checked[item.id])}
                    onChange={() => toggle(item.id)}
                  />
                  <span>
                    <em className="consent-required">[필수]</em> {item.label}
                  </span>
                </label>
                {item.doc && (
                  <button
                    type="button"
                    className="linkish"
                    onClick={() => setOpenDoc(item.doc ?? null)}
                  >
                    전문 보기
                  </button>
                )}
              </li>
            ))}
          </ul>

          {/* 거부권 고지는 의무다. 빼지 않는다 */}
          <p className="consent-refusal">
            동의를 거부할 수 있으나, 거부하면 서비스를 이용할 수 없습니다.
          </p>

          <div className="consent-actions">
            <button type="button" className="ghost" onClick={agreeAll}>
              모두 동의
            </button>
            <button type="button" className="cta" disabled={!all} onClick={enter}>
              동의하고 시작
            </button>
          </div>
        </div>
      </div>

      {openDoc && <LegalModal doc={openDoc} onClose={() => setOpenDoc(null)} />}
    </>
  )
}
