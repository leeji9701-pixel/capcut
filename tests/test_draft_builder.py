import json

from capcut_agent.pipeline.draft_builder import build_jumpcut_draft
from capcut_agent.pipeline.silence_detect import Interval
from conftest import requires_ffmpeg


@requires_ffmpeg
def test_build_jumpcut_draft_produces_valid_contiguous_timeline(tmp_path, synthetic_video):
    drafts_dir = tmp_path / "CapCut Drafts"
    drafts_dir.mkdir()

    keep_ranges = [Interval(0.0, 1.62), Interval(2.88, 4.62)]

    save_path = build_jumpcut_draft(str(drafts_dir), "test_draft", synthetic_video, keep_ranges)

    with open(save_path, encoding="utf-8") as f:
        content = json.load(f)

    assert (drafts_dir / "test_draft" / "draft_meta_info.json").exists()

    video_tracks = [t for t in content["tracks"] if t["type"] == "video"]
    assert len(video_tracks) == 1
    segments = video_tracks[0]["segments"]
    assert len(segments) == len(keep_ranges)

    # 메인 트랙 첫 세그먼트는 반드시 0에서 시작해야 함 (CapCut이 강제로 당겨버리는 것을 방지)
    assert segments[0]["target_timerange"]["start"] == 0

    # 세그먼트들이 타임라인 상에서 빈틈/겹침 없이 이어붙어 있어야 함
    cursor = 0
    for seg, expected in zip(segments, keep_ranges):
        target = seg["target_timerange"]
        assert target["start"] == cursor
        cursor += target["duration"]

        expected_duration_us = round(expected.duration * 1_000_000)
        assert abs(target["duration"] - expected_duration_us) < 1000  # 1ms 이내 오차 허용

    # source_timerange은 원본 영상에서 남긴 발화 구간을 정확히 가리켜야 함
    first_source = segments[0]["source_timerange"]
    assert first_source["start"] == 0
