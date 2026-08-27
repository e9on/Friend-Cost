/**
 * 약관·처리방침 전문 모달.
 *
 * 앱 밖으로 내보내지 않는다. 휴대폰에서 돌아오지 못하는 사용자가 생기고,
 * 문서가 두 벌이 되면 한쪽만 고쳐진다. `legal/` 이 단일 원본이다.
 *
 * `Frontend-명세.md` 2.1
 */

import privacy from '@legal/개인정보-처리방침.md?raw'
import terms from '@legal/이용약관.md?raw'

import type { Node, Part } from '../lib/markdown'
import { renderMarkdown } from '../lib/markdown'

export type LegalDoc = 'terms' | 'privacy'

const SOURCE: Record<LegalDoc, string> = { terms, privacy }
const TITLE: Record<LegalDoc, string> = {
  terms: '이용약관',
  privacy: '개인정보 처리방침',
}

function Text({ parts }: { parts: Part[] }) {
  return (
    <>
      {parts.map((part, index) =>
        part.bold ? <strong key={index}>{part.text}</strong> : <span key={index}>{part.text}</span>,
      )}
    </>
  )
}

function Block({ node }: { node: Node }) {
  if (node.kind === 'heading') {
    const level = Math.min(node.level + 1, 6)
    const Tag = `h${level}` as 'h2'
    return <Tag>{node.text}</Tag>
  }
  if (node.kind === 'paragraph') return <p><Text parts={node.parts} /></p>
  if (node.kind === 'quote') return <blockquote><Text parts={node.parts} /></blockquote>
  if (node.kind === 'list') {
    const items = node.items.map((item, index) => (
      <li key={index}>
        <Text parts={[{ bold: false, text: item }]} />
      </li>
    ))
    return node.ordered ? <ol>{items}</ol> : <ul>{items}</ul>
  }
  return (
    <div className="legal-table">
      <table>
        <thead>
          <tr>
            {node.head.map((cell, index) => (
              <th key={index}>{cell}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {node.rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {row.map((cell, index) => (
                <td key={index}>{cell}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function LegalModal({ doc, onClose }: { doc: LegalDoc; onClose: () => void }) {
  const nodes = renderMarkdown(SOURCE[doc])

  return (
    <div className="modal-backdrop" role="dialog" aria-modal="true" aria-label={TITLE[doc]}>
      <div className="modal modal-legal">
        <header className="modal-head">
          <h2>{TITLE[doc]}</h2>
          <button type="button" className="ghost modal-close" onClick={onClose}>
            닫기
          </button>
        </header>
        <div className="legal-body">
          {nodes.map((node, index) => (
            <Block key={index} node={node} />
          ))}
        </div>
      </div>
    </div>
  )
}
