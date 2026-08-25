# Cloud Run 배포

기준 명세 6장이 전제한 **요청이 없을 때 인스턴스가 0으로 내려가는** 배포다.

`AI-모델-선정-보고서.md` 6장의 비용 계산이 이 구성을 전제로 한다. 다른 곳에 올려도 되지만, 유휴 과금이 생기면 예상 비용이 달라진다.

## 왜 이 구성인가

| 결정 | 이유 |
| --- | --- |
| **최소 인스턴스 0** | 유휴 과금이 없다. 초기 트래픽에서 서버비가 사실상 0원 |
| **최대 인스턴스 1** | 작업 상태와 요청 제한이 프로세스 메모리에 있다. 늘리면 상태가 갈라진다 |
| **워커 1개** | 같은 이유 |
| **동시성 20** | 분석은 대부분 OCR·LLM 응답을 기다리는 시간이라 한 프로세스가 여러 건을 겹쳐 처리할 수 있다 |
| **타임아웃 300초** | 분석 전체 제한이 180초. 여유를 둔다 |
| **메모리 512Mi** | 이미지를 메모리에 들고 있다. 10장 × 5MB = 50MB + 여유 |

> **최대 인스턴스 1은 임시 제약이다.** 트래픽이 늘어 인스턴스를 늘려야 하면, `app/infrastructure/storage/base.py` 의 인터페이스를 외부 TTL 저장소 구현으로 갈아 끼운 뒤에 올린다. 그 전에 늘리면 사용자가 자기 결과를 못 찾는다.

## 준비

```bash
gcloud config set project <PROJECT_ID>
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
    secretmanager.googleapis.com vision.googleapis.com
```

## 시크릿

API 키를 환경변수로 두지 않는다. `운영-보안-법적고지-명세.md` 6.2의 배포 전 항목이다.

```bash
echo -n "$OCR_KEY" | gcloud secrets create fc-ocr-key --data-file=-
echo -n "$LLM_KEY" | gcloud secrets create fc-llm-key --data-file=-
```

## 배포

```bash
gcloud run deploy friend-cost-api \
  --source backend \
  --region us-central1 \
  --allow-unauthenticated \
  --min-instances 0 \
  --max-instances 1 \
  --concurrency 20 \
  --timeout 300 \
  --memory 512Mi \
  --cpu 1 \
  --set-env-vars "FC_LLM_PROVIDER=groq,FC_LLM_MODEL=llama-3.3-70b-versatile,FC_OCR_ENGINE=google_vision" \
  --set-secrets "FC_LLM_API_KEY=fc-llm-key:latest,FC_OCR_API_KEY=fc-ocr-key:latest"
```

리전을 `us-central1` 로 두는 이유는 Cloud Run 무료 한도가 일부 미국 리전에만 적용되기 때문이다. 분석이 어차피 수십 초라 지연은 체감되지 않는다.

## 배포 후 확인

```bash
curl https://<서비스주소>/health
```

```json
{ "status": "ok", "llmProvider": "groq", "ocrEngine": "google_vision", "ttlSeconds": 1200 }
```

**`llmProvider` 나 `ocrEngine` 이 `stub` 이면 가짜가 올라간 것이다.** 환경변수가 전달되지 않았다는 뜻이므로 즉시 고친다.

## CORS

기본값이 비어 있어 브라우저에서 호출되지 않는다. 배포 시 프론트 도메인을 넣는다.

```bash
--set-env-vars "FC_CORS_ORIGINS=[\"https://friend-cost.example\"]"
```

와일드카드(`*`)는 설정으로도 넣을 수 없다. 값 검증에서 거부한다.

## 예산 알림

비용 폭주는 사고 대응 항목이다. 배포와 함께 걸어둔다.

```bash
gcloud billing budgets create \
  --billing-account=<BILLING_ID> \
  --display-name="친구비 측정기" \
  --budget-amount=30000KRW \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=90
```

3개월 비상 상한이 30,000원이므로 월 단위로는 넉넉한 값이다. 여기에 걸리면 무언가 잘못된 것이다.

## 배포 전 점검

전체 목록은 [`운영-보안-법적고지-명세.md`](../../mdfiles/운영-보안-법적고지-명세.md) 8장에 있다. 이 문서 범위에서만 추리면,

- [ ] 시크릿 매니저에 키 등록
- [ ] `FC_LLM_PROVIDER` / `FC_OCR_ENGINE` 이 `stub` 이 아닌지 `/health` 로 확인
- [ ] CORS 도메인 설정
- [ ] 최대 인스턴스 1 확인
- [ ] 예산 알림 설정
