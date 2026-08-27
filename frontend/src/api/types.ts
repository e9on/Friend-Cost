/**
 * 서버와 주고받는 데이터 구조.
 *
 * `mdfiles/데이터-계약-명세.md` 를 그대로 옮긴 것이다.
 * 필드를 여기서 새로 정의하지 않는다. 구조가 바뀌면 그 문서를 먼저 고친다.
 */

export type JobStatus = 'pending' | 'processing' | 'done' | 'failed' | 'expired'

export type JobStage = 'ocr' | 'parsing' | 'analyzing' | 'scoring' | 'reporting'

export interface ErrorBody {
  code: string
  message: string
  retryable: boolean
}

export interface ErrorResponse {
  error: ErrorBody
}

export interface CreateResponse {
  jobId: string
  status: JobStatus
  expiresAt: number
  pollAfterSeconds: number
}

export interface StatusResponse {
  jobId: string
  status: JobStatus
  stage: JobStage | null
  expiresAt: number
  pollAfterSeconds: number | null
  error: ErrorBody | null
}

export interface ReplySeconds {
  me: number | null
  peer: number | null
}

export interface RelationshipScoreData {
  friendFee: number
  intimacy: number
  breakupRisk: number
  firstContactRatio: number
  avgReplySeconds: ReplySeconds
  contactBalance: number
}

export interface ReportSection {
  title: string
  body: string
}

export interface ReportData {
  headline: string
  summary: string
  sections: ReportSection[]
  advice: string
  disclaimer: string
}

export interface ResultMeta {
  messageCount: number
  imageCount: number
  sampled: boolean
  spanSeconds: number | null
}

export interface AnalysisResult {
  jobId: string
  scores: RelationshipScoreData
  report: ReportData
  meta: ResultMeta
  expiresAt: number
}

/** 분석 단계별 안내 문구. 사용자는 이 문구로 진행 상황을 읽는다. */
export const STAGE_LABELS: Record<JobStage, string> = {
  ocr: '대화를 읽는 중',
  parsing: '메시지를 정리하는 중',
  analyzing: '관계를 살펴보는 중',
  scoring: '점수를 계산하는 중',
  reporting: '리포트를 쓰는 중',
}

/** 진행률 표시용 가중치. 실제 소요 시간 비중에 맞춘 어림값이다. */
export const STAGE_PROGRESS: Record<JobStage, number> = {
  ocr: 20,
  parsing: 35,
  analyzing: 60,
  scoring: 75,
  reporting: 90,
}
