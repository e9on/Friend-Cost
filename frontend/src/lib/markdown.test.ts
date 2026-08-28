/**
 * 최소 마크다운 렌더러.
 *
 * 법률 문서 두 개를 앱 안에서 보여주기 위한 것이다. 라이브러리를 쓰지 않는
 * 이유는 두 문서가 쓰는 문법이 다섯 가지뿐이기 때문이다. 결과 카드를 DOM
 * 캡처 라이브러리 없이 직접 그린 것과 같은 판단이다.
 *
 * **다루는 문법을 늘리지 않는다.** 늘리기 시작하면 라이브러리를 쓰는 편이
 * 낫고, 그 판단은 그때 다시 한다.
 */

import { describe, expect, it } from 'vitest'

import type { Part } from './markdown'
import { renderMarkdown } from './markdown'

describe('renderMarkdown', () => {
  it('제목을 단계에 맞게 옮긴다', () => {
    const nodes = renderMarkdown('# 큰제목\n\n## 중간제목')

    expect(nodes[0]).toMatchObject({ kind: 'heading', level: 1, text: '큰제목' })
    expect(nodes[1]).toMatchObject({ kind: 'heading', level: 2, text: '중간제목' })
  })

  it('문단을 옮긴다', () => {
    const nodes = renderMarkdown('첫 문단입니다.')

    expect(nodes[0]).toMatchObject({ kind: 'paragraph' })
  })

  it('표를 머리와 몸으로 나눈다', () => {
    const nodes = renderMarkdown('| 가 | 나 |\n| --- | --- |\n| 1 | 2 |')

    const table = nodes[0] as { kind: string; head: { parts: Part[] }[]; rows: { parts: Part[] }[][] }

    expect(table.kind).toBe('table')
    expect(table.head.map((c) => c.parts[0].text)).toEqual(['가', '나'])
    expect(table.rows.map((row) => row.map((c) => c.parts[0].text))).toEqual([['1', '2']])
  })

  it('구분선만 있는 행을 내용으로 넣지 않는다', () => {
    const nodes = renderMarkdown('| 가 |\n| --- |\n| 1 |')

    const rows = (nodes[0] as { rows: { parts: Part[] }[][] }).rows

    expect(rows.map((row) => row.map((c) => c.parts[0].text))).toEqual([['1']])
  })

  it('글머리 목록을 묶는다', () => {
    const nodes = renderMarkdown('- 하나\n- 둘')

    const list = nodes[0] as { kind: string; ordered: boolean; items: { parts: Part[] }[] }

    expect(list).toMatchObject({ kind: 'list', ordered: false })
    expect(list.items.map((item) => item.parts[0].text)).toEqual(['하나', '둘'])
  })

  it('번호 목록을 묶는다', () => {
    const nodes = renderMarkdown('1. 하나\n2. 둘')

    const list = nodes[0] as { kind: string; ordered: boolean; items: { parts: Part[] }[] }

    expect(list).toMatchObject({ kind: 'list', ordered: true })
    expect(list.items.map((item) => item.parts[0].text)).toEqual(['하나', '둘'])
  })

  it('굵게를 조각으로 나눈다', () => {
    const nodes = renderMarkdown('보통 **굵게** 보통')

    expect((nodes[0] as { parts: unknown[] }).parts).toEqual([
      { bold: false, text: '보통 ' },
      { bold: true, text: '굵게' },
      { bold: false, text: ' 보통' },
    ])
  })

  it('인용을 옮긴다', () => {
    const nodes = renderMarkdown('> 이 문서는 초안이다')

    expect(nodes[0]).toMatchObject({ kind: 'quote' })
  })

  it('수평선을 버린다', () => {
    // 문서 상단의 --- 는 화면에서 의미가 없다
    expect(renderMarkdown('---')).toEqual([])
  })

  it('빈 입력에도 터지지 않는다', () => {
    expect(renderMarkdown('')).toEqual([])
  })
})

describe('굵게는 어디서나 처리된다', () => {
  it('표 칸 안에서도', () => {
    // 법률 문서는 표 안에서 "**초안. 법률 검토를 받지 않았다.**" 처럼 쓴다.
    // 처리하지 않으면 별표가 그대로 화면에 보인다
    const nodes = renderMarkdown(['| 상태 |', '| --- |', '| **초안** |'].join('\n'))
    const table = nodes[0] as { rows: { parts: unknown[] }[][] }

    expect(table.rows[0][0].parts).toEqual([{ bold: true, text: '초안' }])
  })

  it('목록 항목 안에서도', () => {
    const nodes = renderMarkdown('- **본인이 참여한 대화만** 올린다')
    const list = nodes[0] as { items: { parts: unknown[] }[] }

    expect(list.items[0].parts).toEqual([
      { bold: true, text: '본인이 참여한 대화만' },
      { bold: false, text: ' 올린다' },
    ])
  })

  it('표 머리에서도', () => {
    const nodes = renderMarkdown(['| **항목** |', '| --- |', '| 값 |'].join('\n'))
    const table = nodes[0] as { head: { parts: unknown[] }[] }

    expect(table.head[0].parts).toEqual([{ bold: true, text: '항목' }])
  })
})
