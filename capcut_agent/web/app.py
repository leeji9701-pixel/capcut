"""FastAPI 앱. 정적 HTML 1장 + SSE로 무음->대본->잔말/NG->드래프트 진행상황을 보여준다.

로컬에서만 쓰는 도구이므로 인증/CORS 등은 다루지 않는다 (127.0.0.1 바인딩 전제).
"""

import asyncio
import json
import tempfile
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from .. import env_check
from ..pipeline.filler_ng import SegmentVerdict
from ..pipeline.pipeline import StageEvent, regenerate_draft
from ..pipeline.silence_detect import Interval
from .jobs import _STREAM_END, Job, JobStore

APP_DIR = Path(__file__).parent
STATIC_DIR = APP_DIR / "static"
WORK_DIR = Path(tempfile.gettempdir()) / "capcut_agent_jobs"
CACHE_DIR = WORK_DIR / "asr_cache"

app = FastAPI(title="캡컷 에이전트")
store = JobStore()


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/env")
async def api_env(drafts_dir: Optional[str] = None):
    target = drafts_dir or env_check.default_drafts_dir()
    checks = env_check.run_all(target)
    return {
        "platform": env_check.detect_platform(),
        "default_drafts_dir": env_check.default_drafts_dir(),
        "checks": [
            {"name": c.name, "ok": c.ok, "detail": c.detail, "fix_hint": c.fix_hint} for c in checks
        ],
    }


@app.post("/api/jobs")
async def create_job(
    video: UploadFile = File(...),
    drafts_dir: str = Form(...),
    draft_name: str = Form(...),
    noise_db: float = Form(-30.0),
    min_silence: float = Form(0.4),
    pad: float = Form(0.12),
):
    job = store.create(video_path="", drafts_dir=drafts_dir, draft_name=draft_name)

    job_dir = WORK_DIR / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(video.filename or "input.mp4").suffix or ".mp4"
    video_path = job_dir / f"input{suffix}"
    with open(video_path, "wb") as f:
        while chunk := await video.read(1024 * 1024):
            f.write(chunk)
    job.video_path = str(video_path)

    asyncio.create_task(store.run(
        job, str(CACHE_DIR),
        noise_db=noise_db, min_silence_duration=min_silence, pad=pad,
    ))

    return {"job_id": job.id}


def _serialize_detail(stage: str, detail: dict) -> dict:
    if stage == "silence":
        return {"duration": detail.get("duration"), "silence_count": detail.get("silence_count")}
    if stage == "asr":
        return {"segment_count": detail.get("segment_count"), "full_text": detail.get("full_text")}
    if stage == "filler":
        return {
            "dropped_segment_count": detail.get("dropped_segment_count"),
            "kept_range_count": detail.get("kept_range_count"),
        }
    if stage == "draft":
        return {"save_path": detail.get("save_path"), "subtitle_count": detail.get("subtitle_count")}
    return detail


def _sse_format(event: StageEvent) -> str:
    payload = {"stage": event.stage, "status": event.status, "detail": _serialize_detail(event.stage, event.detail)}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@app.get("/api/jobs/{job_id}/events")
async def job_events(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job을 찾을 수 없습니다")

    async def event_stream():
        for event in list(job.events):
            yield _sse_format(event)

        if job.status in ("done", "error"):
            return

        queue = store.subscribe(job)
        try:
            while True:
                event = await queue.get()
                if event is _STREAM_END:
                    break
                yield _sse_format(event)
        finally:
            store.unsubscribe(job, queue)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


def _verdict_json(v: SegmentVerdict) -> dict:
    return {
        "start": v.segment.start, "end": v.segment.end, "text": v.segment.text,
        "is_filler": v.is_filler, "is_ng": v.is_ng,
    }


def _job_summary(job: Job) -> dict:
    return {
        "id": job.id,
        "status": job.status,
        "error": job.error,
        "duration": job.duration,
        "draft_name": job.draft_name,
        "verdicts": [_verdict_json(v) for v in (job.verdicts or [])],
        "keep_ranges": [[r.start, r.end] for r in (job.keep_ranges or [])],
        "subtitle_pieces": [{"start": p.start, "end": p.end, "text": p.text} for p in (job.subtitle_pieces or [])],
        "protected_ranges": [[r.start, r.end] for r in job.protected_ranges],
        "save_path": job.save_path,
    }


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job을 찾을 수 없습니다")
    return _job_summary(job)


@app.get("/api/jobs/{job_id}/video")
async def get_job_video(job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job을 찾을 수 없습니다")
    return FileResponse(job.video_path)


class RegenerateRequest(BaseModel):
    protected_ranges: List[List[float]] = []
    pad: float = 0.12


@app.post("/api/jobs/{job_id}/regenerate")
async def regenerate(job_id: str, body: RegenerateRequest):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(404, "job을 찾을 수 없습니다")
    if job.status != "done" or job.silences is None or job.transcript is None:
        raise HTTPException(400, "아직 1차 드래프트 생성이 끝나지 않았습니다")

    protected = [Interval(s, e) for s, e in body.protected_ranges]
    result = regenerate_draft(
        job.video_path, job.drafts_dir, job.draft_name, job.duration, job.silences, job.transcript,
        protected_ranges=protected, pad=body.pad,
    )

    job.protected_ranges = protected
    job.verdicts = result.verdicts
    job.keep_ranges = result.keep_ranges
    job.subtitle_pieces = result.subtitle_pieces
    job.save_path = result.save_path

    return _job_summary(job)
