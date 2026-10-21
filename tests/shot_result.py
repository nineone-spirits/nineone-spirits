"""生成文档用的结果窗截图（整理视图 / 整理明细）。

运行：python tests/shot_result.py
输出：docs/img/result.png、docs/img/tidy-details.png
"""
from __future__ import annotations

import ctypes
import sys
import time
import tkinter as tk
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from screengrab.result_window import ResultWindow  # noqa: E402
from screengrab.tidy import tidy                   # noqa: E402


def frame_rect(win: tk.Toplevel) -> tuple[int, int, int, int]:
    """取窗口真实外框（含标题栏）。

    直接用 winfo_rootx/width 会在 DWM 阴影与边框上偏几像素，
    连带把桌面抓进来；GetWindowRect 拿到的是精确的物理像素矩形。
    """
    hwnd = int(win.wm_frame(), 16)
    r = wintypes.RECT()
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right, r.bottom

RAW = """项目周报(2026年第41周)

本周完成了三项主要工作,分别是接口联调、性能
优化和灰度发布。接口联调覆盖了12个外部服务，
平均响应时间从380ms 降到 210ms;性能优化主
要针对数据库慢查询,新增了4个联合索引。

下周计划:
- 推进第二阶段的容量压测
- 补齐监控告警的覆盖盲区
- 完成 2026 年度预算的初稿编制"""

META = {"lines": 11, "chars": 178, "avg_score": 0.982, "elapsed": 0.66}


def grab(rw: ResultWindow, out: Path) -> None:
    """抓窗口外框。

    这台机器是 125% 缩放，Python 进程被 DPI 虚拟化：Tk 报告的屏幕是
    1536×864，而 ImageGrab 返回物理像素 1920×1080。两者差一个比例，
    直接用 Tk 坐标去裁会整体偏移，所以先抓全屏再按比例换算裁剪。
    """
    win = rw.win
    win.update_idletasks()
    left, top, right, bottom = frame_rect(win)
    full = ImageGrab.grab(all_screens=True)
    k = full.width / win.winfo_screenwidth()
    # 去掉 DWM 的 8px 半透明边框，否则四周会漏出桌面背景
    pad = int(8 * k)
    img = full.crop((int(left * k) + pad, int(top * k),
                     int(right * k) - pad, int(bottom * k) - pad))
    img.save(out)
    print(f"  saved {out.name}  {img.size[0]}x{img.size[1]}  (DPI ×{k:.2f})")


def main() -> None:
    raw = RAW.replace("\n", "\r\n")
    result = tidy(raw)
    print(f"整理 {result.total} 处 / {result.paragraphs} 段 / {result.fidelity}")

    root = tk.Tk()
    root.withdraw()
    rw = ResultWindow(root, on_copy=lambda t: None, on_retry=lambda: None,
                      on_mode_change=lambda m: None)
    rw.show(raw, META, tidy_result=result, view="tidy")
    rw.win.geometry("760x470+140+120")
    for _ in range(8):
        root.update()
        time.sleep(0.06)

    grab(rw, ROOT / "docs" / "img" / "result.png")

    rw._toggle_details()
    rw.win.geometry("760x640+140+120")
    for _ in range(8):
        root.update()
        time.sleep(0.06)
    grab(rw, ROOT / "docs" / "img" / "tidy-details.png")

    rw.win.destroy()
    root.destroy()


if __name__ == "__main__":
    main()
