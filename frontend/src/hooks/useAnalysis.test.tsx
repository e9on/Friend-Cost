/**
 * 분석 수명주기 훅.
 *
 * 생성 -> 폴링 -> 결과 -> 삭제. 기준 명세 4장의 흐름을 그대로 밟는지 본다.
 * 특히 이탈 시 삭제 요청은 눈에 보이지 않아 깨져도 알아채기 어렵다.
 */

import { act, renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { useAnalysis } from './useAnalysis'
import type { AnalysisResult, StatusResponse } from '../api/types'

const client = vi.hoisted(() => ({
  createAnalysis: vi.fn(),
  getStatus: vi.fn(),
  getResult: vi.fn(),
  deleteAnalysis: vi.fn(),
  requestDeletionOnUnload: vi.fn(),
}))

vi.mock('../api/client', async () => {
  const actual = await vi.importActual<typeof import('../api/client')>('../api/client')
  return { ...actual, ...client }
})

const RESULT: AnalysisResult = {
  jobId: 'job-1',
  scores: {
    friendFee: 63000,
    intimacy: 64,
    breakupRisk: 38,
    firstContactRatio: 0.63,
    avgReplySeconds: { me: 420, peer: 1860 },
    contactBalance: 74,
  },
  report: {
    headline: '서로 챙기는 사이',
    summary: '요약',
    sections: [
      { title: '연락의 흐름', body: '본문' },
      { title: '지켜볼 지점', body: '본문' },
    ],
    advice: '제안',
    disclaimer: '재미로 보는 결과입니다.',
  },
  meta: { messageCount: 184, imageCount: 5, sampled: false, spanSeconds: 1209600 },
  expiresAt: 2000,
}

function status(partial: Partial<StatusResponse>): StatusResponse {
  return {
    jobId: 'job-1',
    status: 'processing',
    stage: null,
    expiresAt: 2000,
    pollAfterSeconds: 0,
    error: null,
    ...partial,
  }
}

function png(): File {
  return new File([new Uint8Array(4)], 'a.png', { type: 'image/png' })
}

beforeEach(() => {
  vi.clearAllMocks()
  client.createAnalysis.mockResolvedValue({
    jobId: 'job-1',
    status: 'pending',
    expiresAt: 2000,
    pollAfterSeconds: 0,
  })
})

describe('성공 흐름', () => {
  it('생성하고 폴링해서 결과까지 간다', async () => {
    client.getStatus
      .mockResolvedValueOnce(status({ stage: 'ocr' }))
      .mockResolvedValueOnce(status({ stage: 'analyzing' }))
      .mockResolvedValue(status({ status: 'done' }))
    client.getResult.mockResolvedValue(RESULT)

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })

    await waitFor(() => expect(result.current.phase).toBe('done'))
    expect(result.current.result?.scores.friendFee).toBe(63000)
  })

  it('폴링 도중 단계를 노출한다', async () => {
    client.getStatus
      .mockResolvedValueOnce(status({ stage: 'analyzing' }))
      .mockResolvedValue(status({ status: 'done' }))
    client.getResult.mockResolvedValue(RESULT)

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })

    await waitFor(() => expect(result.current.phase).toBe('done'))
    expect(client.getStatus).toHaveBeenCalled()
  })

  it('서버가 준 폴링 간격을 따른다', async () => {
    client.createAnalysis.mockResolvedValue({
      jobId: 'job-1',
      status: 'pending',
      expiresAt: 2000,
      pollAfterSeconds: 5,
    })
    vi.useFakeTimers()

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })

    expect(client.getStatus).not.toHaveBeenCalled()
    await act(async () => {
      vi.advanceTimersByTime(5000)
    })
    vi.useRealTimers()
  })
})

describe('실패 흐름', () => {
  it('서버가 failed 를 주면 오류를 그대로 보여준다', async () => {
    client.getStatus.mockResolvedValue(
      status({
        status: 'failed',
        error: { code: 'TOO_FEW_MESSAGES', message: '짧음', retryable: false },
      }),
    )

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })

    await waitFor(() => expect(result.current.phase).toBe('failed'))
    expect(result.current.error?.code).toBe('TOO_FEW_MESSAGES')
    expect(client.getResult).not.toHaveBeenCalled()
  })

  it('생성 자체가 막히면 폴링하지 않는다', async () => {
    const { ApiError } = await import('../api/client')
    client.createAnalysis.mockRejectedValue(
      new ApiError(429, { code: 'RATE_LIMITED', message: '잦음', retryable: true }),
    )

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })

    expect(result.current.phase).toBe('failed')
    expect(result.current.error?.code).toBe('RATE_LIMITED')
    expect(client.getStatus).not.toHaveBeenCalled()
  })

  it('폴링 중 연결이 끊겨도 화면이 멈추지 않는다', async () => {
    const { ApiError } = await import('../api/client')
    client.getStatus.mockRejectedValue(
      new ApiError(0, { code: 'NETWORK_ERROR', message: '끊김', retryable: true }),
    )

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })

    await waitFor(() => expect(result.current.phase).toBe('failed'))
    expect(result.current.error?.code).toBe('NETWORK_ERROR')
  })
})

