"""웹 UI용 job 상태 관리. 업로드된 영상 하나 = job 하나.

무음 구간/대본 결과를 job에 보관해뒀다가, 5단계에서 사용자가 보존 구간을 새로
지정하고 "다시 생성"을 누르면 ffmpeg/whisper를 다시 돌리지 않고 즉시 재계산한다.
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..pipeline.asr import Transcript
from ..pipeline.filler_ng import SegmentVerdict
from ..pipeline.draft_builder import SubtitlePiece
from ..pipeline.pipeline import StageEvent, run_pipeline
from ..pipeline.silence_detect import Interval

# 종료(sentinel) 신호 - 이걸 큐에 넣으면 SSE 스트림을 닫는다
_STREAM_END = object()


@dataclass
class Job:
    id: str
    video_path: str
    drafts_dir: str
    draft_name: str
    status: str = "pending"  # pending | running | done | error
    error: Optional[str] = None

    events: List[StageEvent] = field(default_factory=list)
    subscribers: List["asyncio.Queue"] = field(default_factory=list)

    duration: Optional[float] = None
    silences: Optional[List[Interval]] = None
    transcript: Optional[Transcript] = None

    verdicts: Optional[List[SegmentVerdict]] = None
    keep_ranges: Optional[List[Interval]] = None
    subtitle_pieces: Optional[List[SubtitlePiece]] = None
    save_path: Optional[str] = None
    protected_ranges: List[Interval] = field(default_factory=list)


class JobStore:
    def __init__(self) -> None:
        self._jobs: Dict[str, Job] = {}

    def create(self, video_path: str, drafts_dir: str, draft_name: str) -> Job:
        job = Job(id=uuid.uuid4().hex, video_path=video_path, drafts_dir=drafts_dir, draft_name=draft_name)
        self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def subscribe(self, job: Job) -> "asyncio.Queue":
        queue: asyncio.Queue = asyncio.Queue()
        job.subscribers.append(queue)
        return queue

    def unsubscribe(self, job: Job, queue: "asyncio.Queue") -> None:
        if queue in job.subscribers:
            job.subscribers.remove(queue)

    async def _publish(self, job: Job, event: StageEvent) -> None:
        job.events.append(event)
        for queue in list(job.subscribers):
            await queue.put(event)

    async def _close_subscribers(self, job: Job) -> None:
        for queue in list(job.subscribers):
            await queue.put(_STREAM_END)

    async def run(self, job: Job, cache_dir: str, **pipeline_kwargs) -> None:
        job.status = "running"
        try:
            async for event in run_pipeline(job.video_path, job.drafts_dir, job.draft_name, cache_dir, **pipeline_kwargs):
                if event.stage == "silence" and event.status == "done":
                    job.duration = event.detail["duration"]
                    job.silences = event.detail["silences"]
                elif event.stage == "asr" and event.status == "done":
                    job.transcript = event.detail["transcript"]
                elif event.stage == "filler" and event.status == "done":
                    job.verdicts = event.detail["verdicts"]
                    job.keep_ranges = event.detail["keep_ranges"]
                elif event.stage == "draft" and event.status == "done":
                    job.subtitle_pieces = event.detail["subtitle_pieces"]
                    job.save_path = event.detail["save_path"]

                await self._publish(job, event)

            job.status = "done"
        except Exception as e:  # noqa: BLE001 - job 상태로 전달해야 하므로 넓게 잡음
            job.status = "error"
            job.error = str(e)
            await self._publish(job, StageEvent("error", "done", {"message": str(e)}))
        finally:
            await self._close_subscribers(job)
