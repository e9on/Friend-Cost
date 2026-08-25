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
  formatPercent,
  formatSpan,
  formatWon,
} from '../lib/format'
import { drawResultCard, saveCard } from '../lib/shareImage'

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
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'failed'>('idle')
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

  return (
    <section className="panel">
      <div className="fee">
        <span className="fee-label">이 친구의 친구비</span>
        <strong className="fee-value">{formatWon(scores.friendFee)}</strong>
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
        <button type="button" className="cta" onClick={handleSave} disabled={saveState === 'saving'}>
          {saveState === 'saving' ? '만드는 중…' : '결과 이미지 저장'}
        </button>
        <button type="button" className="ghost" onClick={onRestart}>
          다른 대화 분석하기
        </button>
      </div>

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
