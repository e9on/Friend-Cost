# 친구비 측정기 — API 명세서

| 항목 | 값 |
| --- | --- |
| 버전 | v1.3 |
| 최종 수정일 | 2026-08-25 |
| 상위 문서 | `친구비-측정기-서비스-기준-명세.md` |
| 데이터 구조 | `데이터-계약-명세.md` |

## 1. 문서 목적

이 문서는 Frontend와 Backend 사이의 HTTP 인터페이스를 정의한다.

요청·응답 본문에 등장하는 모든 구조체, 상태값, 오류 코드는 `데이터-계약-명세.md`가 정의한 것을 그대로 사용한다. 이 문서에서 새로 정의하지 않는다.

## 2. 공통 규격

| 항목 | 값 |
| --- | --- |
| Base URL | `/v1` |
| 프로토콜 | HTTPS 전용. HTTP 요청은 308로 리다이렉트 |
| 요청 본문 | `multipart/form-data` (업로드) 또는 없음 |
| 응답 본문 | `application/json; charset=utf-8` |
| 인증 | 없음 (비회원 서비스) |
| 시각 표기 | Unix epoch 초 단위 정수 |

`jobId`는 UUID v4이며 **이것이 사실상의 접근 토큰이다.** 별도 인증이 없으므로 `jobId`를 아는 클라이언트만 결과를 조회할 수 있다. 로그, 오류 메시지, 리다이렉트 URL에 `jobId`를 노출하지 않는다.

## 3. 엔드포인트 목록

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| `POST` | `/v1/analyses` | 분석 생성 |
| `GET` | `/v1/analyses/{jobId}` | 상태 조회 |
| `GET` | `/v1/analyses/{jobId}/result` | 결과 조회 |
| `DELETE` | `/v1/analyses/{jobId}` | 임시 데이터 삭제 |
| `POST` | `/v1/analyses/{jobId}/deletion` | 삭제 (beacon 전용) |
| `GET` | `/health` | 상태 확인 |

**결과 다운로드 엔드포인트는 두지 않는다.** 다운로드 이미지는 클라이언트가 결과 데이터로 직접 렌더링한다. 서버가 파일을 만들면 임시 파일이 하나 더 생겨 기준 명세 5장의 삭제 정책과 얽히고, 렌더링 비용도 서버가 부담하게 된다.

## 4. 분석 생성

```http
POST /v1/analyses
Content-Type: multipart/form-data
```

### 요청

| 필드 | 타입 | 제약 |
| --- | --- | --- |
| `images` | file[] | 1 ~ 10개 |

| 제한 | 값 |
| --- | --- |
| 허용 형식 | `image/png`, `image/jpeg`, `image/webp` |
| 개별 파일 크기 | 5 MB |
| 전체 요청 크기 | 20 MB |
| 최소 해상도 | 짧은 변 **320px** |
| 최대 화소 수 | **4천만 화소** (예: 1080×12000 통과, 8000×8000 거절) |

파일은 **확장자가 아니라 매직 넘버로 형식을 검증한다.** 확장자만 바꾼 실행 파일을 걸러내기 위해서다.

해상도는 이미지 헤더에서 직접 읽는다. 이미지 라이브러리를 쓰지 않는 이유는 콜드 스타트가 중요한 배포 형태이기 때문이다. 320px보다 작으면 글자를 읽을 수 없으므로 OCR을 돌리기 전에 거절한다.

**화소 수 상한은 용량 상한과 별개다.** 균일한 색으로 채운 PNG는 33바이트로도 30000×30000을 선언할 수 있다. 용량만 검사하면 그대로 OCR로 넘어가 처리 시간과 과금이 그대로 나간다. 우리가 직접 디코드하지 않으므로 서버가 죽지는 않지만 **비용이 샌다.**

한 변이 아니라 총 화소를 보는 이유는, 변마다 상한을 두면 8000×8000(6400만 화소) 같은 조합을 놓치기 때문이다. 스크롤 캡처는 세로로 길어서 1080×12000(1300만 화소) 정도는 정상 범위다.

형식·해상도·화소 위반은 모두 `IMAGE_FORMAT_UNSUPPORTED`로 응답한다.

이미지 순서는 업로드 순서를 시간 순서로 간주한다(`OCR-Parser-명세.md` 4.4).

### 응답 — 202 Accepted

```json
{
  "jobId": "9f2a7c14-3b8e-4d51-a0c6-7e2f5b91d834",
  "status": "pending",
  "expiresAt": 1755502260,
  "pollAfterSeconds": 2
}
```

| 필드 | 설명 |
| --- | --- |
| `pollAfterSeconds` | 클라이언트가 다음 상태 조회까지 기다릴 권장 시간 |

