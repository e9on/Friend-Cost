/**
 * 분석 한 건의 수명주기.
 *
 * 생성 -> 폴링 -> 결과 -> 삭제까지를 한곳에서 다룬다.
 * 화면은 여기서 나온 상태만 그리면 된다.
 */

import { useCallback, useEffect, useRef, useState } from 'react'

import {
  ApiError,
  createAnalysis,
  deleteAnalysis,
  getResult,
  getStatus,
  requestDeletionOnUnload,
} from '../api/client'
import type { AnalysisResult, ErrorBody, JobStage } from '../api/types'

export type Phase = 'idle' | 'uploading' | 'running' | 'done' | 'failed'

interface State {
  phase: Phase
  stage: JobStage | null
  result: AnalysisResult | null
  error: ErrorBody | null
  expiresAt: number | null
}

const INITIAL: State = {
  phase: 'idle',
  stage: null,
  result: null,
  error: null,
  expiresAt: null,
}

const FALLBACK_POLL_SECONDS = 2

function toErrorBody(error: unknown): ErrorBody {
  if (error instanceof ApiError) {
    return { code: error.code, message: error.message, retryable: error.retryable }
  }
  return {
    code: 'UNKNOWN',
    message: '알 수 없는 오류가 발생했습니다.',
    retryable: true,
  }
}

export function useAnalysis() {
  const [state, setState] = useState<State>(INITIAL)

  // 렌더와 무관한 값이라 ref에 둔다. 언마운트 시 정리에도 쓴다
  const jobIdRef = useRef<string | null>(null)
  const timerRef = useRef<number | null>(null)
  const aliveRef = useRef(true)

  const clearTimer = useCallback(() => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }, [])

  /** 페이지를 떠날 때 임시 데이터 삭제를 요청한다. */
  useEffect(() => {
    // **재마운트마다 다시 켠다.** React 는 개발 모드에서 마운트 -> 언마운트 ->
    // 재마운트 하는데, 정리 함수가 이 값을 false 로 바꾸고 되돌리지 않으면
    // 이후 모든 동작이 조용히 중단된다. 업로드는 성공하는데 폴링이 시작되지
    // 않아 화면이 첫 단계에 멈춘다. 오류가 나지 않으므로 원인을 찾기 어렵다.
    aliveRef.current = true

    const onUnload = () => {
      if (jobIdRef.current) requestDeletionOnUnload(jobIdRef.current)
    }
    window.addEventListener('pagehide', onUnload)
    return () => {
      window.removeEventListener('pagehide', onUnload)
      aliveRef.current = false
      clearTimer()
      if (jobIdRef.current) requestDeletionOnUnload(jobIdRef.current)
    }
  }, [clearTimer])

  const poll = useCallback(
    async (jobId: string) => {
      if (!aliveRef.current) return

      try {
        const status = await getStatus(jobId)
        if (!aliveRef.current) return

        if (status.status === 'done') {
          const result = await getResult(jobId)
          if (!aliveRef.current) return
          setState({
            phase: 'done',
            stage: null,
            result,
            error: null,
            expiresAt: result.expiresAt,
          })
          return
        }

        if (status.status === 'failed') {
          setState((prev) => ({
            ...prev,
            phase: 'failed',
            stage: null,
            error: status.error ?? toErrorBody(null),
          }))
          return
        }

        setState((prev) => ({
          ...prev,
          phase: 'running',
          stage: status.stage,
          expiresAt: status.expiresAt,
        }))

        const wait = (status.pollAfterSeconds ?? FALLBACK_POLL_SECONDS) * 1000
        timerRef.current = window.setTimeout(() => void poll(jobId), wait)
      } catch (error) {
        if (!aliveRef.current) return
        setState((prev) => ({
          ...prev,
          phase: 'failed',
          stage: null,
          error: toErrorBody(error),
        }))
      }
    },
    [],
  )

  const start = useCallback(
    async (files: File[]) => {
      clearTimer()
      setState({ ...INITIAL, phase: 'uploading' })

      try {
        const created = await createAnalysis(files)
        if (!aliveRef.current) return

        jobIdRef.current = created.jobId
        setState((prev) => ({
          ...prev,
          phase: 'running',
          expiresAt: created.expiresAt,
        }))

        timerRef.current = window.setTimeout(
          () => void poll(created.jobId),
          created.pollAfterSeconds * 1000,
        )
      } catch (error) {
        if (!aliveRef.current) return
        setState({ ...INITIAL, phase: 'failed', error: toErrorBody(error) })
      }
    },
    [clearTimer, poll],
  )

  /** 결과를 확인하고 나면 서버에서 지운다. TTL을 기다리지 않는다. */
  const finish = useCallback(async () => {
    clearTimer()
    const jobId = jobIdRef.current
    jobIdRef.current = null
    setState(INITIAL)
    if (jobId) {
      await deleteAnalysis(jobId).catch(() => undefined)
    }
  }, [clearTimer])

  const reset = useCallback(() => {
    void finish()
  }, [finish])

  return { ...state, start, reset }
}
