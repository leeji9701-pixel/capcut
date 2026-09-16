import asyncio
import json

import pytest

from capcut_agent.pipeline import pipeline as pipeline_module
from capcut_agent.pipeline.asr import Segment, Transcript, Word
from conftest import requires_ffmpeg


def _fake_backend_factory(segments):
    def backend(video_path: str, language: str) -> Transcript:
        return Transcript(language=language, full_text=" ".join(s.text for s in segments), segments=segments)
    return backend


@requires_ffmpeg
def test_run_pipeline_end_to_end(tmp_path, synthetic_video, monkeypatch):
    monkeypatch.setattr(pipeline_module, "STAGE_DELAY_SECONDS", 0.0)

    drafts_dir = tmp_path / "CapCut Drafts"
    drafts_dir.mkdir()
    cache_dir = tmp_path / "cache"

    # 합성 영상은 [말 0-1.5][무음][말 3-4.5][무음] 패턴 -> 대본은 그 두 말 구간에 맞춘다
    segments = [
        Segment(0.0, 1.4, "안녕하세요 반갑습니다", []),
        Segment(3.0, 3.3, "음", []),  # 필러 -> 드랍되어야 함
        Segment(3.3, 4.4, "이건 진짜 내용입니다", []),
    ]
    backend = _fake_backend_factory(segments)

    events = asyncio.run(_collect(pipeline_module.run_pipeline(
        synthetic_video, str(drafts_dir), "e2e_draft", str(cache_dir),
        asr_backend_fn=backend,
    )))

    stages_seen = [(e.stage, e.status) for e in events]
    assert stages_seen == [
        ("silence", "start"), ("silence", "done"),
        ("asr", "start"), ("asr", "done"),
        ("filler", "start"), ("filler", "done"),
        ("draft", "start"), ("draft", "done"),
    ]

    filler_done = next(e for e in events if e.stage == "filler" and e.status == "done")
    assert filler_done.detail["dropped_segment_count"] == 1  # "음"만 드랍

    draft_done = next(e for e in events if e.stage == "draft" and e.status == "done")
    save_path = draft_done.detail["save_path"]

    with open(save_path, encoding="utf-8") as f:
        content = json.load(f)

    text_tracks = [t for t in content["tracks"] if t["type"] == "text"]
    assert len(text_tracks) == 1
    # 필러였던 "음" 세그먼트는 잘려나가 자막에도 나타나지 않아야 함
    assert draft_done.detail["subtitle_count"] == 2
    subtitle_texts = [p.text for p in draft_done.detail["subtitle_pieces"]]
    assert "음" not in subtitle_texts


@requires_ffmpeg
def test_protected_range_rescues_filler_segment_in_both_video_and_subtitles(tmp_path, synthetic_video, monkeypatch):
    monkeypatch.setattr(pipeline_module, "STAGE_DELAY_SECONDS", 0.0)

    from capcut_agent.pipeline.silence_detect import Interval

    drafts_dir = tmp_path / "CapCut Drafts"
    drafts_dir.mkdir()
    cache_dir = tmp_path / "cache"

    segments = [
        Segment(0.0, 1.4, "안녕하세요 반갑습니다", []),
        Segment(3.0, 3.3, "음", []),
        Segment(3.3, 4.4, "이건 진짜 내용입니다", []),
    ]
    backend = _fake_backend_factory(segments)

    events = asyncio.run(_collect(pipeline_module.run_pipeline(
        synthetic_video, str(drafts_dir), "protect_draft", str(cache_dir),
        asr_backend_fn=backend,
        protected_ranges=[Interval(3.0, 3.3)],
    )))

    draft_done = next(e for e in events if e.stage == "draft" and e.status == "done")
    subtitle_texts = [p.text for p in draft_done.detail["subtitle_pieces"]]
    assert "음" in subtitle_texts


async def _collect(async_gen):
    result = []
    async for event in async_gen:
        result.append(event)
    return result
