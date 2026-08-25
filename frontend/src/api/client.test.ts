/**
 * API 클라이언트.
 *
 * 서버 오류 봉투를 제대로 풀어야 실패 화면이 알맞은 안내를 고를 수 있다.
 * 네트워크 단절과 서버 오류를 구분하는 것도 여기 책임이다.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  ApiError,
  createAnalysis,
  deleteAnalysis,
  getResult,
  getStatus,
  requestDeletionOnUnload,
} from './client'

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'content-type': 'application/json' },
  })
}

function pngFile(name = 'shot.png'): File {
  return new File([new Uint8Array([0x89, 0x50, 0x4e, 0x47])], name, {
    type: 'image/png',
  })
}

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('createAnalysis', () => {
  it('이미지를 multipart 로 보낸다', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(202, {
        jobId: 'job-1',
        status: 'pending',
        expiresAt: 100,
        pollAfterSeconds: 2,
      }),
    )

    const result = await createAnalysis([pngFile('a.png'), pngFile('b.png')])

    expect(result.jobId).toBe('job-1')
    const [, init] = fetchMock.mock.calls[0]
    const body = init.body as FormData
    expect(body.getAll('images')).toHaveLength(2)
  })

  it('서버 오류 봉투를 ApiError 로 푼다', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(422, {
        error: {
          code: 'TOO_FEW_MESSAGES',
          message: '분석하기에 대화가 너무 짧습니다.',
          retryable: false,
        },
      }),
    )

    await expect(createAnalysis([pngFile()])).rejects.toMatchObject({
      code: 'TOO_FEW_MESSAGES',
      retryable: false,
      status: 422,
    })
  })

  it('네트워크가 끊기면 서버 오류와 다른 코드를 준다', async () => {
    fetchMock.mockRejectedValue(new TypeError('failed to fetch'))

    await expect(createAnalysis([pngFile()])).rejects.toMatchObject({
      code: 'NETWORK_ERROR',
      retryable: true,
      status: 0,
    })
  })

  it('오류 봉투가 아닌 응답도 삼키지 않는다', async () => {
    fetchMock.mockResolvedValue(new Response('<html>502</html>', { status: 502 }))

    await expect(createAnalysis([pngFile()])).rejects.toBeInstanceOf(ApiError)
  })
})

describe('getStatus', () => {
  it('상태 본문을 그대로 돌려준다', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(200, {
        jobId: 'job-1',
        status: 'processing',
        stage: 'analyzing',
        expiresAt: 100,
        pollAfterSeconds: 2,
        error: null,
      }),
    )

    const status = await getStatus('job-1')

    expect(status.stage).toBe('analyzing')
    expect(fetchMock.mock.calls[0][0]).toContain('/analyses/job-1')
  })

  it('만료를 없는 작업과 구분한다', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(410, {
        error: { code: 'JOB_EXPIRED', message: '만료', retryable: false },
      }),
    )

    await expect(getStatus('job-1')).rejects.toMatchObject({ code: 'JOB_EXPIRED' })
  })
})

describe('getResult', () => {
  it('아직 안 끝났으면 JOB_NOT_READY 를 던진다', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(409, {
        error: { code: 'JOB_NOT_READY', message: '진행 중', retryable: true },
      }),
    )

    await expect(getResult('job-1')).rejects.toMatchObject({ code: 'JOB_NOT_READY' })
  })
})

describe('deleteAnalysis', () => {
  it('204 본문 없음을 오류로 보지 않는다', async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    await expect(deleteAnalysis('job-1')).resolves.toBeUndefined()
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'DELETE' })
  })
})

describe('requestDeletionOnUnload', () => {
  it('sendBeacon 이 있으면 그것을 쓴다', () => {
    const beacon = vi.fn().mockReturnValue(true)
    vi.stubGlobal('navigator', { sendBeacon: beacon })

    requestDeletionOnUnload('job-1')

    expect(beacon).toHaveBeenCalledOnce()
    expect(beacon.mock.calls[0][0]).toContain('/analyses/job-1/deletion')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sendBeacon 이 없으면 keepalive fetch 로 대신한다', () => {
    vi.stubGlobal('navigator', {})
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }))

    requestDeletionOnUnload('job-1')

    expect(fetchMock).toHaveBeenCalledOnce()
    expect(fetchMock.mock.calls[0][1]).toMatchObject({
      method: 'POST',
      keepalive: true,
    })
  })

  it('삭제 요청이 실패해도 예외를 밖으로 내보내지 않는다', () => {
    // 실패해도 서버의 TTL이 대신 지운다. 이탈 중에 오류를 띄울 이유가 없다
    vi.stubGlobal('navigator', {})
    fetchMock.mockRejectedValue(new Error('gone'))

    expect(() => requestDeletionOnUnload('job-1')).not.toThrow()
  })
})
