/** 화면에 보여줄 값으로 다듬는다. */

import type { Confidence } from '../api/types'

export function formatWon(value: number): string {
  return `${value.toLocaleString('ko-KR')}원`
}

export type FeeDirection = 'receive' | 'pay' | 'even'

export interface FormattedFee {
  direction: FeeDirection
  label: string
  amount: string
}

/**
 * 친구비는 정산액이다. 부호가 뜻을 갖는다.
 *
 * 화면에 "-36,000원"만 띄우면 읽히지 않는다. 마이너스가 '나쁜 관계'로
 * 오해되기 쉬운데, 실제 뜻은 "상대가 나보다 더 기여했다"이다.
 *
 * 그래서 **방향은 문구로, 금액은 절댓값으로** 나눠 보여준다. 숫자에까지
 * 부호를 붙이면 같은 말을 두 번 하는 셈이다.
 */
export function formatFee(value: number): FormattedFee {
  if (value > 0) {
    return {
      direction: 'receive',
      label: '이 친구가 나에게 낼 친구비',
      amount: formatWon(value),
    }
  }
  if (value < 0) {
    return {
      direction: 'pay',
      label: '내가 이 친구에게 낼 친구비',
      amount: formatWon(-value),
    }
  }
  return { direction: 'even', label: '서로 비긴 사이', amount: formatWon(0) }
}

export function formatPercent(ratio: number): string {
  return `${Math.round(ratio * 100)}%`
}

/**
 * 초를 사람이 읽는 시간으로 바꾼다.
 *
 * 표본이 모자라면 서버가 `null` 을 준다. "알 수 없음"과 "빠름"은 다른 뜻이므로
 * 0으로 뭉뚱그리지 않는다.
 *
 * 1분 미만을 초 단위로 쓰지 않는 이유는 **원본에 그만한 정밀도가 없기**
 * 때문이다. 카카오톡 캡처의 시각은 분 단위라, 같은 분에 오간 메시지는
 * 간격이 0초로 계산된다. 화면에 "0초"라고 쓰면 가진 적 없는 정밀도를
 * 주장하는 셈이고, 사용자는 즉답으로 읽는다.
 */
export function formatDuration(seconds: number | null): string {
  if (seconds === null) return '알 수 없음'
  if (seconds < 60) return '1분 이내'

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
