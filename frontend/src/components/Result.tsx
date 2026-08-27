/**
 * 결과 화면.
 *
 * 결과 이미지는 서버가 아니라 여기서 만든다. 기준 명세 11장.
 * TTL이 지나면 서버에서 사라지므로 남은 시간을 함께 보여준다.
 */

import { useEffect, useRef, useState } from 'react'

import type { AnalysisResult } from '../api/types'
import {
  CONFIDENCE_LABEL,
  CONFIDENCE_NOTE,
  formatCountdown,
  formatDuration,
  formatFee,
  formatPercent,
  formatSpan,
  shareMessage,
} from '../lib/format'
import { drawResultCard, saveCard, shareCard } from '../lib/shareImage'

interface Props {
  result: AnalysisResult
  onRestart: () => void
}

function useCountdown(expiresAt: number): number {
  const [left, setLeft] = useState(() => expiresAt - Math.floor(Date.now() / 1000))

  useEffect(() => {
    const id = window.setInterval(() => {
      setLeft(expiresAt - Math.floor(Date.now() / 1000))
    }, 1000)
    return () => window.clearInterval(id)
  }, [expiresAt])

  return left
}

export function Result({ result, onRestart }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [saveState, setSaveState] = useState<
    'idle' | 'saving' | 'saved' | 'failed' | 'copied'
  >('idle')
  const secondsLeft = useCountdown(result.expiresAt)
  const expired = secondsLeft <= 0

  useEffect(() => {
    if (canvasRef.current) drawResultCard(canvasRef.current, result)
  }, [result])

  async function handleSave() {
    if (!canvasRef.current) return
    setSaveState('saving')
    const outcome = await saveCard(canvasRef.current)
    setSaveState(outcome === 'failed' ? 'failed' : 'saved')
  }

  // 링크는 **결과가 아니라 서비스 첫 화면**을 가리킨다. 결과 링크를 뿌리면
  // 20분 TTL 과 "링크만 알면 누구나 열람" 문제가 따라온다. 친구에게 필요한
  // 것은 "너도 해봐"이지 내 결과 열람이 아니다.
  //
  // 도메인을 박아두지 않는 이유는 배포 주소가 바뀔 때 조용히 틀린 링크를
  // 뿌리게 되기 때문이다.
  async function handleShare() {
    if (!canvasRef.current) return
    setSaveState('saving')
    const outcome = await shareCard(
      canvasRef.current,
      shareMessage(scores.friendFee),
      window.location.origin,
    )
    if (outcome === 'failed') setSaveState('failed')
    else if (outcome === 'copied') setSaveState('copied')
    else setSaveState('saved')
  }

  const { scores, report, meta } = result
  const note = CONFIDENCE_NOTE[scores.confidence]

  const metrics = [
    { label: '친밀도', value: `${scores.intimacy}`, unit: '점' },
    { label: '손절 위험도', value: `${scores.breakupRisk}`, unit: '점' },
    { label: '연락 균형도', value: `${scores.contactBalance}`, unit: '점' },
    { label: '내가 먼저', value: formatPercent(scores.firstContactRatio), unit: '' },
    { label: '내 답장', value: formatDuration(scores.avgReplySeconds.me), unit: '' },
    { label: '상대 답장', value: formatDuration(scores.avgReplySeconds.peer), unit: '' },
  ]

  // 부호는 문구가 말하고 금액은 절댓값으로 보여준다.
  // "-36,000원"만 띄우면 '나쁜 관계'로 읽힌다
  const fee = formatFee(scores.friendFee)

  return (
    <section className="panel">
      <div className={`fee fee-${fee.direction}`}>
        <span className="fee-label">{fee.label}</span>
        <strong className="fee-value">{fee.amount}</strong>
      </div>

      <h2 className="headline">{report.headline}</h2>
      <p className="summary">{report.summary}</p>

      {note && <p className="confidence-note">{note}</p>}

      <div className="metrics">
        {metrics.map((metric) => (
          <div className="metric" key={metric.label}>
            <span className="metric-label">{metric.label}</span>
            <span className="metric-value">
              {metric.value}
              {metric.unit && <em>{metric.unit}</em>}
            </span>
          </div>
        ))}
      </div>

      {report.sections.map((section) => (
        <article className="section" key={section.title}>
          <h3>{section.title}</h3>
          <p>{section.body}</p>
        </article>
      ))}

      <article className="advice">
        <h3>이렇게 해보면 어때요</h3>
        <p>{report.advice}</p>
      </article>

      <dl className="meta">
        <div>
          <dt>분석한 메시지</dt>
          <dd>{meta.messageCount.toLocaleString('ko-KR')}개</dd>
        </div>
        <div>
          <dt>대화 기간</dt>
          <dd>{formatSpan(meta.spanSeconds)}</dd>
        </div>
        <div>
          <dt>신뢰도</dt>
          <dd>{CONFIDENCE_LABEL[scores.confidence]}</dd>
        </div>
      </dl>

      {meta.sampled && (
        <p className="sampled-note">
          대화가 길어 일부만 골라 분석했어요. 앞부분과 최근 대화를 중심으로 봤습니다.
        </p>
      )}

      <canvas ref={canvasRef} className="share-canvas" aria-label="저장할 결과 카드" />

      <div className="actions">
        <button
          type="button"
          className="cta"
          onClick={handleShare}
          disabled={saveState === 'saving'}
        >
          {saveState === 'saving' ? '준비하는 중…' : '친구에게 공유'}
        </button>
        <button
          type="button"
          className="ghost"
          onClick={handleSave}
          disabled={saveState === 'saving'}
        >
          결과 이미지 저장
        </button>
        <button type="button" className="ghost" onClick={onRestart}>
          다른 대화 분석하기
        </button>
      </div>

      {saveState === 'copied' && (
        <p className="notice">공유가 안 되는 기기라 링크를 복사했어요. 붙여넣어 보내주세요.</p>
      )}

      {saveState === 'failed' && (
        <p className="problem">이미지를 만들지 못했어요. 화면을 캡처해 주세요.</p>
      )}

      <p className={`ttl ${expired ? 'ttl-expired' : ''}`}>
        {expired
          ? '결과가 서버에서 삭제되었어요. 저장한 이미지는 그대로 남아 있습니다.'
          : `${formatCountdown(secondsLeft)} 뒤 서버에서 자동 삭제됩니다.`}
      </p>

      <p className="disclaimer">{report.disclaimer}</p>
    </section>
  )
}
