"""GUI: 폴더를 끌어다 놓거나 경로를 입력하고 [정리하기]를 누른다.

실행: python -m insta360_flatten
(선택) 드래그앤드롭: pip install tkinterdnd2
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext

from .core import execute, make_plan

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:  # 드래그앤드롭 없이도 동작
    TkinterDnD = None


class App:
    def __init__(self, initial: str | None = None):
        self.root = TkinterDnD.Tk() if TkinterDnD else tk.Tk()
        self.root.title("인스타360 폴더 정리기")
        self.root.geometry("640x420")

        tip = ("폴더를 이 창에 끌어다 놓거나, 경로를 입력/선택하세요."
               if TkinterDnD else
               "경로를 입력하거나 [찾아보기]로 선택하세요. "
               "(끌어다 놓기: pip install tkinterdnd2)")
        tk.Label(self.root, text=tip, anchor="w").pack(fill="x", padx=12, pady=(12, 4))

        row = tk.Frame(self.root)
        row.pack(fill="x", padx=12)
        self.path_var = tk.StringVar(value=initial or "")
        tk.Entry(row, textvariable=self.path_var).pack(side="left", fill="x", expand=True)
        tk.Button(row, text="찾아보기", command=self.browse).pack(side="left", padx=(6, 0))

        tk.Button(self.root, text="정리하기", height=2, command=self.run).pack(
            fill="x", padx=12, pady=8)

        self.log = scrolledtext.ScrolledText(self.root, height=15, state="disabled")
        self.log.pack(fill="both", expand=True, padx=12, pady=(0, 12))

        if TkinterDnD:
            self.root.drop_target_register(DND_FILES)
            self.root.dnd_bind("<<Drop>>", self.on_drop)

    def write(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.path_var.set(d)

    def on_drop(self, event):
        paths = self.root.tk.splitlist(event.data)
        if paths:
            self.path_var.set(paths[0])
            self.run()

    def run(self):
        raw = self.path_var.get().strip().strip('"')
        if not raw:
            messagebox.showwarning("안내", "폴더 경로를 넣어주세요.")
            return
        try:
            plan = make_plan(Path(raw))
        except NotADirectoryError as e:
            messagebox.showerror("오류", str(e))
            return
        if not plan.subdirs:
            self.write(f"[{plan.root}] 하위 폴더가 없습니다. 할 일이 없어요.")
            return

        msg = (f"폴더: {plan.root}\n\n"
               f"• 꺼낼 동영상: {len(plan.videos)}개\n"
               f"• 삭제할 하위 폴더: {len(plan.subdirs)}개\n"
               f"• 함께 삭제될 기타 파일(썸네일 등): {plan.other_files}개\n\n"
               "삭제한 폴더는 복구할 수 없습니다. 진행할까요?")
        if not messagebox.askyesno("확인", msg):
            self.write("취소했습니다.")
            return

        result = execute(plan)
        for _, dst in result.moved:
            self.write(f"이동: {dst.name}")
        for err in result.errors:
            self.write(f"⚠ {err}")
        self.write(f"완료 — 동영상 {len(result.moved)}개 이동, "
                   f"폴더 {len(result.deleted_dirs)}개 삭제, 오류 {len(result.errors)}건\n")

    def mainloop(self):
        self.root.mainloop()


def main():
    # 폴더를 실행 파일/스크립트 아이콘에 끌어다 놓으면 argv로 경로가 들어온다.
    App(sys.argv[1] if len(sys.argv) > 1 else None).mainloop()


if __name__ == "__main__":
    main()
