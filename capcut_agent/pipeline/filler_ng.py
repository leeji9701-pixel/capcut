"""전체 대본(세그먼트 목록) 기반 잔말/NG 컷 판단.

★ 핵심 원칙: 단어 단위로 판단하지 않는다. Whisper가 나눈 세그먼트(문장/구 단위)
전체를 "잔말만 있음" 또는 "NG 마커 포함"으로 표시하거나 하지 않거나, 둘 중 하나로만
판단한다 - 세그먼트 중간을 단어 단위로 쪼개서 자르지 않는다.

이 목록은 시작점일 뿐이다. 실제 채널 말투에 맞춰 FILLER_WORDS/NG_MARKERS를
계속 다듬어야 정확도가 올라간다.
"""

from dataclasses import dataclass
from typing import List

from .asr import Segment
from .silence_detect import Interval

FILLER_WORDS = [
    "음", "어", "그", "저", "저기", "그니까", "그러니까", "인제", "이제", "약간", "뭐지", "막",
]

NG_MARKERS = [
    "다시 할게요", "다시 갈게요", "다시 말씀드릴게요", "다시 찍을게요", "다시 갈게",
    "잠시만요", "잠깐만요", "죄송해요 다시", "컷 해주세요", "여기 컷", "엔지 났어요",
]


@dataclass
class SegmentVerdict:
    segment: Segment
    is_filler: bool
    is_ng: bool

    @property
    def should_drop(self) -> bool:
        return self.is_filler or self.is_ng


def _strip(text: str) -> str:
    return text.strip().strip(".,!?~ 　")


def is_filler_only(text: str) -> bool:
    """세그먼트 텍스트가 실질적 내용 없이 필러 단어로만 이루어졌는지 판단."""
    stripped = _strip(text)
    if not stripped:
        return True
    if len(stripped) > 8:
        return False
    tokens = stripped.replace(",", " ").split()
    if not tokens:
        return True
    return all(any(tok == fw or tok.startswith(fw) for fw in FILLER_WORDS) for tok in tokens)


def is_ng_marker(text: str) -> bool:
    """세그먼트 텍스트에 NG(재촬영/컷 요청) 마커가 포함되어 있는지 판단."""
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in NG_MARKERS)


def classify_segments(segments: List[Segment]) -> List[SegmentVerdict]:
    return [
        SegmentVerdict(segment=seg, is_filler=is_filler_only(seg.text), is_ng=is_ng_marker(seg.text))
        for seg in segments
    ]


def drop_ranges(segments: List[Segment]) -> List[Interval]:
    """드랍(컷)할 시간 구간 목록 - 필러 전용 세그먼트 및 NG 마커가 포함된 세그먼트."""
    return [
        Interval(v.segment.start, v.segment.end)
        for v in classify_segments(segments)
        if v.should_drop
    ]
