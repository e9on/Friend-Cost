/**
 * 사용 이벤트 전송.
 *
 * 보내고 잊는다. 응답을 기다리지 않고 실패해도 삼킨다. 집계가 사용자
 * 흐름을 막아서는 안 된다. 네트워크가 끊긴 사람에게 "집계 전송 실패"를
 * 보여줄 이유가 없다.
 *
 * `Frontend-명세.md` 4-1
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sendEvent } from './events'

describe('sendEvent', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('이름을 서버로 보낸다', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 204 }))
    vi.stubGlobal('fetch', fetchMock)

    await sendEvent('consent.agreed')

    const [url, init] = fetchMock.mock.calls[0]
    expect(String(url)).toContain('/events')
    expect(JSON.parse(init.body)).toEqual({ name: 'consent.agreed' })
  })

  it('실패해도 던지지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))

    await expect(sendEvent('page.view')).resolves.toBeUndefined()
  })

  it('서버가 오류를 줘도 던지지 않는다', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(null, { status: 429 })))

    await expect(sendEvent('page.view')).resolves.toBeUndefined()
  })

  it('fetch 가 없는 환경에서도 터지지 않는다', async () => {
    vi.stubGlobal('fetch', undefined)

    await expect(sendEvent('page.view')).resolves.toBeUndefined()
  })
})
