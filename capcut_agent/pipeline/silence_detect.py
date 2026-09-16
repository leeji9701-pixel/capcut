"""ffmpeg silencedetect 필터로 무음 구간을 찾고, 그 여집합(발화 구간)을 계산한다.

이 단계는 단어 단위 판단을 하지 않는다 - 순수하게 오디오 볼륨 기준의 점프컷이다.
잔말/NG 판단(전체 대본 기반)은 이후 단계에서 별도로 처리한다.
"""

import re
import subprocess
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class Interval:
    start: float
    """초 단위 시작 시각"""
    end: float
    """초 단위 종료 시각"""

    @property
    def duration(self) -> float:
        return self.end - self.start


_SILENCE_START_RE = re.compile(r"silence_start:\s*(-?[\d.]+)")
_SILENCE_END_RE = re.compile(r"silence_end:\s*(-?[\d.]+)")


def probe_duration(video_path: str) -> float:
    """ffprobe로 미디어 길이(초)를 얻는다."""
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ],
        capture_output=True, text=True, check=True,
    )
    return float(result.stdout.strip())


def detect_silences(
    video_path: str,
    noise_db: float = -30.0,
    min_silence_duration: float = 0.4,
    duration: float = None,
) -> List[Interval]:
    """ffmpeg silencedetect로 무음 구간 목록을 얻는다 (초 단위, 시작 기준 정렬).

    Args:
        video_path: 입력 영상 경로
        noise_db: 이 값(dB)보다 조용하면 무음으로 간주. 값이 작을수록(더 음수) 엄격해짐.
        min_silence_duration: 이 길이(초) 이상 지속된 무음만 인정.
        duration: 영상 전체 길이(초). 주어지면 파일 끝까지 이어지는 무음(silence_end
            로그가 찍히지 않는 경우)을 닫는 데 사용한다.
    """
    cmd = [
        "ffmpeg", "-i", video_path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence_duration}",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    log = result.stderr

    silences: List[Interval] = []
    pending_start = None
    for line in log.splitlines():
        start_match = _SILENCE_START_RE.search(line)
        if start_match:
            pending_start = float(start_match.group(1))
            continue
        end_match = _SILENCE_END_RE.search(line)
        if end_match and pending_start is not None:
            silences.append(Interval(pending_start, float(end_match.group(1))))
            pending_start = None

    if pending_start is not None and duration is not None and duration > pending_start:
        silences.append(Interval(pending_start, duration))

    return silences


def speech_segments(
    duration: float,
    silences: List[Interval],
    pad: float = 0.12,
    min_keep: float = 0.06,
) -> List[Interval]:
    """무음 구간의 여집합(발화 구간)을 구하고, 컷 경계에 패딩을 적용한다.

    각 무음 구간의 좌우로 `pad`초만큼 발화 구간을 확장해 단어가 씹히는 것을 방지한다.
    무음 구간이 `2*pad`보다 짧으면 패딩이 서로 맞닿을 뿐 겹치지 않도록 pad를 줄인다
    (`min(pad, gap/2)`) - 이러면 인접한 두 발화 구간이 경계에서 정확히 맞닿게 되어
    사실상 그 무음은 컷되지 않는 것과 같아진다 (너무 촘촘한 점프컷 방지).
    """
    silences = sorted(silences, key=lambda i: i.start)

    raw: List[Interval] = []
    cursor = 0.0
    for s in silences:
        if s.start > cursor:
            raw.append(Interval(cursor, s.start))
        cursor = max(cursor, s.end)
    if cursor < duration:
        raw.append(Interval(cursor, duration))

    if not raw:
        return []

    # 각 발화 구간이 이웃한 무음 쪽으로 얼마나 확장될 수 있는지 계산
    padded: List[Interval] = []
    for idx, seg in enumerate(raw):
        left_gap = seg.start - raw[idx - 1].end if idx > 0 else seg.start
        right_gap = raw[idx + 1].start - seg.end if idx < len(raw) - 1 else duration - seg.end

        left_pad = min(pad, left_gap / 2) if left_gap > 0 else 0.0
        right_pad = min(pad, right_gap / 2) if right_gap > 0 else 0.0

        new_start = max(0.0, seg.start - left_pad)
        new_end = min(duration, seg.end + right_pad)
        padded.append(Interval(new_start, new_end))

    return [seg for seg in padded if seg.duration >= min_keep]


def compute_keep_ranges(
    video_path: str,
    noise_db: float = -30.0,
    min_silence_duration: float = 0.4,
    pad: float = 0.12,
    min_keep: float = 0.06,
) -> Tuple[float, List[Interval]]:
    """영상 하나를 분석해 (전체 길이, 남길 발화 구간 목록)을 반환하는 편의 함수."""
    duration = probe_duration(video_path)
    silences = detect_silences(
        video_path, noise_db=noise_db, min_silence_duration=min_silence_duration, duration=duration,
    )
    keep = speech_segments(duration, silences, pad=pad, min_keep=min_keep)
    return duration, keep
