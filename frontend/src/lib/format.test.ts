/**
 * 화면 표시용 변환.
 *
 * 여기서 틀리면 서버가 준 정확한 숫자가 사용자에게 잘못 전달된다.
 */

import { describe, expect, it } from 'vitest'

import {
  CONFIDENCE_LABEL,
  CONFIDENCE_NOTE,
  formatCountdown,
  formatDuration,
  formatFee,
  formatPercent,
  formatSpan,
  formatWon,
  shareMessage,
} from './format'

describe('formatWon', () => {
  it('천 단위로 끊어 보여준다', () => {
    expect(formatWon(45000)).toBe('45,000원')
    expect(formatWon(1000)).toBe('1,000원')
    expect(formatWon(100000)).toBe('100,000원')
  })
})

describe('formatPercent', () => {
  it('비율을 백분율로 반올림한다', () => {
    expect(formatPercent(0.63)).toBe('63%')
    expect(formatPercent(0)).toBe('0%')
    expect(formatPercent(1)).toBe('100%')
  })

  it('소수점을 반올림한다', () => {
    expect(formatPercent(0.335)).toBe('34%')
  })
})

describe('formatDuration', () => {
  it('알 수 없음과 빠른 답장을 구분한다', () => {
    // 표본이 모자라면 서버가 null을 준다. 빠른 답장과는 다른 뜻이다
    expect(formatDuration(null)).toBe('알 수 없음')
    expect(formatDuration(0)).toBe('1분 이내')
  })

  it('1분 미만은 초 단위로 쓰지 않는다', () => {
    // 카톡 시각은 분 단위다. "45초"는 없는 정밀도를 주장하는 것이다
    expect(formatDuration(45)).toBe('1분 이내')
    expect(formatDuration(59)).toBe('1분 이내')
    expect(formatDuration(60)).toBe('1분')
  })

  it('1시간 미만은 분으로', () => {
    expect(formatDuration(300)).toBe('5분')
    expect(formatDuration(1860)).toBe('31분')
  })

  it('1시간 이상은 시간과 분으로', () => {
    expect(formatDuration(3600)).toBe('1시간')
    expect(formatDuration(5400)).toBe('1시간 30분')
    expect(formatDuration(7200)).toBe('2시간')
  })
})

describe('formatSpan', () => {
  it('기간을 사람이 읽는 단위로 줄인다', () => {
    expect(formatSpan(null)).toBe('기간 미상')
    expect(formatSpan(3600)).toBe('하루 이내')
    expect(formatSpan(86400 * 14)).toBe('약 14일')
    expect(formatSpan(86400 * 90)).toBe('약 3개월')
  })
})

describe('formatCountdown', () => {
  it('mm:ss 로 보여준다', () => {
    expect(formatCountdown(1200)).toBe('20:00')
    expect(formatCountdown(65)).toBe('1:05')
    expect(formatCountdown(9)).toBe('0:09')
  })

  it('만료 후에도 음수를 보여주지 않는다', () => {
    expect(formatCountdown(-30)).toBe('0:00')
  })
})

describe('신뢰도 안내', () => {
  it('세 등급 모두 이름이 있다', () => {
    expect(CONFIDENCE_LABEL.high).toBe('높음')
    expect(CONFIDENCE_LABEL.medium).toBe('보통')
    expect(CONFIDENCE_LABEL.low).toBe('낮음')
  })

  it('높음일 때만 경고를 붙이지 않는다', () => {
    expect(CONFIDENCE_NOTE.high).toBeNull()
    expect(CONFIDENCE_NOTE.medium).not.toBeNull()
    expect(CONFIDENCE_NOTE.low).not.toBeNull()
  })
})

describe('formatFee', () => {
  /**
   * 친구비는 정산액이다. 부호가 뜻을 갖는다.
   *
   * 화면에 "-36,000원"만 띄우면 읽히지 않는다. 마이너스가 '나쁜 관계'로
   * 오해되기 쉽다. 방향을 문구로 풀고 금액은 절댓값으로 보여준다.
   */
  it('양수면 친구에게 요청하라고 한다', () => {
    // 명사구("이 친구가 나에게 낼 친구비")보다 할 일을 말하는 편이
    // 무엇을 뜻하는지 바로 읽힌다
    const fee = formatFee(34000)

    expect(fee.direction).toBe('receive')
    expect(fee.amount).toBe('34,000원')
    expect(fee.label).toContain('요청')
  })

  it('음수면 내가 주라고 한다', () => {
    const fee = formatFee(-36000)

    expect(fee.direction).toBe('pay')
    expect(fee.amount).toBe('36,000원')
    expect(fee.label).toContain('주세요')
  })

  it('방향 문구는 둘 다 할 일로 끝난다', () => {
    // '요청하세요'와 '주어야 합니다'가 섞여 있었다. 한쪽은 시키는 말이고
    // 다른 쪽은 설명하는 말이라, 같은 자리에 번갈아 나오면 결이 달라진다
    for (const value of [34000, -36000]) {
      expect(formatFee(value).label.endsWith('하세요') || formatFee(value).label.endsWith('주세요')).toBe(true)
    }
  })

  it('방향마다 문구가 다르다', () => {
    const labels = [formatFee(1000), formatFee(-1000), formatFee(0)].map((f) => f.label)

    expect(new Set(labels).size).toBe(3)
  })

  it('음수여도 금액에 마이너스를 붙이지 않는다', () => {
    // 방향은 문구가 말한다. 숫자에까지 붙이면 두 번 말하는 셈이고
    // '마이너스 = 나쁨'으로 읽힌다
    expect(formatFee(-36000).amount).not.toContain('-')
  })

  it('0이면 정산할 것이 없다', () => {
    const fee = formatFee(0)

    expect(fee.direction).toBe('even')
    expect(fee.amount).toBe('0원')
  })
})

describe('shareMessage', () => {
  it('금액과 방향을 함께 담는다', () => {
    // 금액만 보내면 받는 쪽인지 주는 쪽인지 알 수 없다
    expect(shareMessage(-79000)).toContain('79,000원')
    expect(shareMessage(-79000)).toContain('낼')
    expect(shareMessage(79000)).toContain('받을')
  })

  it('받는 쪽과 주는 쪽의 문구가 다르다', () => {
    expect(shareMessage(79000)).not.toBe(shareMessage(-79000))
  })

  it('비긴 사이도 말이 된다', () => {
    expect(shareMessage(0)).toContain('비긴')
  })

  it('친구가 해볼 수 있게 권하는 말이 붙는다', () => {
    // 결과만 던지면 링크를 왜 눌러야 하는지 알 수 없다
    expect(shareMessage(-79000)).toMatch(/해볼래|해봐/)
  })
})
