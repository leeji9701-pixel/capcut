import asyncio
import json

import httpx
import pytest

from capcut_agent.pipeline import asr as asr_module
from capcut_agent.pipeline.asr import Segment, Transcript
from capcut_agent.web import app as app_module
from conftest import requires_ffmpeg


def _fake_backend(video_path: str, language: str) -> Transcript:
    segments = [
        Segment(0.0, 1.4, "안녕하세요 반갑습니다", []),
        Segment(3.0, 3.3, "음", []),  # 필러 -> 드랍
        Segment(3.3, 4.4, "이건 진짜 내용입니다", []),
    ]
    return Transcript(language=language, full_text=" ".join(s.text for s in segments), segments=segments)


async def _run_full_job(tmp_path, synthetic_video, monkeypatch):
    monkeypatch.setattr(asr_module, "_default_backend_fn", lambda backend: _fake_backend)

    drafts_dir = tmp_path / "CapCut Drafts"
    drafts_dir.mkdir()
    cache_dir = tmp_path / "asr_cache"
    monkeypatch.setattr(app_module, "CACHE_DIR", cache_dir)
    monkeypatch.setattr(app_module, "WORK_DIR", tmp_path / "jobs")

    transport = httpx.ASGITransport(app=app_module.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        env_res = await client.get("/api/env")
        assert env_res.status_code == 200
        assert env_res.json()["platform"] in ("mac", "windows", "unsupported")

        with open(synthetic_video, "rb") as f:
            video_bytes = f.read()

        files = {"video": ("input.mp4", video_bytes, "video/mp4")}
        data = {"drafts_dir": str(drafts_dir), "draft_name": "web_test_draft"}
        create_res = await client.post("/api/jobs", files=files, data=data)
        assert create_res.status_code == 200
        job_id = create_res.json()["job_id"]

        events = []
        async with client.stream("GET", f"/api/jobs/{job_id}/events", timeout=30) as resp:
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                payload = json.loads(line[len("data: "):])
                events.append(payload)
                if payload["stage"] == "draft" and payload["status"] == "done":
                    break

        detail_res = await client.get(f"/api/jobs/{job_id}")
        detail = detail_res.json()

        video_res = await client.get(f"/api/jobs/{job_id}/video")

        regen_res = await client.post(
            f"/api/jobs/{job_id}/regenerate",
            json={"protected_ranges": [[3.0, 3.3]]},  # 필러 구간을 강제로 보존
        )

        return events, detail, video_res, regen_res.json()


@requires_ffmpeg
def test_full_job_flow_over_http(tmp_path, synthetic_video, monkeypatch):
    events, detail, video_res, regen = asyncio.run(_run_full_job(tmp_path, synthetic_video, monkeypatch))

    stages = [(e["stage"], e["status"]) for e in events]
    assert ("silence", "start") in stages
    assert ("draft", "done") in stages

    assert detail["status"] == "done"
    assert len(detail["verdicts"]) == 3
    assert detail["verdicts"][1]["is_filler"] is True  # "음"

    assert video_res.status_code == 200
    assert video_res.headers["content-type"].startswith("video/")

    # 보존 구간 지정 후 재생성 -> "음" 세그먼트가 더 이상 드랍되지 않아야 함
    assert len(regen["keep_ranges"]) >= 1
    total_kept_before = sum(e - s for s, e in [tuple(r) for r in detail["keep_ranges"]])
    total_kept_after = sum(e - s for s, e in [tuple(r) for r in regen["keep_ranges"]])
    assert total_kept_after > total_kept_before
