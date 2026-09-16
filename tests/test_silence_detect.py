import pytest

from capcut_agent.pipeline.silence_detect import Interval, compute_keep_ranges, detect_silences, speech_segments
from conftest import requires_ffmpeg


@requires_ffmpeg
def test_detect_silences_finds_two_gaps(synthetic_video):
    silences = detect_silences(synthetic_video, min_silence_duration=0.4, duration=6.0)
    assert len(silences) == 2
    assert silences[0].start == pytest.approx(1.5, abs=0.15)
    assert silences[0].end == pytest.approx(3.0, abs=0.15)
    assert silences[1].start == pytest.approx(4.5, abs=0.15)
    assert silences[1].end == pytest.approx(6.0, abs=0.15)


@requires_ffmpeg
def test_compute_keep_ranges_cuts_silence_keeps_speech(synthetic_video):
    duration, keep = compute_keep_ranges(synthetic_video, min_silence_duration=0.4, pad=0.12)

    assert duration == pytest.approx(6.0, abs=0.05)
    assert len(keep) == 2

    # 메인 트랙 제약: 첫 발화 구간은 0초에서 시작해야 함
    assert keep[0].start == 0.0

    # 두 구간은 겹치지 않고, 순서대로 나열됨
    assert keep[0].end <= keep[1].start

    # 원본 6초 중 무음(약 3초)이 상당 부분 제거되어야 함
    kept_total = sum(seg.duration for seg in keep)
    assert kept_total < 4.5
    assert kept_total > 2.5


def test_speech_segments_never_overlaps_when_silence_shorter_than_double_pad():
    # 무음 길이(0.1s)가 2*pad(0.24s)보다 짧은 경우 -> 패딩이 서로 잡아먹지 않고 축소되어야 함
    silences = [Interval(1.0, 1.1)]
    keep = speech_segments(duration=2.0, silences=silences, pad=0.12, min_keep=0.0)

    assert len(keep) == 2
    assert keep[0].end <= keep[1].start
