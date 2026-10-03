# 인스타360 폴더 정리기

Insta360 클라우드에서 받은 영상이 파일마다 폴더에 하나씩 들어 있는 게 불편해서 만든 도구입니다.
폴더를 넣으면 **하위 폴더 속 동영상을 전부 그 폴더 바로 아래로 꺼내고, 하위 폴더는 삭제**합니다.

```
다운로드/                     다운로드/
├─ VID_001/                   ├─ VID_001.mp4
│  ├─ VID_001.mp4      →      ├─ VID_002.mp4
│  └─ thumb.jpg               └─ VID_002 (1).mp4   ← 이름이 겹치면 번호를 붙임
└─ VID_002/
   ├─ VID_002.mp4
   └─ sub/VID_002.mp4
```

## 실행

```bash
pip install tkinterdnd2      # 선택: 창에 폴더를 끌어다 놓기
python -m insta360_flatten
```

1. 폴더를 창에 끌어다 놓거나, 경로 입력 / [찾아보기]로 선택 후 [정리하기]
2. 꺼낼 동영상 수·삭제할 폴더 수를 확인하는 창에서 [예]

## 주의

- 동영상 확장자: mp4, mov, insv, avi, mkv, m4v, mts, m2ts, wmv, webm, 3gp
- 하위 폴더에 있던 **동영상 외 파일(썸네일, .lrv 미리보기 등)은 폴더와 함께 영구 삭제**됩니다.
- 동영상 이동에 실패한 폴더는 삭제하지 않고 그대로 둡니다.
- 최상위 폴더에 원래 있던 파일은 건드리지 않습니다.

## 실행 파일(.exe / .app)로 만들기 (선택)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name 인스타360정리기 --collect-all tkinterdnd2 run_insta360_flatten.py
```

`dist/` 폴더에 생성된 실행 파일 아이콘 위에 폴더를 끌어다 놓아도 그 경로로 열립니다.
