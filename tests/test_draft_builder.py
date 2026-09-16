import json

from capcut_agent.pipeline.draft_builder import SubtitlePiece, build_full_draft, build_jumpcut_draft
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


@requires_ffmpeg
def test_build_full_draft_adds_subtitle_track_on_output_timeline(tmp_path, synthetic_video):
    drafts_dir = tmp_path / "CapCut Drafts"
    drafts_dir.mkdir()

    keep_ranges = [Interval(0.0, 1.62), Interval(2.88, 4.62)]
    subtitles = [
        SubtitlePiece(start=0.0, end=1.5, text="첫 번째 말"),
        SubtitlePiece(start=1.62, end=3.36, text="두 번째 말"),
    ]

    save_path = build_full_draft(
        str(drafts_dir), "test_full_draft", synthetic_video, keep_ranges, subtitle_pieces=subtitles,
    )

    with open(save_path, encoding="utf-8") as f:
        content = json.load(f)

    video_tracks = [t for t in content["tracks"] if t["type"] == "video"]
    text_tracks = [t for t in content["tracks"] if t["type"] == "text"]
    assert len(video_tracks) == 1
    assert len(text_tracks) == 1

    text_segments = text_tracks[0]["segments"]
    assert len(text_segments) == 2
    assert text_segments[0]["target_timerange"]["start"] == 0
    assert text_segments[1]["target_timerange"]["start"] == round(1.62 * 1_000_000)

    # 자막 텍스트 내용은 materials.texts 쪽에 저장됨
    texts_material = {m["id"]: m for m in content["materials"]["texts"]}
    rendered = [texts_material[seg["material_id"]]["content"] for seg in text_segments]
    assert any("첫 번째 말" in r for r in rendered)
    assert any("두 번째 말" in r for r in rendered)


@requires_ffmpeg
def test_build_full_draft_without_subtitles_omits_text_track(tmp_path, synthetic_video):
    drafts_dir = tmp_path / "CapCut Drafts"
    drafts_dir.mkdir()
    keep_ranges = [Interval(0.0, 1.5)]

    save_path = build_full_draft(str(drafts_dir), "no_subs", synthetic_video, keep_ranges, subtitle_pieces=None)

    with open(save_path, encoding="utf-8") as f:
        content = json.load(f)

    assert not [t for t in content["tracks"] if t["type"] == "text"]