### 오류

| 상황 | 코드 | HTTP |
| --- | --- | ---: |
| 이미지 0개 또는 10개 초과 | `IMAGE_TOO_MANY` | 400 |
| 개별·전체 용량 초과 | `IMAGE_TOO_LARGE` | 400 |
| 허용되지 않은 형식 | `IMAGE_FORMAT_UNSUPPORTED` | 400 |
| 요청 빈도 초과 | `RATE_LIMITED` | 429 |
| 일일 분석 횟수 초과 | `DAILY_LIMIT_EXCEEDED` | 429 |
| 동시 분석 한도 초과 | `CONCURRENCY_LIMIT` | 429 |

## 5. 상태 조회

```http
GET /v1/analyses/{jobId}
```

분석은 수십 초가 걸릴 수 있으므로 클라이언트는 이 엔드포인트를 폴링한다.

### 응답 — 200 OK

처리 중:

```json
{
  "jobId": "9f2a7c14-3b8e-4d51-a0c6-7e2f5b91d834",
  "status": "processing",
  "stage": "analyzing",
  "expiresAt": 1755502260,
  "pollAfterSeconds": 2
}
```

완료:

```json
{
  "jobId": "9f2a7c14-3b8e-4d51-a0c6-7e2f5b91d834",
  "status": "done",
  "stage": null,
  "expiresAt": 1755502260
}
```

실패:

```json
{
  "jobId": "9f2a7c14-3b8e-4d51-a0c6-7e2f5b91d834",
  "status": "failed",
  "stage": null,
  "expiresAt": 1755502260,
  "error": {
    "code": "TOO_FEW_MESSAGES",
    "message": "분석하기에 대화가 너무 짧습니다.",
    "retryable": false
  }
}
```

`status`가 `failed`여도 HTTP는 **200이다.** 작업 조회 자체는 성공했기 때문이다. 실패 내용은 본문의 `error`로 전달한다.

### 오류

| 상황 | 코드 | HTTP |
| --- | --- | ---: |
| 존재하지 않는 `jobId` | `JOB_NOT_FOUND` | 404 |
| TTL 만료로 삭제됨 | `JOB_EXPIRED` | 410 |

`JOB_NOT_FOUND`와 `JOB_EXPIRED`를 구분해 응답한다. 만료는 사용자에게 "다시 분석해 주세요"로 안내할 수 있지만, 없는 작업은 잘못된 접근이기 때문이다.

## 6. 결과 조회

```http
GET /v1/analyses/{jobId}/result
```

### 응답 — 200 OK

본문은 `데이터-계약-명세.md` 12장의 `AnalysisResult`다.

```json
{
  "jobId": "9f2a7c14-3b8e-4d51-a0c6-7e2f5b91d834",
  "scores": {
    "friendFee": 63000,
    "intimacy": 64,
    "breakupRisk": 38,
    "firstContactRatio": 0.63,
    "avgReplySeconds": { "me": 420, "peer": 1860 },
    "contactBalance": 74,
    "confidence": "high"
  },
  "report": {
    "headline": "서로 챙기지만 균형이 조금 기운 사이",
    "summary": "...",
    "sections": [
      { "title": "연락의 흐름", "body": "..." },
      { "title": "지켜볼 지점", "body": "..." }
    ],
    "advice": "...",
    "disclaimer": "이 결과는 재미를 위한 추정이며 실제 관계를 판단하는 근거가 아닙니다."
  },
  "meta": {
    "messageCount": 184,
    "imageCount": 5,
    "sampled": false,
    "spanSeconds": 1209600
  },
  "expiresAt": 1755502260
}
```

**대화 원문과 `RelationshipAnalysisData`는 응답에 포함하지 않는다.**

`expiresAt`까지는 **몇 번이든 재조회할 수 있다.** 사용자가 결과 화면을 새로고침하거나 잠시 다른 앱에 다녀와도 결과가 유지되어야 하기 때문이다. TTL은 조회로 연장되지 않는다.

### 오류

| 상황 | 코드 | HTTP |
| --- | --- | ---: |
| 아직 완료되지 않음 | `JOB_NOT_READY` | 409 |
| 분석이 실패로 끝남 | 해당 실패 코드 | 422 / 502 |
| 존재하지 않는 `jobId` | `JOB_NOT_FOUND` | 404 |
| TTL 만료 | `JOB_EXPIRED` | 410 |

## 7. 삭제

```http
DELETE /v1/analyses/{jobId}
```

### 응답 — 204 No Content

본문 없음. 이미 삭제되었거나 존재하지 않아도 **204를 반환한다.** 삭제는 멱등이어야 하고, 존재 여부를 알려주면 `jobId` 유효성을 탐지하는 통로가 된다.

