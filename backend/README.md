# 친구비 측정기 — 백엔드

메신저 1:1 대화 캡처를 분석해 관계 지표와 리포트를 만드는 API 서버.

명세는 저장소 루트의 [`mdfiles/`](../mdfiles)에 있다. **코드보다 문서가 먼저다.** 구조나 필드를 바꿀 때는 `데이터-계약-명세.md`를 먼저 고친다.

## 현재 상태

| 계층 | 상태 |
| --- | --- |
| 도메인 모델 | 완료 |
| 관계 점수 알고리즘 | 완료 |
| Conversation Parser | 완료 |
| AI Agent / Validator | 완료 (**기본값은 스텁**) |
| 저장소 | 완료 (인메모리) |
| API | 완료 |
| Frontend | 완료 (React) |

**실제 LLM과 OCR 엔진은 기본값이 스텁이다.** 성능 평가 후에 연결할 예정이라, 그 자리에 결정론적 가짜가 들어 있다. 스텁으로도 업로드부터 결과 조회까지 전 구간이 동작한다.

`GET /health` 의 `llmProvider`, `ocrEngine` 이 `stub` 이면 아직 가짜다.

실제 구현은 이미 들어 있다. 설정만 바꾸면 붙는다.

| 구분 | 사용 가능한 값 |
| --- | --- |
| `FC_LLM_PROVIDER` | `stub` · `anthropic` · `groq` · `deepseek` · `together` · `openrouter` |
| `FC_OCR_ENGINE` | `stub` · `google_vision` |

후보 조사와 선정 근거는 [`mdfiles/AI-모델-선정-보고서.md`](../mdfiles/AI-모델-선정-보고서.md)에 있다.

> **무료 티어라고 다 쓸 수 있는 것이 아니다.** Gemini와 Mistral의 무료 티어는 입력을 학습에 쓰고 사람이 검토할 수 있다. 우리는 사용자 본인이 아니라 **대화 상대방의 사적 메시지**를 다루므로 쓸 수 없다. Groq은 무료·유료 모두 학습에 쓰지 않는다고 명시한다.

## 모델 실측

후보를 가격순으로 고르지 않는다. 같은 대화를 넣어보고 고른다.

```bash
.venv/Scripts/python.exe tools/evaluate_llm.py --provider stub --count 8 --repeat 3
.venv/Scripts/python.exe tools/evaluate_llm.py --provider groq --model llama-3.3-70b-versatile --key $GROQ_KEY
.venv/Scripts/python.exe tools/evaluate_llm.py --provider anthropic --model claude-haiku-4-5 --key $ANTHROPIC_KEY
```

실제 카카오톡 캡처가 있으면 `--fixtures` 로 `OcrPage` JSON 디렉터리를 넘긴다. 없으면 합성 대화로 돈다.

가장 중요한 지표는 정확도가 아니라 **결과 분산**이다. 스키마를 지키고 문장이 매끄러워도, 어떤 대화를 넣든 친밀도가 60~70으로만 나온다면 그 모델은 관계를 읽지 못하는 것이다. 그런 결과는 오류로 드러나지 않고, 사용자는 그것이 자기 관계를 반영한다고 믿는다.

## 실행

