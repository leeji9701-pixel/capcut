import asyncio

from capcut_agent.pipeline.asr import Segment, Transcript, Word, transcribe


def _fake_backend(video_path: str, language: str) -> Transcript:
    _fake_backend.calls += 1
    return Transcript(
        language=language,
        full_text="안녕하세요 테스트입니다",
        segments=[
            Segment(0.0, 1.0, "안녕하세요", [Word(0.0, 1.0, "안녕하세요")]),
            Segment(1.0, 2.0, "테스트입니다", [Word(1.0, 2.0, "테스트입니다")]),
        ],
    )


_fake_backend.calls = 0


def test_transcribe_uses_cache_on_second_call(tmp_path):
    video = tmp_path / "input.mp4"
    video.write_bytes(b"fake video bytes")
    cache_dir = tmp_path / "cache"

    _fake_backend.calls = 0
    transcript1 = asyncio.run(transcribe(str(video), str(cache_dir), backend_fn=_fake_backend))
    transcript2 = asyncio.run(transcribe(str(video), str(cache_dir), backend_fn=_fake_backend))

    assert _fake_backend.calls == 1  # 두 번째 호출은 캐시에서 읽어야 함
    assert transcript1.full_text == transcript2.full_text
    assert len(transcript2.segments) == 2
    assert transcript2.segments[0].text == "안녕하세요"
    assert transcript2.segments[0].words[0].text == "안녕하세요"


def test_transcribe_cache_keyed_by_content_not_name(tmp_path):
    video_a = tmp_path / "a.mp4"
    video_b = tmp_path / "b.mp4"
    video_a.write_bytes(b"same bytes")
    video_b.write_bytes(b"same bytes")
    cache_dir = tmp_path / "cache"

    _fake_backend.calls = 0
    asyncio.run(transcribe(str(video_a), str(cache_dir), backend_fn=_fake_backend))
    asyncio.run(transcribe(str(video_b), str(cache_dir), backend_fn=_fake_backend))

    assert _fake_backend.calls == 1  # 내용이 같으면 파일명이 달라도 캐시 공유
