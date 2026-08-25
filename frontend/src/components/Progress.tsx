/**
 * 분석 진행 화면.
 *
 * 서버가 알려주는 단계를 그대로 보여준다. 진행률은 단계에 매핑한 어림값이라
 * 실제 완료 비율이 아니지만, 멈춰 있는 것처럼 보이지 않게 하는 데 필요하다.
 */

import type { JobStage } from '../api/types'
import { STAGE_LABELS, STAGE_PROGRESS } from '../api/types'

interface Props {
  stage: JobStage | null
  phase: 'uploading' | 'running'
}

const STAGE_ORDER: JobStage[] = ['ocr', 'parsing', 'analyzing', 'scoring', 'reporting']

export function Progress({ stage, phase }: Props) {
  const percent = phase === 'uploading' ? 8 : stage ? STAGE_PROGRESS[stage] : 12
  const label =
    phase === 'uploading'
      ? '캡처를 올리는 중'
      : stage
        ? STAGE_LABELS[stage]
        : '분석을 준비하는 중'

  const currentIndex = stage ? STAGE_ORDER.indexOf(stage) : -1

  return (
    <section className="panel center">
      <div className="spinner" aria-hidden />
      <h2 className="progress-label">{label}</h2>
      <p className="progress-hint">대화가 길면 조금 더 걸릴 수 있어요.</p>

      <div
        className="bar"
        role="progressbar"
        aria-valuenow={percent}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="분석 진행률"
      >
        <div className="bar-fill" style={{ width: `${percent}%` }} />
      </div>

      <ol className="steps">
        {STAGE_ORDER.map((item, index) => {
          const done = currentIndex > index
          const active = currentIndex === index
          return (
            <li
              key={item}
              className={`step ${done ? 'step-done' : ''} ${active ? 'step-active' : ''}`}
            >
              <span className="step-dot" aria-hidden>
                {done ? '✓' : index + 1}
              </span>
              <span>{STAGE_LABELS[item]}</span>
            </li>
          )
        })}
      </ol>
    </section>
  )
}
