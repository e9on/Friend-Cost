/**
 * 사용 이벤트 전송.
 *
 * 서버는 분석 요청이 들어와야만 안다. 그 전에 떠난 사람은 흔적이 없다.
 * 이탈 지점이 정확히 거기이므로 화면이 알려준다.
 *
 * **보내고 잊는다.** 응답을 기다리지 않고, 실패해도 삼킨다. 집계가 사용자
 * 흐름을 막아서는 안 된다. 네트워크가 끊긴 사람에게 "집계 전송 실패"를
 * 보여줄 이유가 없다.
 *
 * **식별자를 붙이지 않는다.** 세션 ID 도 쿠키도 없다. 그래서 "방문 100,
 * 동의 60" 은 알아도 "그 60명이 누구인가"는 모른다. 개인을 이어붙이려면
 * 식별자를 심어야 하고, 그것은 이 서비스가 하지 않기로 한 일이다.
 *
 * 이름은 `데이터-계약-명세.md` 12-1 이 정한다. 서버도 같은 목록만 받는다.
 */

const BASE = import.meta.env.VITE_API_BASE ?? '/v1'

export type UsageEvent =
  | 'page.view'
  | 'consent.agreed'
  | 'upload.selected'
  | 'result.viewed'
  | 'result.shared'
  | 'result.saved'

export async function sendEvent(name: UsageEvent): Promise<void> {
  try {
    await fetch(`${BASE}/events`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
      // 화면을 떠나는 순간에도 나가도록 둔다
      keepalive: true,
    })
  } catch {
    // 집계는 사용자 흐름보다 뒤에 있다. 조용히 넘어간다
  }
}
