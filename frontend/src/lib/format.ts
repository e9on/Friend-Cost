/** 화면에 보여줄 값으로 다듬는다. */

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
 *
 * 문구는 명사구가 아니라 **할 일**로 쓴다. "이 친구가 나에게 낼 친구비"보다
 * "친구에게 친구비를 요청하세요"가 무엇을 뜻하는지 바로 읽힌다.
 *
 * 두 방향 모두 시키는 말로 끝을 맞춘다. "요청하세요"와 "주어야 합니다"가
 * 섞여 있었는데, 한쪽은 시키는 말이고 다른 쪽은 설명하는 말이라 같은 자리에
 * 번갈아 나오면 결이 달라진다.
 */
export function formatFee(value: number): FormattedFee {
  if (value > 0) {
    return {
      direction: 'receive',
      label: '친구에게 친구비를 요청하세요',
      amount: formatWon(value),
    }
  }
  if (value < 0) {
    return {
      direction: 'pay',
      label: '친구에게 친구비를 주세요',
      amount: formatWon(-value),
    }
  }
  return { direction: 'even', label: '서로 비긴 사이입니다', amount: formatWon(0) }
}

/**
 * 친구에게 보낼 한 줄.
 *
 * 이미지만 보내면 상대는 화면 밖에서 무슨 말인지 모른다. 카카오톡 미리보기에
 * 뜨는 것은 이 문구이므로, 여기에 금액과 방향이 다 들어 있어야 한다.
 *
 * 권하는 말을 붙이는 이유는 링크를 왜 눌러야 하는지 알려주기 위해서다.
 * 결과만 던지면 자랑으로만 읽히고 링크는 눌리지 않는다.
 */
export function shareMessage(friendFee: number): string {
  const fee = formatFee(friendFee)
  if (fee.direction === 'even') {
    return `친구비 계산해보니 딱 비긴 사이래. 너도 해볼래?`
  }
  const who = fee.direction === 'receive' ? '내가 받을' : '내가 낼'
  return `친구비 계산해보니 ${who} 돈이 ${fee.amount}래. 너도 해볼래?`
}

export type Tone = 'good' | 'warn' | 'risk' | 'none'

// 세 칸으로 나눈다. 다섯 단계로 나누면 색이 다섯 가지가 되어 다시 구분이
// 안 된다.
//
// 경계를 삼등분(67/33)이 아니라 60/30 에 둔 것은 실측 때문이다. 친밀도 64,
// 연락 균형도 62 가 노랑으로 떨어졌는데 둘 다 준수한 값이라 어울리지 않았다.
// `Frontend-명세.md` 6.1.2
const GOOD_AT = 60
const RISK_AT = 30

/**
 * 0~100 점수를 색 톤으로 옮긴다.
 *
 * `higherIsBetter` 가 `false` 면 방향이 뒤집힌다. 손절 위험도 8점은 **잘 나온
 * 것이다.** 방향을 고정해두면 낮은 위험도가 빨갛게 칠해져 뜻이 정반대가 된다.
 */
export function scoreTone(value: number, higherIsBetter = true): Tone {
  // 값을 '좋은 정도'로 한 번 뒤집어 기준을 하나만 쓴다. 방향마다 부등호를
  // 따로 쓰면 경계에서 앞뒤가 어긋난다
  const goodness = higherIsBetter ? value : 100 - value
  if (goodness >= GOOD_AT) return 'good'
  if (goodness < RISK_AT) return 'risk'
  return 'warn'
}

/**
 * 반반에서 얼마나 떨어졌는지로 잰다.
 *
 * 어느 쪽으로 치우쳤는지는 보지 않는다. 내가 90%든 상대가 90%든 한쪽이
 * 짊어지고 있다는 사실은 같다.
 */
export function balanceTone(ratio: number): Tone {
  // 자릿수를 맞추지 않으면 |0.35 - 0.5| 가 0.15000000000000002 이 되어
  // 경계값이 한 칸 밀린다. 서버가 주는 비율도 소수점 셋째 자리다
  const off = Math.round(Math.abs(ratio - 0.5) * 1000) / 1000
  if (off <= 0.15) return 'good'
  if (off <= 0.3) return 'warn'
  return 'risk'
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

/**
 * 표본이 적을 때만 띄우는 한 줄.
 *
 * 신뢰도 등급(높음/보통/낮음)을 두었다가 없앴다. 재미로 읽는 결과에 정확도
 * 등급을 붙이면 사용자는 그것을 **자기 관계에 대한 평가**로 읽는데, 실제로
 * 등급을 끌어내리던 것은 관계가 아니라 우리 OCR 품질이었다.
 *
 * 판단 근거를 메시지 수 하나로 둔 이유는 그것이 **사용자가 어찌할 수 있는
 * 값**이기 때문이다. 캡처를 더 올리면 늘어난다. 시각 복원 비율은 OCR 이
 * 시각을 읽어내느냐에 달려 있어 사용자가 손댈 수 없다.
 *
 * `Frontend-명세.md` 6.4
 */
const THIN_MESSAGES = 40

export function thinDataNote(messageCount: number): string | null {
  if (messageCount >= THIN_MESSAGES) return null
  return '분석한 대화가 적어 결과가 흔들릴 수 있어요.'
}

/** 남은 시간을 mm:ss 로. TTL 카운트다운에 쓴다. */
export function formatCountdown(seconds: number): string {
  const safe = Math.max(0, seconds)
  const minutes = Math.floor(safe / 60)
  const rest = safe % 60
  return `${minutes}:${String(rest).padStart(2, '0')}`
}
