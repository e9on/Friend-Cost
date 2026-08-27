/**
 * 결과 카드 이미지를 브라우저에서 직접 그린다.
 *
 * 기준 명세 11장: 결과 다운로드 엔드포인트는 두지 않는다.
 * 서버가 파일을 만들면 임시 파일이 하나 더 생겨 삭제 정책이 복잡해지고
 * 렌더링 비용도 서버가 진다.
 *
 * DOM을 캡처하는 라이브러리 대신 캔버스에 직접 그리는 이유는, 의존성 없이
 * 결과물이 어느 브라우저에서나 똑같이 나오기 때문이다. 폰트 로딩이나 CSS
 * 해석 차이로 이미지가 깨지는 일도 없다.
 */

import type { AnalysisResult } from '../api/types'
import {
  formatDuration,
  formatFee,
  formatPercent,
} from './format'

const WIDTH = 1080
const PADDING = 72
const BG = '#12121a'
const CARD = '#1c1c28'
const ACCENT = '#ffd166'
const TEXT = '#f4f4f8'
const MUTED = '#9a9aae'

const FONT_STACK =
  '"Pretendard", "Apple SD Gothic Neo", "Malgun Gothic", system-ui, sans-serif'

function font(size: number, weight = 400): string {
  return `${weight} ${size}px ${FONT_STACK}`
}

/** 주어진 폭 안에서 줄바꿈해 그리고, 그린 뒤 y 좌표를 돌려준다. */
function wrapText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  maxWidth: number,
  lineHeight: number,
): number {
  const words = text.split(' ')
  let line = ''
  let cursor = y

  for (const word of words) {
    const candidate = line ? `${line} ${word}` : word
    if (ctx.measureText(candidate).width > maxWidth && line) {
      ctx.fillText(line, x, cursor)
      cursor += lineHeight
      line = word
    } else {
      line = candidate
    }
  }
  if (line) {
    ctx.fillText(line, x, cursor)
    cursor += lineHeight
  }
  return cursor
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
): void {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
  ctx.fill()
}

interface Metric {
  label: string
  value: string
}

function metricsOf(result: AnalysisResult): Metric[] {
  const { scores } = result
  return [
    { label: '친밀도', value: `${scores.intimacy}` },
    { label: '손절 위험도', value: `${scores.breakupRisk}` },
    { label: '연락 균형도', value: `${scores.contactBalance}` },
    { label: '먼저 연락', value: formatPercent(scores.firstContactRatio) },
    { label: '내 답장', value: formatDuration(scores.avgReplySeconds.me) },
    { label: '상대 답장', value: formatDuration(scores.avgReplySeconds.peer) },
  ]
}

export function drawResultCard(
  canvas: HTMLCanvasElement,
  result: AnalysisResult,
): void {
  const metrics = metricsOf(result)
  const rows = Math.ceil(metrics.length / 2)
  const height = 760 + rows * 132

  canvas.width = WIDTH
  canvas.height = height

  const ctx = canvas.getContext('2d')
  if (!ctx) return

  ctx.fillStyle = BG
  ctx.fillRect(0, 0, WIDTH, height)

  const inner = WIDTH - PADDING * 2
  let y = PADDING + 40

  ctx.fillStyle = MUTED
  ctx.font = font(30, 500)
  ctx.fillText('친구비 측정기', PADDING, y)
  y += 78

  // 친구비를 가장 크게 보여준다. 서비스의 대표 지표다.
  //
  // 방향 문구를 함께 새긴다. 금액만 있으면 누가 누구에게 내는지 알 수 없다.
  // 화면에서는 절댓값만 보여주므로 이미지에도 부호를 붙이지 않는다
  const fee = formatFee(result.scores.friendFee)
  // 화면(.fee-label)과 같은 무게로 새긴다. 흐리게 두면 큰 숫자에 묻혀
  // 누가 누구에게 내는지가 읽히지 않는다
  ctx.fillStyle = TEXT
  ctx.font = font(40, 700)
  ctx.fillText(fee.label, PADDING, y)
  y += 46

  ctx.fillStyle = ACCENT
  ctx.font = font(122, 800)
  ctx.fillText(fee.amount, PADDING, y + 90)
  y += 190

  ctx.fillStyle = TEXT
  ctx.font = font(42, 700)
  y = wrapText(ctx, result.report.headline, PADDING, y, inner, 58)
  y += 24

  ctx.fillStyle = MUTED
  ctx.font = font(30)
  y = wrapText(ctx, result.report.summary, PADDING, y, inner, 46)
  y += 40

  // 지표 격자
  const gap = 24
  const cellW = (inner - gap) / 2
  const cellH = 108

  metrics.forEach((metric, index) => {
    const col = index % 2
    const row = Math.floor(index / 2)
    const x = PADDING + col * (cellW + gap)
    const top = y + row * (cellH + gap)

    ctx.fillStyle = CARD
    roundedRect(ctx, x, top, cellW, cellH, 20)

    ctx.fillStyle = MUTED
    ctx.font = font(26, 500)
    ctx.fillText(metric.label, x + 28, top + 42)

    ctx.fillStyle = TEXT
    ctx.font = font(38, 700)
    ctx.fillText(metric.value, x + 28, top + 86)
  })

  y += rows * (cellH + gap) + 30

  ctx.fillStyle = MUTED
  ctx.font = font(24)
  ctx.fillText(result.report.disclaimer, PADDING, y + 20)
}

/**
 * 캔버스를 PNG 파일로 저장한다.
 *
 * 모바일 브라우저는 `<a download>` 을 무시하는 경우가 있어, 공유 시트를
 * 쓸 수 있으면 그쪽을 먼저 시도한다.
 */
export async function saveCard(
  canvas: HTMLCanvasElement,
  filename = '친구비-결과.png',
): Promise<'shared' | 'downloaded' | 'failed'> {
  const blob = await new Promise<Blob | null>((resolve) =>
    canvas.toBlob(resolve, 'image/png'),
  )
  if (!blob) return 'failed'

  const file = new File([blob], filename, { type: 'image/png' })

  if (navigator.canShare?.({ files: [file] })) {
    try {
      await navigator.share({ files: [file] })
      return 'shared'
    } catch {
      // 사용자가 공유를 취소한 경우다. 저장으로 넘어간다
    }
  }

  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
  return 'downloaded'
}
