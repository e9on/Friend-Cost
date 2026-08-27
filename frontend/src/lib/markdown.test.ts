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

    expect(nodes[0]).toMatchObject({
      kind: 'table',
      head: ['가', '나'],
      rows: [['1', '2']],
    })
  })

  it('구분선만 있는 행을 내용으로 넣지 않는다', () => {
    const nodes = renderMarkdown('| 가 |\n| --- |\n| 1 |')

    expect((nodes[0] as { rows: string[][] }).rows).toEqual([['1']])
  })

  it('글머리 목록을 묶는다', () => {
    const nodes = renderMarkdown('- 하나\n- 둘')

    expect(nodes[0]).toMatchObject({ kind: 'list', ordered: false, items: ['하나', '둘'] })
  })

  it('번호 목록을 묶는다', () => {
    const nodes = renderMarkdown('1. 하나\n2. 둘')

    expect(nodes[0]).toMatchObject({ kind: 'list', ordered: true, items: ['하나', '둘'] })
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
