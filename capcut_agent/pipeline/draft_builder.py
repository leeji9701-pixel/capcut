"""남길 발화 구간(Interval) 목록으로부터 CapCut 점프컷 드래프트를 생성한다.

pycapcut (https://github.com/GuanYixuan/pyCapCut) 위에 얹어서 만든다 - draft_content.json을
직접 손으로 조립하지 않는다. 알려진 함정: 메인(가장 아래) 비디오 트랙의 첫 세그먼트는
반드시 타임라인 0초부터 시작해야 하며, 어긋나면 CapCut이 강제로 0초로 당겨버린다.
이 빌더는 keep_ranges를 이어붙여 첫 세그먼트가 항상 0초에서 시작하도록 보장한다.
"""

from typing import List

import pycapcut as cc
from pycapcut import trange

from .silence_detect import Interval

SEC_TO_US = 1_000_000


def build_jumpcut_draft(
    drafts_dir: str,
    draft_name: str,
    video_path: str,
    keep_ranges: List[Interval],
    allow_replace: bool = True,
) -> str:
    """점프컷 드래프트를 생성하고 저장된 draft_content.json 경로를 반환한다.

    Args:
        drafts_dir: CapCut 드래프트 폴더 (예: ".../CapCut Drafts")
        draft_name: 생성할 드래프트 이름 (CapCut 목록에 표시될 이름)
        video_path: 원본 영상 파일 경로
        keep_ranges: 남길 발화 구간 목록 (초 단위), 시간순 정렬되어 있어야 함
        allow_replace: 동일한 이름의 드래프트가 있으면 덮어쓸지 여부
    """
    if not keep_ranges:
        raise ValueError("남길 구간이 없습니다 (keep_ranges가 비어있음)")

    material = cc.VideoMaterial(video_path)

    draft_folder = cc.DraftFolder(drafts_dir)
    script = draft_folder.create_draft(
        draft_name, material.width, material.height, allow_replace=allow_replace,
    )
    script.add_track(cc.TrackType.video)

    cursor_us = 0
    for seg in keep_ranges:
        start_us = round(seg.start * SEC_TO_US)
        end_us = min(round(seg.end * SEC_TO_US), material.duration)
        duration_us = end_us - start_us
        if duration_us <= 0:
            continue

        video_segment = cc.VideoSegment(
            material,
            trange(cursor_us, duration_us),
            source_timerange=trange(start_us, duration_us),
        )
        script.add_segment(video_segment)
        cursor_us += duration_us

    script.save()
    return script.save_path