```bash
cd backend
py -3.10 -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[dev]"     # Windows
# source .venv/bin/activate && pip install -e ".[dev]"  # macOS / Linux

.venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

- 문서: http://127.0.0.1:8000/docs
- 상태: http://127.0.0.1:8000/health

Python은 **3.10 고정**이다. `pyproject.toml` 이 `>=3.10,<3.11` 로 잠가 두었다.

## 테스트

```bash
.venv/Scripts/python.exe -m pytest                          # 전체
.venv/Scripts/python.exe -m pytest tests/test_docs_consistency.py -v   # 문서·코드 일치
```

핵심 로직은 테스트를 먼저 쓰고 구현했다. `관계-점수-계산-규칙.md` 13장의 손계산 예제가 그대로 회귀 테스트 고정값이다. **문서의 숫자와 테스트의 숫자가 어긋나면 둘 중 하나가 틀린 것이다.**

## 구조

기준 명세 10장을 그대로 따른다.

```text
app
├── api             HTTP 경로, 요청 제한, 응답 스키마
├── application     업로드 검증, 파이프라인, 작업 수명주기
├── domain          데이터 계약을 옮긴 모델과 열거값
├── ai              Parser, Agent, Prompt, Provider, Validator
├── algorithm       점수 산식과 가중치 (LLM 미사용)
├── infrastructure  OCR 엔진, 저장소
├── common          오류 코드, 수치 유틸
└── config          설정
```

의존 방향은 `api → application → {ai, algorithm} → domain` 이다. `domain` 은 아무것도 import 하지 않는다.

## 실제 모델을 붙일 때

교체 지점은 두 곳뿐이다.

**LLM** — Anthropic과 OpenAI 호환 후보(Groq 등)는 이미 구현되어 있다. `FC_LLM_PROVIDER`, `FC_LLM_MODEL`, `FC_LLM_API_KEY` 만 채우면 된다. 새 후보를 추가할 때는 `app/ai/provider/` 에 구현을 넣고 `_build_llm_provider` 에 분기를 더한다.

OpenAI 호환 스펙을 따르는 곳은 구현 하나로 모두 덮으므로, 대부분 설정만 바뀐다.

Provider는 전송만 한다. 프롬프트는 `app/ai/prompt/`, 응답 검증은 `app/ai/validator/` 소관이므로 건드릴 필요가 없다.

**OCR** — Google Cloud Vision이 구현되어 있다. `FC_OCR_ENGINE=google_vision` 과 `FC_OCR_API_KEY` 를 설정한다.

> OCR 엔진은 **텍스트와 함께 bounding box 좌표, 그리고 이미지 크기를 반환해야 한다.** 화자 판별이 좌우 여백 비교에 의존하기 때문이다. 좌표를 주지 않는 엔진은 비용이 낮아도 쓸 수 없다. 자세한 내용은 `OCR-Parser-명세.md` 2장.

비교 기준은 `tests/fixtures/kakao.py` 의 합성 픽스처다. 실제 엔진의 출력이 이 픽스처와 같은 성질(좌우 정렬, 시각 라벨 위치)을 가지면 Parser가 그대로 동작한다.

## 설정

환경변수 접두사는 `FC_` 다. 전체 목록은 `app/config/settings.py`.

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `FC_TTL_SECONDS` | 1200 | 임시 데이터 수명 (20분, 생성 시점 고정) |
| `FC_MAX_IMAGES` | 10 | 이미지 개수 상한 |
| `FC_MAX_MESSAGES` | 120 | 초과 시 샘플링 |
| `FC_RATE_LIMIT_PER_MINUTE` | 5 | IP당 분석 생성 |
| `FC_DAILY_ANALYSIS_LIMIT` | 10 | IP당 일일 분석 |
| `FC_TOTAL_TIMEOUT_SECONDS` | 180 | 분석 전체 제한 |
| `FC_LLM_PROVIDER` | stub | 교체 지점 |
| `FC_OCR_ENGINE` | stub | 교체 지점 |

## 배포 시 주의

**단일 워커로 띄워야 한다.** 작업 상태와 요청 제한 카운터가 프로세스 메모리에 있어서, 워커나 인스턴스를 늘리면 상태가 갈라진다.

인스턴스를 늘려야 할 시점이 오면 `app/infrastructure/storage/base.py` 의 인터페이스를 외부 저장소 구현으로 갈아 끼운다. 기준 명세 6장이 이 전제와 한계를 적어두었다.

CORS 허용 Origin은 기본값이 비어 있다. `FC_CORS_ORIGINS` 로 프론트 도메인을 넣는다. 와일드카드는 값 검증에서 거부한다.

Cloud Run 배포는 [`deploy/cloudrun.md`](deploy/cloudrun.md) 참조.

## 남은 일

- **실제 캡처로 OCR·LLM 실측** — 후보와 절차는 `AI-모델-선정-보고서.md` 8장
- Naver CLOVA OCR 엔진 (Vision 정확도가 부족할 때의 대안)
- AI 프롬프트 명세, Frontend 명세, 법적 고지 문서
- 외부 TTL 저장소 구현 (인스턴스를 늘릴 시점에)
