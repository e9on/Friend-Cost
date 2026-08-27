/**
 * 최소 마크다운 렌더러.
 *
 * 법률 문서 두 개(`legal/*.md`)를 앱 안에서 보여주기 위한 것이다.
 *
 * 라이브러리를 쓰지 않는 이유는 두 문서가 쓰는 문법이 **제목·표·목록·굵게·
 * 인용** 다섯 가지뿐이기 때문이다. 결과 카드를 DOM 캡처 라이브러리 없이
 * 직접 그린 것과 같은 판단이다.
 *
 * **다루는 문법을 늘리지 않는다.** 늘리기 시작하면 라이브러리를 쓰는 편이
 * 낫고, 그 판단은 그때 다시 한다.
 */

export interface Part {
  bold: boolean
  text: string
}

export type Node =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'paragraph'; parts: Part[] }
  | { kind: 'quote'; parts: Part[] }
  | { kind: 'list'; ordered: boolean; items: string[] }
  | { kind: 'table'; head: string[]; rows: string[][] }

const HEADING = /^(#{1,6})\s+(.*)$/
const BULLET = /^[-*]\s+(.*)$/
const NUMBERED = /^\d+\.\s+(.*)$/
const DIVIDER = /^\|?[\s:|-]+\|[\s:|-]*$/

/** `**굵게**` 를 조각으로 나눈다. 별표 두 개만 다룬다. */
export function splitBold(text: string): Part[] {
  const parts: Part[] = []
  for (const chunk of text.split(/(\*\*[^*]+\*\*)/)) {
    if (!chunk) continue
    const bold = chunk.startsWith('**') && chunk.endsWith('**')
    parts.push({ bold, text: bold ? chunk.slice(2, -2) : chunk })
  }
  return parts
}

function cells(line: string): string[] {
  return line
    .replace(/^\|/, '')
    .replace(/\|$/, '')
    .split('|')
    .map((cell) => cell.trim())
}

export function renderMarkdown(source: string): Node[] {
  const lines = source.split('\n')
  const nodes: Node[] = []
  let index = 0

  while (index < lines.length) {
    const line = lines[index]
    const trimmed = line.trim()

    if (!trimmed || /^-{3,}$/.test(trimmed)) {
      index += 1
      continue
    }

    const heading = HEADING.exec(trimmed)
    if (heading) {
      nodes.push({ kind: 'heading', level: heading[1].length, text: heading[2].trim() })
      index += 1
      continue
    }

    if (trimmed.startsWith('|')) {
      const table: string[][] = []
      while (index < lines.length && lines[index].trim().startsWith('|')) {
        const row = lines[index].trim()
        // 구분선(| --- |)은 내용이 아니다
        if (!DIVIDER.test(row)) table.push(cells(row))
        index += 1
      }
      if (table.length) {
        nodes.push({ kind: 'table', head: table[0], rows: table.slice(1) })
      }
      continue
    }

    if (BULLET.test(trimmed) || NUMBERED.test(trimmed)) {
      const ordered = NUMBERED.test(trimmed)
      const pattern = ordered ? NUMBERED : BULLET
      const items: string[] = []
      while (index < lines.length) {
        const match = pattern.exec(lines[index].trim())
        if (!match) break
        items.push(match[1].trim())
        index += 1
      }
      nodes.push({ kind: 'list', ordered, items })
      continue
    }

    if (trimmed.startsWith('>')) {
      const collected: string[] = []
      while (index < lines.length && lines[index].trim().startsWith('>')) {
        collected.push(lines[index].trim().replace(/^>\s?/, ''))
        index += 1
      }
      nodes.push({ kind: 'quote', parts: splitBold(collected.join(' ').trim()) })
      continue
    }

    // 그 밖은 문단. 빈 줄을 만날 때까지 이어 붙인다
    const collected: string[] = []
    while (index < lines.length && lines[index].trim() && !lines[index].trim().startsWith('|')) {
      collected.push(lines[index].trim())
      index += 1
    }
    nodes.push({ kind: 'paragraph', parts: splitBold(collected.join(' ')) })
  }

  return nodes
}
