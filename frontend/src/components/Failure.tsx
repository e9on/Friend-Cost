/**
 * 실패 화면.
 *
 * 서버가 준 `code` 로 안내를 고른다. 원인마다 사용자가 할 수 있는 일이
 * 다르기 때문이다. 대화가 짧아서 실패한 사람에게 "다시 시도"를 권하면
 * 같은 결과가 반복될 뿐이다.
 */

import type { ErrorBody } from '../api/types'

interface Props {
  error: ErrorBody
  onRestart: () => void
}

interface Guide {
  title: string
  hint: string
  retry: boolean
}

const GUIDES: Record<string, Guide> = {
  TOO_FEW_MESSAGES: {
    title: '대화가 너무 짧아요',
    hint: '메시지가 15개는 넘어야 의미 있는 결과가 나와요. 캡처를 더 올려주세요.',
    retry: false,
  },
  NO_CONVERSATION_FOUND: {
    title: '대화를 찾지 못했어요',
    hint: '말풍선이 잘 보이는 대화 화면을 캡처해 주세요. 한쪽만 말한 대화도 분석할 수 없어요.',
    retry: false,
  },
  GROUP_CHAT_DETECTED: {
    title: '단체방은 분석할 수 없어요',
    hint: '지금은 1:1 대화만 지원해요.',
    retry: false,
  },
  SPEAKER_DETECTION_FAILED: {
    title: '누가 보낸 말인지 구분하지 못했어요',
    hint: '말풍선이 좌우로 나뉘어 보이는 원본 캡처를 올려주세요. 잘라내거나 확대한 이미지는 어려워요.',
    retry: false,
  },
  IMAGE_FORMAT_UNSUPPORTED: {
    title: '읽을 수 없는 이미지예요',
    hint: 'PNG, JPG, WEBP 파일만 올릴 수 있어요. 너무 작은 이미지도 글자를 읽기 어려워요.',
    retry: false,
  },
  IMAGE_TOO_LARGE: {
    title: '이미지가 너무 커요',
    hint: '한 장에 5MB, 전체 20MB까지 올릴 수 있어요.',
    retry: false,
  },
  IMAGE_TOO_MANY: {
    title: '이미지 수가 맞지 않아요',
    hint: '1장에서 10장까지 올릴 수 있어요.',
    retry: false,
  },
  RATE_LIMITED: {
    title: '조금 쉬었다 해주세요',
    hint: '요청이 너무 잦아요. 잠시 후 다시 시도해 주세요.',
    retry: true,
  },
  DAILY_LIMIT_EXCEEDED: {
    title: '오늘은 여기까지예요',
    hint: '하루에 분석할 수 있는 횟수를 모두 썼어요. 내일 다시 만나요.',
    retry: false,
  },
  CONCURRENCY_LIMIT: {
    title: '이미 분석이 돌고 있어요',
    hint: '앞선 분석이 끝나면 다시 시도해 주세요.',
    retry: true,
  },
  JOB_EXPIRED: {
    title: '결과가 만료되었어요',
    hint: '임시 데이터는 20분 뒤 자동으로 지워져요. 다시 분석해 주세요.',
    retry: false,
  },
  ANALYSIS_TIMEOUT: {
    title: '분석이 너무 오래 걸렸어요',
    hint: '캡처를 조금 줄여서 다시 시도해 주세요.',
    retry: true,
  },
  NETWORK_ERROR: {
    title: '서버에 연결하지 못했어요',
    hint: '네트워크 상태를 확인하고 다시 시도해 주세요.',
    retry: true,
  },
}

const FALLBACK: Guide = {
  title: '분석에 실패했어요',
  hint: '잠시 후 다시 시도해 주세요.',
  retry: true,
}

export function Failure({ error, onRestart }: Props) {
  const guide = GUIDES[error.code] ?? { ...FALLBACK, retry: error.retryable }

  return (
    <section className="panel center">
      <div className="failure-icon" aria-hidden>
        😥
      </div>
      <h2 className="headline">{guide.title}</h2>
      <p className="summary">{guide.hint}</p>

      <button type="button" className="cta" onClick={onRestart}>
        {guide.retry ? '다시 시도하기' : '처음으로'}
      </button>

      <p className="error-code">오류 코드: {error.code}</p>
    </section>
  )
}
