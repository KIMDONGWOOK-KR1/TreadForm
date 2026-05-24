"""
Analysis Worker — 내부 전용 FastAPI 서버 (:8001).

무거운 분석 파이프라인(MediaPipe + 전처리 + 지표 + 렌더링)을 전담한다.
API 서버(app.py)가 HTTP 로 호출하며 외부에 직접 노출하지 않는다.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent))

from video_validator import VideoValidationError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="TreadForm Analysis Worker", docs_url=None, redoc_url=None)


class RunRequest(BaseModel):
    video_path: str
    output_dir: str


class RunResponse(BaseModel):
    analysis_result: dict
    rendered_video_path: str
    csv_report_path: str
    coach_message: str


@app.post("/run", response_model=RunResponse)
def run_analysis(req: RunRequest):
    import time

    from analyzer import run_full_analysis_with_output

    logger.info("===== /run 요청 수신 =====")
    logger.info("video_path: %s", req.video_path)
    logger.info("output_dir: %s", req.output_dir)

    vpath = Path(req.video_path)
    if not vpath.exists():
        logger.error("파일 없음: %s", req.video_path)
        raise HTTPException(status_code=400, detail="영상 파일을 찾을 수 없습니다.")
    logger.info("파일 크기: %d bytes", vpath.stat().st_size)

    t0 = time.time()
    try:
        result = run_full_analysis_with_output(req.video_path, req.output_dir)
    except VideoValidationError as e:
        logger.warning("검증 실패: %s — %s", e.code, e.message_ko)
        raise HTTPException(status_code=422, detail={"code": e.code, "message_ko": e.message_ko})
    except Exception as e:
        logger.exception("분석 실패: %s", e)
        raise HTTPException(status_code=500, detail=str(e))

    elapsed = time.time() - t0
    logger.info("분석 완료: %.1f초 소요", elapsed)
    logger.info("analysis_id: %s", result["analysis_result"].analysis_id)
    logger.info("rendered: %s", result["rendered_video_path"])
    logger.info("csv: %s", result["csv_report_path"])
    logger.info("===== /run 응답 반환 =====")

    return RunResponse(
        analysis_result=result["analysis_result"].model_dump(),
        rendered_video_path=result["rendered_video_path"],
        csv_report_path=result["csv_report_path"],
        coach_message=result["coach_message"],
    )


@app.get("/health")
def health():
    return {"status": "ok", "service": "worker"}


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001)