describe('임시 데이터 정리', () => {
  it('다시 시작하면 서버에서 지운다', async () => {
    client.getStatus.mockResolvedValue(status({ status: 'done' }))
    client.getResult.mockResolvedValue(RESULT)
    client.deleteAnalysis.mockResolvedValue(undefined)

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })
    await waitFor(() => expect(result.current.phase).toBe('done'))

    await act(async () => {
      result.current.reset()
    })

    await waitFor(() => expect(client.deleteAnalysis).toHaveBeenCalledWith('job-1'))
    expect(result.current.phase).toBe('idle')
  })

  it('화면을 벗어나면 삭제를 요청한다', async () => {
    client.getStatus.mockResolvedValue(status({ status: 'done' }))
    client.getResult.mockResolvedValue(RESULT)

    const { result, unmount } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })
    await waitFor(() => expect(result.current.phase).toBe('done'))

    unmount()

    expect(client.requestDeletionOnUnload).toHaveBeenCalledWith('job-1')
  })

  it('삭제 요청이 실패해도 화면은 초기 상태로 돌아간다', async () => {
    client.getStatus.mockResolvedValue(status({ status: 'done' }))
    client.getResult.mockResolvedValue(RESULT)
    client.deleteAnalysis.mockRejectedValue(new Error('gone'))

    const { result } = renderHook(() => useAnalysis())
    await act(async () => {
      await result.current.start([png()])
    })
    await waitFor(() => expect(result.current.phase).toBe('done'))

    await act(async () => {
      result.current.reset()
    })

    expect(result.current.phase).toBe('idle')
  })
})

describe('StrictMode 이중 마운트', () => {
  /**
   * React 는 개발 모드에서 마운트 -> 언마운트 -> 재마운트 한다.
   * 정리 함수가 aliveRef 를 false 로 바꾸고 되돌리지 않으면, 재마운트 뒤
   * 모든 동작이 조용히 중단된다.
   *
   * 실제로 브라우저에서 업로드가 202 로 성공한 뒤 폴링 요청이 하나도 나가지
   * 않았다. 화면은 첫 단계에 멈춰 있고 오류도 나지 않는다. 서버는 8.5초 만에
   * 결과를 냈는데 사용자는 영영 모른다.
   *
   * 기존 테스트가 이것을 잡지 못한 이유는 StrictMode 없이 렌더하기 때문이다.
   */
  it('재마운트 뒤에도 폴링을 시작한다', async () => {
    client.createAnalysis.mockResolvedValue({
      jobId: 'job-1',
      status: 'pending',
      expiresAt: 1_700_000_000,
      pollAfterSeconds: 0,
    })
    client.getStatus.mockResolvedValue({
      jobId: 'job-1',
      status: 'done',
      stage: null,
      expiresAt: 1_700_000_000,
      pollAfterSeconds: null,
      error: null,
    } satisfies StatusResponse)
    client.getResult.mockResolvedValue(RESULT)

    const { result } = renderHook(() => useAnalysis(), {
      reactStrictMode: true,
    })

    await act(async () => {
      await result.current.start([new File(['x'], 'a.png', { type: 'image/png' })])
    })

    await waitFor(() => expect(client.getStatus).toHaveBeenCalled())
    await waitFor(() => expect(result.current.phase).toBe('done'))
  })

  it('재마운트 뒤 실패도 화면에 전달한다', async () => {
    client.createAnalysis.mockResolvedValue({
      jobId: 'job-2',
      status: 'pending',
      expiresAt: 1_700_000_000,
      pollAfterSeconds: 0,
    })
    client.getStatus.mockResolvedValue({
      jobId: 'job-2',
      status: 'failed',
      stage: null,
      expiresAt: 1_700_000_000,
      pollAfterSeconds: null,
      error: {
        code: 'GROUP_CHAT_DETECTED',
        message: '단체 대화방은 분석할 수 없습니다.',
        retryable: false,
      },
    } satisfies StatusResponse)

    const { result } = renderHook(() => useAnalysis(), {
      reactStrictMode: true,
    })

    await act(async () => {
      await result.current.start([new File(['x'], 'a.png', { type: 'image/png' })])
    })

    await waitFor(() => expect(result.current.phase).toBe('failed'))
    expect(result.current.error?.code).toBe('GROUP_CHAT_DETECTED')
  })
})
