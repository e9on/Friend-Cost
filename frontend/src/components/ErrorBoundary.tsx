/**
 * 렌더링 중 터진 오류를 받아낸다.
 *
 * 이게 없으면 컴포넌트 하나가 던졌을 때 화면이 통째로 하얘진다.
 * 사용자는 무슨 일이 일어났는지 알 수 없고, 서버에 올려둔 분석이
 * 남아 있는지도 알 수 없다.
 *
 * 여기서 원인을 자세히 보여주지 않는 이유는, 오류 메시지에 대화 내용이
 * 섞여 나올 수 있기 때문이다. 사용자에게는 다시 시작할 길만 준다.
 */

import { Component } from 'react'
import type { ErrorInfo, ReactNode } from 'react'

interface Props {
  children: ReactNode
}

interface State {
  crashed: boolean
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { crashed: false }

  static getDerivedStateFromError(): State {
    return { crashed: true }
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 개발 중에만 자세히 남긴다. 배포에서는 콘솔에 대화가 남을 수 있다
    if (import.meta.env.DEV) {
      console.error('렌더링 오류', error, info.componentStack)
    }
  }

  render() {
    if (!this.state.crashed) return this.props.children

    return (
      <section className="panel center">
        <div className="failure-icon" aria-hidden>
          😵
        </div>
        <h2 className="headline">화면을 그리지 못했어요</h2>
        <p className="summary">
          새로고침하면 처음부터 다시 시작할 수 있어요. 올렸던 이미지는 서버에서
          이미 지워졌거나 5분 뒤 자동으로 사라집니다.
        </p>
        <button
          type="button"
          className="cta"
          onClick={() => window.location.reload()}
        >
          새로고침
        </button>
      </section>
    )
  }
}
