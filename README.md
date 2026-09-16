# 캡컷 에이전트 (1단계: 점프컷)

한국어 토킹 영상을 넣으면 무음 구간을 잘라낸 CapCut 드래프트를 자동으로 만들어주는 도구.
아직 UI는 없고, 무음 제거 점프컷 코어 로직만 있는 1단계 상태.

## ⚠️ 반드시 로컬(Mac/Windows)에서 실행하세요

이 코드는 CapCut이 설치된 사용자의 Mac/Windows 컴퓨터에서 실행해야 합니다.
CapCut은 데스크톱 앱이라 서버/클라우드 환경에는 설치할 수 없고, 생성된 드래프트가
실제로 맞는지도 CapCut을 직접 열어 재생해봐야 확인할 수 있습니다.

## 설치

```bash
pip install -r requirements.txt
```

- ffmpeg가 필요합니다.
  - Mac: `brew install ffmpeg`
  - Windows: `winget install ffmpeg`

## 사용법

먼저 환경 점검:

```bash
python -m capcut_agent.cli doctor
```

CapCut 드래프트 폴더 경로가 자동으로 안 잡히면, CapCut 앱의
`전역 설정 > 草稿位置(드래프트 위치)`에서 실제 경로를 확인해 `--drafts-dir`로 지정하세요.

무음 제거 점프컷 드래프트 생성:

```bash
python -m capcut_agent.cli jumpcut input.mp4 --drafts-dir "/path/to/CapCut Drafts" --name my_draft
```

생성 후 CapCut을 열어(안 보이면 재시작) `my_draft`를 재생해 컷 지점이 자연스러운지 확인하세요.
**빌드가 성공했다고 검증이 끝난 게 아닙니다 — 실제 재생 확인이 검증입니다.**

### 옵션

- `--noise-db` (기본 -30): 이 dB보다 조용하면 무음으로 판정. 배경 소음이 있으면 더 낮게(-40 등).
- `--min-silence` (기본 0.4초): 이 길이 이상 지속된 무음만 컷 대상.
- `--pad` (기본 0.12초): 컷 경계에 남기는 여유. 단어가 씹히면 늘리세요.

## 테스트

```bash
pip install pytest
pytest tests/
```

합성 영상(ffmpeg로 즉석 생성)으로 무음 탐지 로직과, 생성된 드래프트의 타임라인이
빈틈/겹침 없이 이어지는지, 메인 트랙 첫 세그먼트가 0초에서 시작하는지를 자동 검증합니다.
다만 이 자동 테스트는 draft JSON의 구조적 정합성만 확인할 뿐, CapCut에서 실제로 열리고
재생되는지는 검증하지 못합니다 — 그건 사용자가 직접 확인해야 합니다.

## 구조

```
capcut_agent/
  env_check.py           # OS 감지, ffmpeg/드래프트 폴더/디스크 점검
  pipeline/
    silence_detect.py    # ffmpeg silencedetect -> 발화 구간 계산
    draft_builder.py      # pycapcut으로 점프컷 드래프트 생성
  cli.py                  # 커맨드라인 진입점
```

draft JSON은 직접 만들지 않고 [pycapcut](https://github.com/GuanYixuan/pyCapCut) 라이브러리를
사용합니다 (같은 저자의 [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)의
CapCut 전용 포크).

## 다음 단계 (아직 미구현)

1. ~~silence_detect + build_draft~~ (완료)
2. FastAPI + 정적 HTML (drag/drop + SSE stepper)
3. Whisper로 전체 대본 추출 + 세그먼트 단위 자막
4. 전체 대본 기반 잔말/NG 컷 통합
5. 영상 프리뷰 + 보존 구간 사용자 마킹
