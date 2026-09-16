import pytest

from capcut_agent.pipeline.silence_detect import Interval
from capcut_agent.pipeline.timeline_remap import (
    build_output_offsets,
    merge_ranges,
    remap_to_output,
    subtract_ranges,
)


def test_merge_ranges_combines_overlapping_and_touching():
    ranges = [Interval(0, 1), Interval(1, 2), Interval(5, 6), Interval(5.5, 7)]
    merged = merge_ranges(ranges)
    assert merged == [Interval(0, 2), Interval(5, 7)]


def test_subtract_ranges_carves_out_protected_region():
    drops = [Interval(2.0, 8.0)]
    protect = [Interval(4.0, 5.0)]
    result = subtract_ranges(drops, protect)
    assert result == [Interval(2.0, 4.0), Interval(5.0, 8.0)]


def test_subtract_ranges_no_overlap_is_noop():
    drops = [Interval(2.0, 3.0)]
    protect = [Interval(10.0, 11.0)]
    assert subtract_ranges(drops, protect) == [Interval(2.0, 3.0)]


def test_build_output_offsets_and_remap_simple():
    keep = [Interval(0.0, 1.5), Interval(3.0, 4.5)]  # 6초 중 가운데 1.5초 컷
    offsets = build_output_offsets(keep)
    assert offsets == [0.0, 1.5]

    # 두 번째 keep_range 안에 통째로 들어가는 자막 구간
    pieces = remap_to_output(3.2, 3.8, keep, offsets)
    assert len(pieces) == 1
    assert pieces[0].start == pytest.approx(1.7)
    assert pieces[0].end == pytest.approx(2.3)


def test_remap_to_output_splits_segment_that_straddles_a_cut():
    keep = [Interval(0.0, 1.5), Interval(3.0, 4.5)]
    offsets = build_output_offsets(keep)

    # 원본 1.0~3.5초 구간은 무음(1.5~3.0)에 걸쳐 있어 둘로 쪼개져야 함
    pieces = remap_to_output(1.0, 3.5, keep, offsets)
    assert len(pieces) == 2
    assert pieces[0].start == pytest.approx(1.0)
    assert pieces[0].end == pytest.approx(1.5)
    assert pieces[1].start == pytest.approx(1.5)
    assert pieces[1].end == pytest.approx(2.0)


def test_remap_to_output_drops_segment_entirely_inside_a_cut():
    keep = [Interval(0.0, 1.5), Interval(3.0, 4.5)]
    offsets = build_output_offsets(keep)

    pieces = remap_to_output(1.6, 2.9, keep, offsets)
    assert pieces == []
