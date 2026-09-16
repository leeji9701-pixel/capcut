import shutil
import subprocess

import pytest

FFMPEG_AVAILABLE = shutil.which("ffmpeg") is not None

requires_ffmpeg = pytest.mark.skipif(not FFMPEG_AVAILABLE, reason="ffmpeg가 설치되어 있지 않음")


@pytest.fixture
def synthetic_video(tmp_path):
    """[말][무음][말][무음] 패턴의 6초짜리 합성 영상을 만든다.

    말 구간: 0-1.5s, 3-4.5s (440Hz 톤)
    무음 구간: 1.5-3s, 4.5-6s
    """
    out = tmp_path / "synthetic.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=blue:s=320x240:d=6:r=25",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=6",
        "-filter_complex", "[1:a]volume='if(lt(mod(t,3),1.5),1,0)':eval=frame[a]",
        "-map", "0:v", "-map", "[a]",
        "-shortest", "-c:v", "libx264", "-c:a", "aac", "-t", "6",
        str(out), "-loglevel", "error",
    ]
    subprocess.run(cmd, check=True)
    return str(out)
