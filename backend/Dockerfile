# 친구비 측정기 백엔드
#
# 기준 명세 6장의 배포 전제를 따른다.
# 요청이 없을 때 인스턴스가 0으로 내려가는 컨테이너 서비스를 노린 이미지이므로,
# 콜드 스타트를 줄이기 위해 의존성을 최소로 유지한다.
# (이미지 크기 확인용 라이브러리를 넣지 않고 헤더를 직접 읽는 것도 같은 이유다.)

FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir .

# 루트로 돌리지 않는다
RUN useradd --create-home --uid 10001 appuser
USER appuser

# 컨테이너 서비스가 주입하는 PORT를 따른다. 없으면 8080
ENV PORT=8080
EXPOSE 8080

# 단일 워커로 띄운다. 작업 상태가 프로세스 메모리에 있으므로
# 워커를 늘리면 상태가 갈라진다. (기준 명세 6장)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
