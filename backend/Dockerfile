# 친구비 측정기 백엔드
#
# 기준 명세 6장의 배포 전제를 따른다.
#
# **OCR 이 컨테이너 안에서 돈다.** 그래서 이미지가 가볍지 않고 콜드 스타트도
# 짧지 않다. 스케일-투-제로를 노리던 옛 전제는 더 이상 맞지 않는다.
# 상시 실행을 전제로 한다(`deploy/cloudrun.md` 머리말).
#
# 그래도 우리가 직접 넣는 의존성은 최소로 유지한다. 이미지 크기 확인용
# 라이브러리를 넣지 않고 헤더를 직접 읽는 것이 그 예다.

FROM python:3.10-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

# [ocr] 를 빼면 rapidocr 과 pillow 가 들어오지 않는다. 그것들은
# optional-dependencies 에 있어서 `pip install .` 로는 설치되지 않고,
# 첫 분석 요청에서 ImportError 로 죽는다. 로컬 .venv 에는 있으므로
# 배포하기 전까지 드러나지 않는다
RUN pip install --no-cache-dir ".[ocr]"

# 모델을 빌드 때 받아둔다.
#
# rapidocr 은 첫 사용 시점에 ONNX 모델을 내려받는다. 그대로 두면 첫
# 사용자가 그 다운로드를 기다리고, 컨테이너가 바깥으로 나갈 수 없는
# 환경이면 아예 실패한다. 여기서 한 번 만들어 캐시를 채운다
RUN python -c "from rapidocr import LangRec, ModelType, OCRVersion, RapidOCR; RapidOCR(params={'Rec.lang_type': LangRec('korean'), 'Rec.model_type': ModelType.MOBILE, 'Rec.ocr_version': OCRVersion('PP-OCRv4')})"

# 루트로 돌리지 않는다
RUN useradd --create-home --uid 10001 appuser
USER appuser

# 컨테이너 서비스가 주입하는 PORT를 따른다. 없으면 8080
ENV PORT=8080
EXPOSE 8080

# 단일 워커로 띄운다. 작업 상태가 프로세스 메모리에 있으므로
# 워커를 늘리면 상태가 갈라진다. (기준 명세 6장)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT} --workers 1"]
