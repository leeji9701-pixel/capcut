"""CLI 진입점.

사용 예:
    python -m capcut_agent.cli doctor
    python -m capcut_agent.cli doctor --drafts-dir "/path/to/CapCut Drafts"
    python -m capcut_agent.cli jumpcut input.mp4 --drafts-dir "/path/to/CapCut Drafts" --name my_draft
    python -m capcut_agent.cli serve
"""

import argparse
import sys

from . import env_check
from .pipeline.draft_builder import build_jumpcut_draft
from .pipeline.silence_detect import compute_keep_ranges


def _cmd_doctor(args: argparse.Namespace) -> int:
    ok = env_check.doctor(drafts_dir=args.drafts_dir)
    return 0 if ok else 1


def _cmd_jumpcut(args: argparse.Namespace) -> int:
    if not env_check.doctor(drafts_dir=args.drafts_dir):
        print("\n환경 점검을 통과하지 못했습니다. 위 항목을 먼저 해결하세요.", file=sys.stderr)
        return 1

    drafts_dir = args.drafts_dir or env_check.default_drafts_dir()
    print(f"\n[1/2] 무음 구간 분석 중: {args.video}")
    duration, keep_ranges = compute_keep_ranges(
        args.video,
        noise_db=args.noise_db,
        min_silence_duration=args.min_silence,
        pad=args.pad,
    )
    kept_total = sum(seg.duration for seg in keep_ranges)
    print(
        f"       원본 {duration:.1f}s -> 유지 {kept_total:.1f}s "
        f"({len(keep_ranges)}개 구간, {duration - kept_total:.1f}s 컷)"
    )

    print(f"[2/2] 드래프트 생성 중: {args.name}")
    save_path = build_jumpcut_draft(
        drafts_dir, args.name, args.video, keep_ranges, allow_replace=args.allow_replace,
    )
    print(f"완료: {save_path}")
    print("CapCut을 열어 드래프트 목록에서 확인하세요 (안 보이면 CapCut 재시작).")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    uvicorn.run("capcut_agent.web.app:app", host=args.host, port=args.port, reload=False)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="capcut_agent")
    parser.add_argument("--drafts-dir", help="CapCut 드래프트 폴더 경로 (미지정 시 OS별 기본 경로 추정)")
    sub = parser.add_subparsers(dest="command", required=True)

    doctor_p = sub.add_parser("doctor", help="환경 점검만 수행")
    doctor_p.set_defaults(func=_cmd_doctor)

    jumpcut_p = sub.add_parser("jumpcut", help="무음 제거 점프컷 드래프트 생성")
    jumpcut_p.add_argument("video", help="입력 영상 파일 (mp4/mov)")
    jumpcut_p.add_argument("--name", required=True, help="생성할 드래프트 이름")
    jumpcut_p.add_argument("--noise-db", type=float, default=-30.0, help="무음 판정 기준 dB (기본 -30)")
    jumpcut_p.add_argument("--min-silence", type=float, default=0.4, help="컷 대상 최소 무음 길이(초, 기본 0.4)")
    jumpcut_p.add_argument("--pad", type=float, default=0.12, help="컷 경계 패딩(초, 기본 0.12)")
    jumpcut_p.add_argument(
        "--no-replace", dest="allow_replace", action="store_false",
        help="동일 이름 드래프트가 있어도 덮어쓰지 않음 (기본은 덮어씀)",
    )
    jumpcut_p.set_defaults(func=_cmd_jumpcut, allow_replace=True)

    serve_p = sub.add_parser("serve", help="로컬 웹 UI 실행 (드래그앤드롭 + 진행 상황 표시)")
    serve_p.add_argument("--host", default="127.0.0.1")
    serve_p.add_argument("--port", type=int, default=8000)
    serve_p.set_defaults(func=_cmd_serve)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