### beacon 전용 경로

```http
POST /v1/analyses/{jobId}/deletion
```

브라우저의 `navigator.sendBeacon`은 **POST만 지원한다.** 페이지 이탈 시점에 삭제 요청을 보내려면 이 경로가 필요하다. 동작과 응답은 `DELETE`와 동일하다.

두 경로를 모두 두는 이유는 정석(`DELETE`)과 실제 이탈 처리(`POST` beacon)를 모두 만족시키기 위해서다.

## 8. 삭제 정책과 TTL

```text
정상 이탈 / 결과 확인 완료
  → DELETE 또는 beacon POST
  → 즉시 삭제

브라우저 강제 종료 / 네트워크 단절 / 요청 실패
  → TTL 만료
  → 자동 삭제
```

| 항목 | 값 |
| --- | --- |
| TTL | **20분** |
| 기준 시점 | 분석 **생성 시점** (고정형) |
| 조회 시 연장 | **없음** |

고정형을 쓰는 이유는 최대 보관 시간을 20분으로 확실히 잠그기 위해서다. 조회할 때마다 연장하면 새로고침을 반복하는 것만으로 무기한 보관이 되어 기준 명세 5장의 영구 저장 금지 원칙이 흔들린다.

TTL 만료 시 임시 이미지, 작업 상태, 결과 데이터를 함께 삭제한다.

## 9. 요청 제한

| 대상 | 제한 |
| --- | --- |
| 분석 생성 | IP당 분당 5회 |
| 일일 분석 | IP당 하루 10회 |
| 동시 분석 | IP당 3건 |
| 상태·결과 조회 | IP당 분당 60회 |

상태 조회 한도를 넉넉히 두는 이유는 폴링이 정상 동작이기 때문이다. 생성만 조이면 비용은 통제된다.

제한에 걸린 응답에는 아래 헤더를 포함한다.

```http
Retry-After: 30
X-RateLimit-Remaining: 0
```

IP는 요청 제한 목적으로만 사용하고, 제한 창(window)이 지나면 폐기한다. 분석 데이터와 연결해 저장하지 않는다.

## 9-1. 실행 시간 제한

기준 명세 9장의 "작업별 실행 시간 제한"을 구체화한 값이다.

| 대상 | 제한 |
| --- | ---: |
| 분석 전체 | 180초 |
| OCR 단계 | 60초 |
| LLM 호출 1회 | 45초 |

전체 제한을 넘으면 작업은 `failed` 가 되고 오류 코드는 `ANALYSIS_TIMEOUT` 이다. 단계별 제한은 전체 제한 안에서 어느 단계가 매달려 있는지 빨리 드러내기 위한 것이다.

## 9-2. 상태 확인

```http
GET /health
```

```json
{
  "status": "ok",
  "llmProvider": "stub",
  "ocrEngine": "stub",
  "ttlSeconds": 1200
}
```

배포 상태 점검과 **현재 어떤 Provider가 물려 있는지 확인**하는 용도다. 실제 모델을 붙이기 전에는 `stub` 으로 표시되므로, 운영 환경에 스텁이 올라가는 사고를 이 값으로 잡을 수 있다.

이 엔드포인트는 요청 제한을 적용하지 않는다.

## 10. CORS

| 항목 | 값 |
| --- | --- |
| 허용 Origin | 서비스 도메인만 (와일드카드 금지) |
| 허용 메서드 | `GET`, `POST`, `DELETE`, `OPTIONS` |
| 자격 증명 | 사용하지 않음 |

## 11. 상태 흐름

```text
POST /v1/analyses
  → 202  status: pending
       ↓
GET /v1/analyses/{jobId}   (2초 간격 폴링)
  → 200  status: processing, stage: ocr → parsing → analyzing → scoring → reporting
       ↓
  → 200  status: done
       ↓
GET /v1/analyses/{jobId}/result
  → 200  AnalysisResult
       ↓
클라이언트에서 결과 이미지 렌더링 및 저장
       ↓
DELETE /v1/analyses/{jobId}  또는  TTL 20분 만료
```

## 12. 개정 이력

| 버전 | 날짜 | 내용 |
| --- | --- | --- |
| v1.3 | 2026-08-26 | 최대 화소 수 상한 추가. 용량만 검사하면 33바이트 파일이 9억 화소를 선언해도 통과했다 |
| v1.2 | 2026-08-26 | 친구비 예시를 보정 곡선 반영 값으로 갱신 |
| v1.1 | 2026-08-25 | 최소 해상도 320px, 실행 시간 제한값, `/health` 엔드포인트 추가 |
| v1.0 | 2026-08-25 | 최초 작성 |
