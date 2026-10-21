"""生成「复杂版面（图标网格）」的结果窗截图。

运行：python tests/shot_grid.py
输出：docs/img/grid.png（整理视图）、docs/img/grid-details.png（整理明细）
"""
from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from screengrab.layout import build                     # noqa: E402
from screengrab.ocr import OcrService                   # noqa: E402
from screengrab.result_window import ResultWindow       # noqa: E402
from screengrab.tidy import tidy                        # noqa: E402
from tests.fixture import shot_path, skip_note          # noqa: E402
from tests.shot_result import grab                      # noqa: E402


def main() -> None:
    SHOT = shot_path()
    if SHOT is None:
        print(skip_note())
        return
    res = OcrService().recognize(Image.open(SHOT))
    doc = build(res.items)
    result = tidy(doc.text, rows=doc.rows, dropped=doc.dropped)
    meta = res.stats
    meta.update(elapsed=res.elapsed, engine=res.engine,
                structure=doc.note, dropped=doc.dropped)
    print(f"结构 {doc.note} · 整理 {result.total} 处 · 保真 {result.fidelity}")

    root = tk.Tk()
    root.withdraw()
    rw = ResultWindow(root, on_copy=lambda t: None, on_retry=lambda: None,
                      on_mode_change=lambda m: None)
    rw.show(doc.text, meta, tidy_result=result, view="tidy")
    rw.win.geometry("780x520+140+120")
    for _ in range(8):
        root.update()
        time.sleep(0.06)
    grab(rw, ROOT / "docs" / "img" / "grid.png")

    rw._toggle_details()
    rw.win.geometry("780x640+140+120")
    for _ in range(8):
        root.update()
        time.sleep(0.06)
    grab(rw, ROOT / "docs" / "img" / "grid-details.png")

    rw.win.destroy()
    root.destroy()


if __name__ == "__main__":
    main()
