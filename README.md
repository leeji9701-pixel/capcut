# 캡컷 에이전트

한국어 토킹 영상을 넣으면 무음·잔말·NG 컷을 자동으로 잘라내고 세그먼트 단위 자막까지
넣은 CapCut 드래프트를 만들어주는 로컬 웹 도구. 1~5단계 모두 구현됨.

## ⚠️ 반드시 로컬(Mac/Windows)에서 실행하세요

이 코드는 CapCut이 설치된 사용자의 Mac/Windows 컴퓨터에서 실행해야 합니다.
CapCut은 데스크톱 앱이라 서버/클라우드 환경에는 설치할 수 없고, 생성된 드래프트가
실제로 맞는지도 CapCut을 직접 열어 재생해봐야 확인할 수 있습니다.
**빌드가 성공했다고 검증이 끝난 게 아닙니다 — 실제 재생 확인이 검증입니다.**

## 설치

Mac(Apple Silicon):
```bash
pip install -r requirements-mac.txt
```

Windows / 그 외:
```bash
pip install -r requirements-other.txt
```

- ffmpeg가 필요합니다.
  - Mac: `brew install ffmpeg`
  - Windows: `winget install ffmpeg`

## 사용법

### 웹 UI (권장)

```bash
python -m capcut_agent.cli serve
```

브라우저에서 `http://127.0.0.1:8000` 접속 후:

1. 환경 점검 결과 확인 (ffmpeg/CapCut 드래프트 폴더/디스크)
2. 영상을 드래그앤드롭 (또는 클릭해서 선택)
3. 무음 감지 -> 대본 추출(Whisper) -> 잔말/NG 판단 -> 드래프트 생성 순서로 진행 상황이 표시됨
4. 완료되면 영상 미리보기에서 재생하며 `[` 로 보존 구간 시작, `]` 로 끝을 표시
   (잔말/NG/무음으로 판단됐어도 이 구간은 잘리지 않음)
5. "보존 구간 적용해서 다시 생성" 클릭 -> ffmpeg/Whisper를 다시 돌리지 않고 즉시 재생성
6. CapCut을 열어(안 보이면 재시작) 실제로 재생해서 확인

### CLI (UI 없이, 무음 제거만)

```bash
python -m capcut_agent.cli doctor
python -m capcut_agent.cli jumpcut input.mp4 --drafts-dir "/path/to/CapCut Drafts" --name my_draft
```

CapCut 드래프트 폴더 경로가 자동으로 안 잡히면, CapCut 앱의
`전역 설정 > 草稿位置(드래프트 위치)`에서 실제 경로를 확인해 `--drafts-dir`로 지정하세요.

### 옵션 (무음 감지)

- `--noise-db` (기본 -30): 이 dB보다 조용하면 무음으로 판정. 배경 소음이 있으면 더 낮게(-40 등).
- `--min-silence` (기본 0.4초): 이 길이 이상 지속된 무음만 컷 대상.
- `--pad` (기본 0.12초): 무음 컷 경계에 남기는 여유. 단어가 씹히면 늘리세요 (잔말/NG 컷에는
  적용 안 됨 - 그건 세그먼트 그대로 정확히 잘라냄).

## 테스트

```bash
pip install pytest fastapi httpx
pytest tests/
```

합성 영상(ffmpeg 즉석 생성)과 가짜(fake) ASR 백엔드로 무음 탐지, 잔말/NG 판단,
타임라인 리매핑, 드래프트 JSON 구조, 웹 API(SSE 포함) 전체 흐름을 자동 검증합니다.
다만 이 자동 테스트는 draft JSON의 구조적 정합성만 확인할 뿐, CapCut에서 실제로 열리고
재생되는지, Whisper가 실제 한국어를 정확히 인식하는지는 검증하지 못합니다 — 그건
사용자가 직접 확인해야 합니다.

## 구조

```
capcut_agent/
  env_check.py            # OS 감지, ffmpeg/드래프트 폴더/디스크 점검
  cli.py                   # doctor / jumpcut / serve
  pipeline/
    silence_detect.py      # ffmpeg silencedetect -> 발화 구간 계산
    asr.py                 # Whisper 대본 추출 (mlx-whisper / faster-whisper), content-hash 캐시
    filler_ng.py            # 전체 대본 기반 잔말/NG 세그먼트 판단
    timeline_remap.py       # 원본<->컷 편집 후 타임라인 변환, 구간 대수(merge/subtract)
    draft_builder.py        # pycapcut으로 드래프트(영상+자막) 생성
    pipeline.py              # 위 전부를 순서대로 묶는 오케스트레이션 (SSE/CLI 공용)
  web/
    app.py                   # FastAPI (업로드, SSE, 재생성 API)
    jobs.py                  # job 상태 관리
    static/index.html         # 정적 HTML 1장 (드래그앤드롭 + stepper + 프리뷰/마킹)
```

draft JSON은 직접 만들지 않고 [pycapcut](https://github.com/GuanYixuan/pyCapCut) 라이브러리를
사용합니다 (같은 저자의 [pyJianYingDraft](https://github.com/GuanYixuan/pyJianYingDraft)의
CapCut 전용 포크). 알려진 함정: 메인(가장 아래) 비디오 트랙의 첫 세그먼트는 반드시
타임라인 0초부터 시작해야 하며, 어긋나면 CapCut이 강제로 0초로 당겨버림 - 드래프트 빌더가
이를 보장하도록 짜여 있습니다.

## 잔말/NG 판단 기준 (튜닝 필요)

`capcut_agent/pipeline/filler_ng.py`의 `FILLER_WORDS`/`NG_MARKERS` 목록은 시작점일 뿐입니다.
실제 채널 말투에 맞춰 계속 다듬어야 정확도가 올라갑니다. 오탐(잘못 잘림)은 웹 UI의
보존 구간 마킹(`[` / `]`)으로 즉시 되살릴 수 있습니다.

## 이 프로젝트를 만들 때 확인이 안 된 부분 (솔직하게)

- 이 저장소는 클라우드 컨테이너(Linux)에서 개발되어 **CapCut 앱 자체가 없습니다.** 생성된
  드래프트가 실제로 CapCut에서 열리고 재생되는지는 사용자의 로컬 환경에서 처음 확인하게 됩니다.
- **mlx-whisper(Mac 트랙)는 Apple Silicon 전용이라 여기서 설치·실행 검증이 불가능했습니다.**
  faster-whisper(Windows/기타 트랙)만 실제로 모델을 돌려 API를 확인했고, mlx-whisper 연동은
  공개 문서 기준으로 작성만 했습니다 - Mac에서 처음 실행할 때 문제가 있으면 알려주세요.
- 실제 Whisper 모델 다운로드는 이 세션의 네트워크 정책상 huggingface.co가 막혀 있어
  못 해봤습니다. ASR 모듈은 의존성 주입(가짜 백엔드)으로 캐싱/락/데이터 흐름만 검증했습니다.
