/** 화면에 보여줄 값으로 다듬는다. */

import type { Confidence } from '../api/types'

export function formatWon(value: number): string {
  return `${value.toLocaleString('ko-KR')}원`
}

export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}

/**
 * 초를 사람이 읽는 시간으로 바꾼다.
 *
 * 표본이 모자라면 서버가 `null` 을 준다. 0초와 "알 수 없음"은 다른 뜻이므로
 * 0으로 뭉뚱그리지 않는다.
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '알 수 없음'
  if (seconds < 60) return `${seconds}초`

  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}분`

  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest === 0 ? `${hours}시간` : `${hours}시간 ${rest}분`
}

export function formatSpan(seconds: number | null): string {
  if (seconds === null) return '기간 미상'
  const days = Math.round(seconds / 86400)
  if (days < 1) return '하루 이내'
  if (days < 31) return `약 ${days}일`
  const months = Math.round(days / 30)
  return `약 ${months}개월`
}

export const CONFIDENCE_LABEL: Record<Confidence, string> = {
  high: '높음',
  medium: '보통',
  low: '낮음',
}

/** 신뢰도가 낮을 때 결과를 곧이곧대로 읽지 않도록 덧붙이는 안내. */
export const CONFIDENCE_NOTE: Record<Confidence, string | null> = {
  high: null,
  medium: '대화량이 넉넉하지 않아 결과가 흔들릴 수 있어요.',
  low: '분석할 대화가 적어 결과를 참고만 해주세요.',
}

/** 남은 시간을 mm:ss 로. TTL 카운트다운에 쓴다. */
export function formatCountdown(seconds: number): string {
  const safe = Math.max(0, seconds)
  const minutes = Math.floor(safe / 60)
  const rest = safe % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}
