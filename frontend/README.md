# 친구비 측정기 — 프론트엔드

React + TypeScript + Vite. 정적 호스팅을 전제로 한다.

명세는 [`mdfiles/Frontend-명세.md`](../mdfiles/Frontend-명세.md)에 있다. 화면 흐름이나 사용자와의 약속을 바꿀 때는 그 문서를 먼저 고친다.

## 실행

```bash
npm install
npm run dev      # http://localhost:5173
```

개발 중에는 `/v1` 요청이 `http://127.0.0.1:8000` 으로 프록시된다. 백엔드를 함께 띄워야 한다.

```bash
cd ../backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload
```

## 테스트

```bash
npm test
npm run coverage
```

## 빌드

```bash
npm run build     # dist/
npm run preview
```

## 모바일 우선인 이유

취향이 아니다. 대화 캡처는 휴대폰에서 찍고, 결과도 휴대폰에서 보고, 공유도 휴대폰에서 한다. 데스크톱은 폭만 제한하면 되는 부수적 경우다.

## 알아둘 것 세 가지

### 결과 이미지는 캔버스에 직접 그린다

서버에 다운로드 엔드포인트가 없다(기준 명세 11장). `src/lib/shareImage.ts` 가 캔버스에 한 줄씩 그린다.

DOM 캡처 라이브러리를 쓰지 않는 이유는 **의존성 없이 어느 브라우저에서나 같은 결과가 나오기 때문**이다. 폰트 로딩이나 CSS 해석 차이로 이미지가 깨지지 않는다.

모바일에서는 `<a download>` 이 무시되는 경우가 있어 공유 시트를 먼저 시도한다.

### 답장 속도의 `null` 을 0으로 바꾸지 않는다

서버는 표본이 부족하면 `avgReplySeconds` 를 `null` 로 준다. 화면에는 "알 수 없음"으로 표시한다.

`0초` 로 보이면 "즉시 답장하는 사이"라는 **정반대의 뜻**이 된다. 서버가 굳이 구분해 보내는 이유가 여기 있다.

### 오류 코드마다 안내가 다르다

`src/components/Failure.tsx` 가 `error.code` 로 분기한다.

대화가 짧아 실패한 사람에게 "다시 시도"를 권하면 같은 결과만 반복된다. 무엇을 고쳐야 하는지 알려주는 편이 낫다.

## 환경변수

| 변수 | 기본값 | 설명 |
| --- | --- | --- |
| `VITE_API_BASE` | `/v1` | 백엔드 주소. 배포 시 절대 주소를 넣는다 |
| `VITE_TERMS_URL` | (없음) | 이용약관. 비우면 "준비 중"으로 표시 |
| `VITE_PRIVACY_URL` | (없음) | 개인정보 처리방침. 같음 |

## 배포

정적 호스팅이면 어디든 된다. 보안 헤더 설정을 함께 두었다.

| 파일 | 대상 |
| --- | --- |
| `public/_headers` | Netlify, Cloudflare Pages |
| `vercel.json` | Vercel |

두 파일의 CSP는 같다. `connect-src` 는 **배포 시 실제 API 도메인으로 좁혀야 한다.** 기본값 `'self'` 는 프론트와 백엔드가 같은 도메인일 때만 맞다.

`img-src` 에 `blob:` 이 필요한 이유는 업로드 미리보기와 결과 카드가 objectURL을 쓰기 때문이다.

## 구조

```text
src/
├── api/         타입(데이터 계약을 옮긴 것)과 HTTP 클라이언트
├── components/  화면 넷 + 법적 고지
├── hooks/       useAnalysis — 생성·폴링·결과·삭제를 소유한다
├── lib/         포맷 유틸, 결과 카드 렌더러
└── test/        테스트 설정
```

상태는 `useAnalysis` 하나가 소유한다. 화면은 상태를 읽어 그리기만 한다.
