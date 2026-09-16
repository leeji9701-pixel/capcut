"""로컬 실행 환경 점검. 이 모듈은 사용자의 로컬 Mac/Windows 머신에서 실행되는 것을
전제로 한다 (클라우드 빌드 컨테이너가 아니라) - CapCut 앱과 드래프트 폴더는 로컬에만 존재한다.
"""

import os
import platform
import shutil
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str
    fix_hint: Optional[str] = None


def detect_platform() -> str:
    system = platform.system()
    if system == "Darwin":
        return "mac"
    if system == "Windows":
        return "windows"
    return "unsupported"


def default_drafts_dir(system: Optional[str] = None) -> Optional[str]:
    """CapCut 기본 드래프트 폴더 추정 경로.

    설치 방식/버전에 따라 달라질 수 있으므로 어디까지나 best-effort 기본값이며,
    CapCut 앱의 `전역 설정 > 草稿位置(드래프트 위치)`에서 실제 경로를 확인해
    --drafts-dir 로 직접 지정하는 것을 권장한다.
    """
    system = system or detect_platform()
    home = os.path.expanduser("~")
    if system == "mac":
        return os.path.join(home, "Movies", "CapCut", "User Data", "Projects", "com.lveditor.draft")
    if system == "windows":
        local_appdata = os.environ.get("LOCALAPPDATA", os.path.join(home, "AppData", "Local"))
        return os.path.join(local_appdata, "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return None


def check_ffmpeg() -> CheckResult:
    path = shutil.which("ffmpeg")
    if path:
        return CheckResult("ffmpeg", True, f"발견: {path}")
    system = detect_platform()
    if system == "mac":
        hint = "brew install ffmpeg"
    elif system == "windows":
        hint = "winget install ffmpeg"
    else:
        hint = "https://ffmpeg.org/download.html 에서 설치"
    return CheckResult("ffmpeg", False, "설치되어 있지 않음", hint)


def check_drafts_dir(drafts_dir: Optional[str]) -> CheckResult:
    system = detect_platform()
    if system == "unsupported":
        return CheckResult(
            "capcut_drafts_dir", False,
            "CapCut은 Mac/Windows 데스크톱 앱입니다. 이 스크립트는 CapCut이 설치된 로컬 머신에서 실행해야 합니다.",
        )

    path = drafts_dir or default_drafts_dir(system)
    if path and os.path.isdir(path):
        return CheckResult("capcut_drafts_dir", True, f"발견: {path}")

    return CheckResult(
        "capcut_drafts_dir", False,
        f"경로를 찾을 수 없음: {path}",
        "CapCut 실행 -> 전역 설정 -> 草稿位置(드래프트 위치) 확인 후 --drafts-dir 로 직접 지정하세요. "
        "CapCut을 한 번도 실행하지 않았다면 먼저 실행해 드래프트 폴더를 생성하세요.",
    )


def check_disk_space(path: str, min_gb: float = 5.0) -> CheckResult:
    check_path = path if os.path.exists(path) else os.path.dirname(path) or "."
    try:
        usage = shutil.disk_usage(check_path)
    except OSError as e:
        return CheckResult("disk_space", False, f"확인 실패: {e}")
    free_gb = usage.free / (1024 ** 3)
    ok = free_gb >= min_gb
    return CheckResult("disk_space", ok, f"여유 공간 {free_gb:.1f}GB (최소 {min_gb}GB 필요)")


def run_all(drafts_dir: Optional[str] = None) -> List[CheckResult]:
    results = [check_ffmpeg()]
    drafts_check = check_drafts_dir(drafts_dir)
    results.append(drafts_check)
    space_target = drafts_dir or default_drafts_dir() or "."
    results.append(check_disk_space(space_target))
    return results


def doctor(drafts_dir: Optional[str] = None) -> bool:
    """점검 결과를 출력하고, 모든 항목이 통과했는지 여부를 반환한다."""
    system = detect_platform()
    print(f"플랫폼: {system} ({platform.system()} {platform.machine()})")
    all_ok = True
    for result in run_all(drafts_dir):
        mark = "OK" if result.ok else "FAIL"
        print(f"[{mark}] {result.name}: {result.detail}")
        if not result.ok:
            all_ok = False
            if result.fix_hint:
                print(f"       -> {result.fix_hint}")
    return all_ok


if __name__ == "__main__":
    import sys
    ok = doctor()
    sys.exit(0 if ok else 1)
