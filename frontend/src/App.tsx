/**
 * 화면 전환.
 *
 * 사용자 흐름은 기준 명세 4장 그대로다.
 * 업로드 -> 분석 -> 결과 -> 임시 데이터 삭제.
 */

import { ConsentGate } from './components/ConsentGate'
import { Failure } from './components/Failure'
import { Progress } from './components/Progress'
import { Result } from './components/Result'
import { Uploader } from './components/Uploader'
import { useAnalysis } from './hooks/useAnalysis'

export default function App() {
  const { phase, stage, result, error, start, reset } = useAnalysis()

  // 동의를 받기 전에는 어떤 화면도 보여주지 않는다. 개보법 제22조는 동의를
  // 구분해 각각 받으라고 하고, 그 앞에 서비스를 쓰게 두면 동의가 사후가 된다
  return (
    <ConsentGate>
      <main className="shell">
        {phase === 'idle' && <Uploader onStart={start} busy={false} />}

        {(phase === 'uploading' || phase === 'running') && (
          <Progress stage={stage} phase={phase} />
        )}

        {phase === 'done' && result && <Result result={result} onRestart={reset} />}

        {phase === 'failed' && error && <Failure error={error} onRestart={reset} />}

        <footer className="foot">
          본인이 참여한 대화만 올려주세요. 재미로 보는 결과입니다.
        </footer>
      </main>
    </ConsentGate>
  )
}
