/**
 * 백엔드 API 클라이언트.
 *
 * `mdfiles/API-명세.md` 의 엔드포인트 5종만 다룬다.
 * 결과 다운로드 엔드포인트는 없다. 결과 이미지는 브라우저가 직접 그린다.
 */

import type {
  AnalysisResult,
  CreateResponse,
  ErrorBody,
  StatusResponse,
} from './types'

const BASE = import.meta.env.VITE_API_BASE ?? '/v1'

/** 서버가 돌려준 오류를 그대로 담는다. 화면은 `code` 로 분기한다. */
export class ApiError extends Error {
  readonly code: string
  readonly retryable: boolean
  readonly status: number

  constructor(status: number, body: ErrorBody) {
    super(body.message)
    this.name = 'ApiError'
    this.code = body.code
    this.retryable = body.retryable
    this.status = status
  }
}

const NETWORK_ERROR: ErrorBody = {
  code: 'NETWORK_ERROR',
  message: '서버에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.',
  retryable: true,
}

async function parse<T>(response: Response): Promise<T> {
  if (response.status === 204) {
    return undefined as T
  }

  let body: unknown
  try {
    body = await response.json()
  } catch {
    if (response.ok) return undefined as T
    throw new ApiError(response.status, NETWORK_ERROR)
  }

  if (!response.ok) {
    const error = (body as { error?: ErrorBody }).error
    throw new ApiError(response.status, error ?? NETWORK_ERROR)
  }
  return body as T
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE}${path}`, init)
  } catch {
    // 네트워크 자체가 끊긴 경우다. 서버 오류와 구분해서 안내한다
    throw new ApiError(0, NETWORK_ERROR)
  }
  return parse<T>(response)
}

export async function createAnalysis(files: File[]): Promise<CreateResponse> {
  const form = new FormData()
  for (const file of files) {
    form.append('images', file, file.name)
  }
  return request<CreateResponse>('/analyses', { method: 'POST', body: form })
}

export async function getStatus(jobId: string): Promise<StatusResponse> {
  return request<StatusResponse>(`/analyses/${jobId}`)
}

export async function getResult(jobId: string): Promise<AnalysisResult> {
  return request<AnalysisResult>(`/analyses/${jobId}/result`)
}

export async function deleteAnalysis(jobId: string): Promise<void> {
  await request<void>(`/analyses/${jobId}`, { method: 'DELETE' })
}

/**
 * 페이지를 떠날 때 삭제를 요청한다.
 *
 * `sendBeacon` 은 POST만 보낼 수 있어서 서버가 별도 경로를 열어 두었다.
 * 이 호출은 실패해도 상관없다. 도달하지 못하면 서버의 TTL이 대신 지운다.
 */
export function requestDeletionOnUnload(jobId: string): void {
  const url = `${BASE}/analyses/${jobId}/deletion`
  if (navigator.sendBeacon) {
    navigator.sendBeacon(url, new Blob([], { type: 'text/plain' }))
    return
  }
  void fetch(url, { method: 'POST', keepalive: true }).catch(() => undefined)
}
