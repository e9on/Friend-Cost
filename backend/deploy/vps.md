# VPS 배포

**채택한 구성이다.** Cloud Run 안은 `cloudrun.md` 에 남겨두었지만 지금 구조에는 맞지 않는다.

## 왜 VPS 인가

| 결정 | 이유 |
| --- | --- |
| **국내 VPS** | 서버가 국내면 **국외 이전이 늘지 않는다.** 해외에 두면 Groq(미국) 외에 하나가 더 생겨 동의 항목과 처리방침을 함께 고쳐야 한다 |
| **상시 실행** | RapidOCR 이 컨테이너 안에서 돈다. 스케일-투-제로는 콜드 스타트마다 ONNX 모델을 다시 올린다 |
| **인스턴스 1개** | 작업 상태와 요청 제한이 프로세스 메모리에 있다. 늘리면 사용자가 자기 결과를 못 찾는다 |
| **선불 고정비** | 트래픽이 늘어도 요금이 변하지 않는다. 개인이 무료로 여는 서비스에서 예상 못 한 청구서는 서비스를 닫게 만드는 가장 흔한 이유다 |

Cloud Run 상시 실행은 월 27,594원, VPS 는 9,800원이다(`tools/cost_model.py`). RapidOCR 을 쓰는 한 상시 실행이 필요하므로 Cloud Run 의 장점이 사라진다.

## 사양

```text
RAM     2Gi 이상   ← 아래 실측 참조
CPU     2 vCPU 이상
디스크  20GB       ← 이미지 + ONNX 모델
```

### 메모리는 실측으로 정한다

| 상태 | WorkingSet |
| --- | ---: |
| 기동 직후 | 38 MiB |
| 분석 1건 | 169 MiB |
| 동시 3건 | 975 MiB |

기본 약 170MiB 에 **분석 한 건당 약 270MiB** 가 붙는다.

> **이 값은 Windows 측정치다.** 리눅스 컨테이너에서 다시 재고 동시성을 확정한다. 넘치면 컨테이너가 죽고 진행 중이던 분석이 전부 사라진다.

동시성을 정할 때는 **Groq 무료 티어의 분당 한도(실측 2.1건)** 가 먼저 걸린다는 점을 감안한다. 메모리를 키워도 그 위로는 못 올라간다.

## 준비

```bash
# 도커
curl -fsSL https://get.docker.com | sh

# 방화벽은 80/443 만 연다. 8080 을 직접 열지 않는다
ufw allow 80,443/tcp && ufw enable
```

## 시크릿

API 키를 이미지에 굽지 않는다. 서버의 파일에 두고 권한을 좁힌다.

```bash
install -m 600 /dev/null /etc/friend-cost.env
vi /etc/friend-cost.env      # .env.example 을 채워 넣는다
```

`600` 이라 root 만 읽는다. 이미지에 넣으면 이미지를 가진 사람이 모두 읽게 된다.

## 실행

```bash
docker build -t friend-cost-api ./backend

docker run -d --name friend-cost-api \
  --restart unless-stopped \
  --env-file /etc/friend-cost.env \
  -e PORT=8080 \
  -m 2g \
  -p 127.0.0.1:8080:8080 \
  friend-cost-api
```

- `-p 127.0.0.1:8080` — 바깥에 직접 열지 않는다. 앞단은 Caddy 가 맡는다
- `-m 2g` — 컨테이너가 서버 전체를 잡아먹고 SSH 까지 막는 일을 방지한다
- `--restart unless-stopped` — 재시작하면 요청 제한 카운터가 0으로 돌아간다(알려진 한계)

## HTTPS

Caddy 가 인증서를 자동으로 받고 갱신한다.

```caddyfile
api.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

```bash
docker run -d --name caddy --restart unless-stopped \
  --network host \
  -v /etc/caddy/Caddyfile:/etc/caddy/Caddyfile:ro \
  -v caddy_data:/data \
  caddy:2
```

## 프론트엔드

정적 빌드이므로 서버에 두지 않는다. Cloudflare Pages 등에 올린다.

```bash
cd frontend
VITE_API_BASE=https://api.example.com/v1 npm run build   # dist/ 를 올린다
```

**백엔드의 `FC_CORS_ORIGINS` 에 프론트 도메인을 넣어야 한다.** 기본값이 빈 배열이라 채우지 않으면 브라우저에서 아무 요청도 나가지 않는다. 이것이 배포 후 가장 흔한 실패다.

```bash
FC_CORS_ORIGINS=["https://friend-cost.pages.dev"]
```

## 운영 종료

이 서비스는 **기간을 정해두고 연다**(`운영-보안-법적고지-명세.md` 6.2.2).

```bash
FC_SERVICE_END_DATE=2026-11-30
```

그날이 지나면 새 분석을 받지 않는다. 진행 중이던 작업의 조회와 삭제는 계속 동작한다.

> **서버 정지가 곧 과금 정지는 아니다.** VPS 요금은 인스턴스를 내려야 멈춘다. 종료일은 데이터를 더 받지 않기 위한 장치이고, 인스턴스 정리는 사람이 해야 한다.

종료일에 할 일:

```bash
docker rm -f friend-cost-api caddy
# VPS 인스턴스 파기 (요금 정지)
# DNS 레코드 제거
```

## 배포 후 확인

```bash
curl https://api.example.com/health
# {"status":"ok","llmProvider":"groq","ocrEngine":"rapid","ttlSeconds":1200}
```

`ocrEngine` 이 `rapid` 인지 본다. `stub` 이면 환경변수가 안 먹은 것이고, 사용자는 **지어낸 결과를 진짜로 믿게 된다.**

그다음 브라우저에서 실제로 한 번 올려본다. `curl` 이 통과해도 CORS 가 막혀 있으면 브라우저에서는 아무것도 안 된다.

## 우리가 직접 지는 것

Cloud Run 과 달리 아래가 우리 몫이다. 싼 대가다.

- OS 보안 패치
- 컨테이너 재시작·모니터링 (`--restart unless-stopped` 가 최소한만 해준다)
- 디스크 용량 관리
- 장애 대응

`운영-보안-법적고지-명세.md` 7장의 사고 대응 표가 여기에 그대로 적용된다.
