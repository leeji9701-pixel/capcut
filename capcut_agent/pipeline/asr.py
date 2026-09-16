"""Whisper 기반 전체 대본(Transcript) 추출.

★ 핵심 원칙: 이 모듈의 결과물은 "세그먼트(문장/구 단위) 목록"이다. 단어(word) 타임스탬프도
함께 보관하지만, 이후 단계(자막/잔말·NG 판단)는 세그먼트 단위로만 결정을 내린다.

★ 플랫폼별 백엔드: Mac(Apple Silicon)에서는 mlx-whisper, 그 외(Windows 등)에서는
faster-whisper를 쓴다. mlx-whisper는 Apple Silicon 전용이라 이 저장소를 개발한
클라우드 컨테이너(Linux)에서는 설치도, 실행 검증도 할 수 없었다 - Mac에서 실제로
확인이 필요하다.

★ 동시성 주의: ctranslate2(faster-whisper)와 mlx 모두 동시 호출에 안전하지 않아
동시에 여러 요청이 들어오면 (특히 numba JIT 경로에서) segfault가 날 수 있다.
그래서 프로세스 전역 asyncio.Lock으로 한 번에 하나씩만 돌게 강제한다.

★ 캐시는 파일 mtime이 아니라 content hash로 키를 잡는다 - 업로드 과정에서 mtime이
바뀌면 매번 캐시가 miss나기 때문.
"""

import asyncio
import hashlib
import json
import os
import platform
from dataclasses import asdict, dataclass
from typing import Callable, List, Optional

from .. import env_check

_asr_lock = asyncio.Lock()
_model_cache = {}


@dataclass
class Word:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word]


@dataclass
class Transcript:
    language: str
    full_text: str
    segments: List[Segment]


def content_hash(path: str) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


def _cache_path(cache_dir: str, key: str) -> str:
    return os.path.join(cache_dir, f"{key}.transcript.json")


def _transcript_to_json(transcript: Transcript) -> dict:
    return {
        "language": transcript.language,
        "full_text": transcript.full_text,
        "segments": [
            {"start": s.start, "end": s.end, "text": s.text, "words": [asdict(w) for w in s.words]}
            for s in transcript.segments
        ],
    }


def _transcript_from_json(data: dict) -> Transcript:
    return Transcript(
        language=data["language"],
        full_text=data["full_text"],
        segments=[
            Segment(
                start=s["start"], end=s["end"], text=s["text"],
                words=[Word(**w) for w in s["words"]],
            )
            for s in data["segments"]
        ],
    )


def select_backend() -> str:
    system = env_check.detect_platform()
    if system == "mac" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            return "mlx"
        except ImportError:
            pass
    return "faster_whisper"


def _run_faster_whisper(video_path: str, language: str) -> Transcript:
    from faster_whisper import WhisperModel

    model = _model_cache.get("faster_whisper")
    if model is None:
        model = WhisperModel("small", device="auto", compute_type="int8")
        _model_cache["faster_whisper"] = model

    segments_iter, info = model.transcribe(video_path, language=language, word_timestamps=True)

    segments: List[Segment] = []
    text_parts: List[str] = []
    for seg in segments_iter:
        words = [Word(w.start, w.end, w.word) for w in (seg.words or [])]
        text = seg.text.strip()
        segments.append(Segment(seg.start, seg.end, text, words))
        if text:
            text_parts.append(text)

    return Transcript(language=info.language, full_text=" ".join(text_parts), segments=segments)


def _run_mlx_whisper(video_path: str, language: str) -> Transcript:
    import mlx_whisper

    result = mlx_whisper.transcribe(
        video_path, language=language, word_timestamps=True,
        path_or_hf_repo="mlx-community/whisper-small-mlx",
    )

    segments: List[Segment] = []
    for seg in result["segments"]:
        words = [Word(w["start"], w["end"], w["word"]) for w in seg.get("words", [])]
        segments.append(Segment(seg["start"], seg["end"], seg["text"].strip(), words))

    return Transcript(
        language=result.get("language", language),
        full_text=result.get("text", "").strip(),
        segments=segments,
    )


def _default_backend_fn(backend: str) -> Callable[[str, str], Transcript]:
    return _run_mlx_whisper if backend == "mlx" else _run_faster_whisper


async def transcribe(
    video_path: str,
    cache_dir: str,
    language: str = "ko",
    backend_fn: Optional[Callable[[str, str], Transcript]] = None,
) -> Transcript:
    """영상 전체 대본을 추출한다 (캐시 있으면 재사용).

    Args:
        video_path: 입력 영상 경로
        cache_dir: 캐시 저장 폴더 (content hash 기준)
        language: 언어 코드 (기본 한국어)
        backend_fn: 테스트/주입용. 미지정 시 플랫폼에 맞는 실제 whisper 백엔드를 고른다.
    """
    os.makedirs(cache_dir, exist_ok=True)
    key = content_hash(video_path)
    cache_file = _cache_path(cache_dir, key)

    if os.path.exists(cache_file):
        with open(cache_file, encoding="utf-8") as f:
            return _transcript_from_json(json.load(f))

    fn = backend_fn or _default_backend_fn(select_backend())

    async with _asr_lock:
        loop = asyncio.get_running_loop()
        transcript = await loop.run_in_executor(None, fn, video_path, language)

    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(_transcript_to_json(transcript), f, ensure_ascii=False)

    return transcript
