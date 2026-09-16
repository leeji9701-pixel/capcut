"""원본 영상 타임라인 <-> 컷 편집 후 출력 타임라인 간 시간 변환 및 구간(Interval) 대수.

이 모듈은 순수 로직만 다룬다 (ffmpeg/ASR 호출 없음) - silence_detect가 찾은 무음 구간,
filler_ng가 찾은 잔말/NG 구간, 사용자가 직접 보존 지정한 구간을 하나로 합치고,
그 결과로 만들어지는 "남길 구간(keep ranges)"을 기준으로 자막 등 다른 시간 정보를
출력 타임라인으로 옮기는 데 쓴다.
"""

from typing import List

from .silence_detect import Interval


def merge_ranges(ranges: List[Interval]) -> List[Interval]:
    """겹치거나 맞닿은 구간들을 하나로 합친다."""
    ordered = sorted(ranges, key=lambda i: i.start)
    merged: List[Interval] = []
    for r in ordered:
        if merged and r.start <= merged[-1].end:
            merged[-1] = Interval(merged[-1].start, max(merged[-1].end, r.end))
        else:
            merged.append(Interval(r.start, r.end))
    return merged


def subtract_ranges(ranges: List[Interval], remove: List[Interval]) -> List[Interval]:
    """`ranges`에서 `remove` 구간들과 겹치는 부분을 제거한다.

    사용자가 특정 구간을 "보존"으로 지정했을 때, 그 구간을 드랍(컷) 후보 목록에서
    빼내 강제로 살리는 데 쓴다.
    """
    remove = merge_ranges(remove)
    result: List[Interval] = []
    for r in ranges:
        cursor = r.start
        for rm in remove:
            if rm.end <= cursor or rm.start >= r.end:
                continue
            if rm.start > cursor:
                result.append(Interval(cursor, min(rm.start, r.end)))
            cursor = max(cursor, rm.end)
            if cursor >= r.end:
                break
        if cursor < r.end:
            result.append(Interval(cursor, r.end))
    return [seg for seg in result if seg.duration > 0]


def build_output_offsets(keep_ranges: List[Interval]) -> List[float]:
    """각 keep_range가 출력 타임라인에서 시작하는 위치(초)를 계산한다."""
    offsets = []
    cursor = 0.0
    for r in keep_ranges:
        offsets.append(cursor)
        cursor += r.duration
    return offsets


def remap_to_output(start: float, end: float, keep_ranges: List[Interval], offsets: List[float]) -> List[Interval]:
    """원본 타임라인 구간 [start, end]를 출력(컷 편집 후) 타임라인 구간(들)으로 변환.

    잘려나간(어느 keep_range에도 속하지 않는) 부분은 자동으로 빠지므로, 입력 구간이
    컷 경계에 걸쳐 있으면 여러 조각으로 쪼개져 반환될 수 있다.
    """
    pieces: List[Interval] = []
    for keep_range, offset in zip(keep_ranges, offsets):
        overlap_start = max(start, keep_range.start)
        overlap_end = min(end, keep_range.end)
        if overlap_end > overlap_start:
            out_start = offset + (overlap_start - keep_range.start)
            out_end = offset + (overlap_end - keep_range.start)
            pieces.append(Interval(out_start, out_end))
    return pieces
