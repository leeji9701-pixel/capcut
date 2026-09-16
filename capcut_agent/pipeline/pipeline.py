"""1~4단계를 하나로 묶는 오케스트레이션.

런타임 단계는 항상 이 순서로 진행된다: silence -> asr -> filler -> draft(+자막).
각 단계는 시작/완료 이벤트를 내보내므로 웹 UI의 SSE stepper와 CLI 양쪽에서 그대로 쓸 수 있다.

단계당 최소 `STAGE_DELAY_SECONDS`만큼 지연을 강제한다 - ASR 캐시가 히트해서
그 단계가 순식간에 끝나버리면 UI에서 단계 전환 애니메이션이 보이지도 않고 지나가버리기
때문이다.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Callable, Dict, List, Optional

from . import filler_ng, timeline_remap
from .asr import Transcript, transcribe
from .draft_builder import SubtitlePiece, build_full_draft
from .silence_detect import Interval, detect_silences, probe_duration, speech_segments

STAGE_DELAY_SECONDS = 0.5


@dataclass
class StageEvent:
    stage: str
    """"silence" | "asr" | "filler" | "draft" 중 하나"""
    status: str
    """"start" | "done" """
    detail: Dict[str, Any]


async def _with_min_delay(started_at: float) -> None:
    elapsed = time.monotonic() - started_at
    if elapsed < STAGE_DELAY_SECONDS:
        await asyncio.sleep(STAGE_DELAY_SECONDS - elapsed)


@dataclass
class DraftResult:
    verdicts: List[filler_ng.SegmentVerdict]
    keep_ranges: List[Interval]
    subtitle_pieces: List[SubtitlePiece]
    save_path: str


def _classify_and_keep_ranges(
    duration: float,
    silences: List[Interval],
    transcript: Transcript,
    protected_ranges: List[Interval],
    pad: float,
):
    """잔말/NG 판단 결과와 최종 keep_ranges를 계산한다.

    무음 컷에는 단어가 안 씹히게 `pad`만큼 여유를 주지만, 잔말/NG 컷은 정확히 그
    세그먼트 구간만큼만 잘라내는 "칼컷"이어야 한다 - 무음 padding 로직을 그대로 재사용해
    잔말/NG 구간까지 뭉뚱그려 패딩을 주면, 필러 세그먼트 경계가 무음 경계와 맞닿아 있을 때
    필러의 일부가 패딩 때문에 도로 살아남는 문제가 생긴다. 그래서 무음 기준 keep_ranges를
    먼저 구한 뒤, 거기서 잔말/NG 구간을 정확히 도려내는 순서로 처리한다.

    사용자가 지정한 보존 구간은 잔말/NG/무음 판정과 무관하게 항상 최종적으로 되살린다.
    """
    verdicts = filler_ng.classify_segments(transcript.segments)
    ng_drops = [Interval(v.segment.start, v.segment.end) for v in verdicts if v.should_drop]

    silence_keep = speech_segments(duration, silences, pad=pad)
    keep_ranges = timeline_remap.subtract_ranges(silence_keep, ng_drops)
    keep_ranges = timeline_remap.merge_ranges(keep_ranges + protected_ranges)
    return verdicts, keep_ranges


def _build_subtitles_and_draft(
    video_path: str,
    drafts_dir: str,
    draft_name: str,
    verdicts: List[filler_ng.SegmentVerdict],
    keep_ranges: List[Interval],
    allow_replace: bool,
) -> DraftResult:
    # 잔말/NG 여부로 거르지 않는다 - 최종적으로 keep_ranges에 살아남은(=보존 지정으로
    # 되살아났을 수도 있는) 구간만 remap_to_output이 자연스럽게 걸러준다. 드랍된 세그먼트는
    # keep_ranges에 없으므로 조각이 하나도 안 나와 자막도 자동으로 안 붙는다.
    offsets = timeline_remap.build_output_offsets(keep_ranges)
    subtitle_pieces: List[SubtitlePiece] = []
    for v in verdicts:
        for piece in timeline_remap.remap_to_output(v.segment.start, v.segment.end, keep_ranges, offsets):
            subtitle_pieces.append(SubtitlePiece(piece.start, piece.end, v.segment.text))

    save_path = build_full_draft(
        drafts_dir, draft_name, video_path, keep_ranges, subtitle_pieces, allow_replace=allow_replace,
    )
    return DraftResult(verdicts, keep_ranges, subtitle_pieces, save_path)


def compute_and_build_draft(
    video_path: str,
    drafts_dir: str,
    draft_name: str,
    duration: float,
    silences: List[Interval],
    transcript: Transcript,
    protected_ranges: Optional[List[Interval]] = None,
    pad: float = 0.12,
    allow_replace: bool = True,
) -> DraftResult:
    """잔말/NG 판단 + 드래프트(영상+자막) 생성. silence/asr 결과가 이미 있을 때(재생성 등)
    ffmpeg/whisper를 다시 돌리지 않고 이 부분만 다시 계산하기 위해 분리해뒀다.
    """
    verdicts, keep_ranges = _classify_and_keep_ranges(
        duration, silences, transcript, protected_ranges or [], pad,
    )
    return _build_subtitles_and_draft(video_path, drafts_dir, draft_name, verdicts, keep_ranges, allow_replace)


async def run_pipeline(
    video_path: str,
    drafts_dir: str,
    draft_name: str,
    cache_dir: str,
    protected_ranges: Optional[List[Interval]] = None,
    noise_db: float = -30.0,
    min_silence_duration: float = 0.4,
    pad: float = 0.12,
    language: str = "ko",
    allow_replace: bool = True,
    asr_backend_fn: Optional[Callable[[str, str], Transcript]] = None,
) -> AsyncIterator[StageEvent]:
    """영상 하나를 처리해 CapCut 드래프트를 생성하며, 진행되는 대로 StageEvent를 내보낸다."""
    protected_ranges = protected_ranges or []

    yield StageEvent("silence", "start", {})
    t0 = time.monotonic()
    duration = probe_duration(video_path)
    silences = detect_silences(
        video_path, noise_db=noise_db, min_silence_duration=min_silence_duration, duration=duration,
    )
    await _with_min_delay(t0)
    yield StageEvent("silence", "done", {
        "duration": duration, "silence_count": len(silences), "silences": silences,
    })

    yield StageEvent("asr", "start", {})
    t0 = time.monotonic()
    transcript = await transcribe(video_path, cache_dir, language=language, backend_fn=asr_backend_fn)
    await _with_min_delay(t0)
    yield StageEvent("asr", "done", {
        "segment_count": len(transcript.segments),
        "full_text": transcript.full_text,
        "transcript": transcript,
    })

    yield StageEvent("filler", "start", {})
    t0 = time.monotonic()
    verdicts, keep_ranges = _classify_and_keep_ranges(duration, silences, transcript, protected_ranges, pad)
    await _with_min_delay(t0)
    yield StageEvent("filler", "done", {
        "dropped_segment_count": sum(1 for v in verdicts if v.should_drop),
        "kept_range_count": len(keep_ranges),
        "verdicts": verdicts,
        "keep_ranges": keep_ranges,
    })

    yield StageEvent("draft", "start", {})
    t0 = time.monotonic()
    draft_result = _build_subtitles_and_draft(
        video_path, drafts_dir, draft_name, verdicts, keep_ranges, allow_replace,
    )
    await _with_min_delay(t0)
    yield StageEvent("draft", "done", {
        "save_path": draft_result.save_path,
        "subtitle_count": len(draft_result.subtitle_pieces),
        "subtitle_pieces": draft_result.subtitle_pieces,
    })


def regenerate_draft(
    video_path: str,
    drafts_dir: str,
    draft_name: str,
    duration: float,
    silences: List[Interval],
    transcript: Transcript,
    protected_ranges: Optional[List[Interval]] = None,
    pad: float = 0.12,
) -> DraftResult:
    """이미 끝난 job에 대해, 사용자가 보존 구간을 새로 지정했을 때 draft만 다시 만든다
    (ffmpeg 무음 탐지와 whisper 대본 추출은 다시 하지 않음 - 5단계 프리뷰/마킹 용도).
    """
    return compute_and_build_draft(
        video_path, drafts_dir, draft_name, duration, silences, transcript,
        protected_ranges=protected_ranges, pad=pad, allow_replace=True,
    )
