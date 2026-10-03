"""폴더 정리 로직 (GUI와 분리해 테스트 가능하게 둔다)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

VIDEO_EXTS = {
    ".mp4", ".mov", ".insv", ".avi", ".mkv", ".m4v",
    ".mts", ".m2ts", ".wmv", ".webm", ".3gp",
}


@dataclass
class Plan:
    root: Path
    videos: list[Path] = field(default_factory=list)   # 하위 폴더에서 꺼낼 동영상
    subdirs: list[Path] = field(default_factory=list)  # 삭제할 최상위 하위 폴더
    other_files: int = 0                               # 함께 삭제될 동영상 아닌 파일 수


@dataclass
class Result:
    moved: list[tuple[Path, Path]] = field(default_factory=list)
    deleted_dirs: list[Path] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def is_video(path: Path) -> bool:
    return path.suffix.lower() in VIDEO_EXTS


def make_plan(root: Path) -> Plan:
    root = Path(root)
    if not root.is_dir():
        raise NotADirectoryError(f"폴더가 아닙니다: {root}")
    plan = Plan(root=root)
    for sub in sorted(root.iterdir()):
        if not sub.is_dir() or sub.is_symlink():
            continue
        plan.subdirs.append(sub)
        for f in sorted(sub.rglob("*")):
            if not f.is_file():
                continue
            if is_video(f):
                plan.videos.append(f)
            else:
                plan.other_files += 1
    return plan


def unique_target(directory: Path, name: str) -> Path:
    target = directory / name
    stem, suffix = Path(name).stem, Path(name).suffix
    n = 1
    while target.exists():
        target = directory / f"{stem} ({n}){suffix}"
        n += 1
    return target


def execute(plan: Plan) -> Result:
    result = Result()
    failed_dirs: set[Path] = set()
    for video in plan.videos:
        target = unique_target(plan.root, video.name)
        try:
            shutil.move(str(video), str(target))
            result.moved.append((video, target))
        except OSError as e:
            result.errors.append(f"이동 실패: {video} ({e})")
            failed_dirs.add(_top_subdir(plan.root, video))
    for sub in plan.subdirs:
        if sub in failed_dirs:
            result.errors.append(f"동영상 이동에 실패해 삭제하지 않음: {sub}")
            continue
        try:
            shutil.rmtree(sub)
            result.deleted_dirs.append(sub)
        except OSError as e:
            result.errors.append(f"삭제 실패: {sub} ({e})")
    return result


def _top_subdir(root: Path, path: Path) -> Path:
    return root / path.relative_to(root).parts[0]
