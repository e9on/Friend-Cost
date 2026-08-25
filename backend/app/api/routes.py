"""HTTP 엔드포인트.

API 명세 3~7장.

결과 다운로드 엔드포인트는 두지 않는다. 결과 이미지는 클라이언트가 렌더링한다.
서버가 파일을 만들면 임시 파일이 하나 더 생겨 삭제 정책이 복잡해지고
렌더링 비용도 서버가 지기 때문이다.
"""

import logging

from fastapi import APIRouter, File, Request, Response, UploadFile, status

from app.api.schemas import CreateResponse, HealthResponse, StatusResponse
from app.application.service.upload_validator import UploadedImage
from app.domain.model.result import AnalysisResult

logger = logging.getLogger(__name__)

router = APIRouter()


def _client_ip(request: Request) -> str:
    """요청자의 IP. 프록시 뒤에 있으면 첫 번째 전달 주소를 쓴다."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post(
    "/v1/analyses",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateResponse,
    response_model_by_alias=True,
)
async def create_analysis(request: Request, images: list[UploadFile] = File(default=[])):
    service = request.app.state.service
    limiter = request.app.state.limiter
    settings = request.app.state.settings
    ip = _client_ip(request)

    limiter.check_create(ip)
    try:
        payload = [
            UploadedImage(filename=image.filename or "", data=await image.read())
            for image in images
        ]
        job = await service.create(payload)
    except BaseException:
        limiter.release(ip)
        raise

    # 분석이 끝나면 동시 실행 슬롯을 돌려준다
    request.app.state.pending_release[job.job_id] = ip

    return CreateResponse(
        job_id=job.job_id,
        status=job.status,
        expires_at=job.expires_at,
        poll_after_seconds=settings.poll_after_seconds,
    )


@router.get(
    "/v1/analyses/{job_id}",
    response_model=StatusResponse,
    response_model_by_alias=True,
)
async def get_status(request: Request, job_id: str):
    service = request.app.state.service
    limiter = request.app.state.limiter
    settings = request.app.state.settings

    limiter.check_poll(_client_ip(request))
    job = service.status(job_id)

    if job.status.is_terminal:
        ip = request.app.state.pending_release.pop(job_id, None)
        if ip:
            limiter.release(ip)

    return StatusResponse.of(job, settings.poll_after_seconds)


@router.get(
    "/v1/analyses/{job_id}/result",
    response_model=AnalysisResult,
    response_model_by_alias=True,
)
async def get_result(request: Request, job_id: str):
    request.app.state.limiter.check_poll(_client_ip(request))
    return request.app.state.service.result(job_id)


@router.delete("/v1/analyses/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis(request: Request, job_id: str) -> Response:
    _delete(request, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/v1/analyses/{job_id}/deletion", status_code=status.HTTP_204_NO_CONTENT)
async def delete_analysis_via_beacon(request: Request, job_id: str) -> Response:
    """`navigator.sendBeacon` 은 POST만 보낼 수 있다.

    페이지 이탈 시점의 삭제 요청을 받기 위해 같은 동작을 POST로도 제공한다.
    """
    _delete(request, job_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def _delete(request: Request, job_id: str) -> None:
    """삭제는 멱등이며 존재 여부를 알려주지 않는다."""
    request.app.state.service.delete(job_id)
    ip = request.app.state.pending_release.pop(job_id, None)
    if ip:
        request.app.state.limiter.release(ip)


@router.get("/health", response_model=HealthResponse, response_model_by_alias=True)
async def health(request: Request):
    settings = request.app.state.settings
    return HealthResponse(
        status="ok",
        llm_provider=settings.llm_provider,
        ocr_engine=settings.ocr_engine,
        ttl_seconds=settings.ttl_seconds,
    )
