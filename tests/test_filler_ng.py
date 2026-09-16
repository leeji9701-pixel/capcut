from capcut_agent.pipeline.asr import Segment
from capcut_agent.pipeline.filler_ng import classify_segments, drop_ranges, is_filler_only, is_ng_marker


def _seg(start, end, text):
    return Segment(start=start, end=end, text=text, words=[])


def test_is_filler_only_detects_pure_filler():
    assert is_filler_only("음") is True
    assert is_filler_only("어 그니까") is True
    assert is_filler_only("") is True


def test_is_filler_only_rejects_real_content():
    assert is_filler_only("오늘은 캡컷 자동 편집 테스트를 진행하겠습니다") is False


def test_is_ng_marker_detects_retake_phrase():
    assert is_ng_marker("잠시만요 다시 말씀드릴게요") is True
    assert is_ng_marker("편집이 잘 되는지 확인해 봅시다") is False


def test_classify_and_drop_ranges():
    segments = [
        _seg(0.0, 2.0, "안녕하세요 오늘은 캡컷 자동 편집 테스트를 진행하겠습니다"),
        _seg(2.0, 2.6, "음"),
        _seg(2.6, 4.5, "다시 말씀드릴게요"),
        _seg(4.5, 7.0, "편집이 잘 되는지 확인해 봅시다"),
    ]

    verdicts = classify_segments(segments)
    assert [v.should_drop for v in verdicts] == [False, True, True, False]

    drops = drop_ranges(segments)
    assert len(drops) == 2
    assert drops[0].start == 2.0 and drops[0].end == 2.6
    assert drops[1].start == 2.6 and drops[1].end == 4.5
