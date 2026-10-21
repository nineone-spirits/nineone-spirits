"""结果窗换行与自适应回归测试。

关键断言：任何内容、任何窗口宽度下，Text 的横向可视范围都必须覆盖全部内容
（xview 恒为 0.0~1.0），且四个按钮始终完整落在窗口内。
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab.result_window import ResultWindow  # noqa: E402

LONG_URL = "https://example.com/path?" + "a" * 240
LONG_TOKEN = "Q" * 300
CJK = "这是一段用来验证连续中文字符换行的长文本，中间没有任何空格，" * 6

CONTENT = "\n".join([
    "第三季度经营分析报告",
    LONG_URL,
    "连续长单词：" + LONG_TOKEN,
    CJK,
    "渠道\tGMV（万元）\t同比\t备注\t" + "很长的备注内容" * 6,
    "结尾一行",
])


def check(logical_width: int, logical_height: int) -> None:
    root = tk.Tk()
    root.withdraw()
    rw = ResultWindow(root, on_copy=lambda t: None, on_retry=lambda: None,
                      on_mode_change=lambda m: None)
    rw.show(CONTENT, {"lines": 12, "chars": 900, "avg_score": 0.98, "elapsed": 0.5})
    width = int(logical_width * rw._scale)
    height = int(logical_height * rw._scale)
    rw.win.geometry(f"{width}x{height}")
    root.update()
    root.update_idletasks()

    x0, x1 = rw.text.xview()
    wrap = str(rw.text.cget("wrap"))
    assert wrap == "word", f"wrap 应为 word，实际 {wrap}"
    assert x1 >= 0.999, f"{width}px 下内容横向溢出：xview=({x0:.3f}, {x1:.3f})"

    win_right = rw.win.winfo_rootx() + rw.win.winfo_width()
    for label, btn in rw._btn.items():
        assert btn.winfo_ismapped(), f"{width}px 下按钮「{label}」被隐藏"
        assert btn.winfo_width() + 1 >= btn.winfo_reqwidth(), (
            f"{width}px 下按钮「{label}」被挤扁："
            f"实际 {btn.winfo_width()} < 需要 {btn.winfo_reqwidth()}")
        r = btn.winfo_rootx() + btn.winfo_width()
        assert r <= win_right + 1, f"{width}px 下按钮「{label}」右溢出 {r - win_right}px"

    if rw._hint.winfo_ismapped():
        assert rw._hint.winfo_width() + 1 >= rw._hint.winfo_reqwidth(), \
            f"{width}px 下说明文字被裁切"

    hint_visible = rw._hint.winfo_ismapped()
    print(f"  {logical_width}x{logical_height}（物理 {width}x{height}）: "
          f"wrap={wrap} xview=({x0:.2f},{x1:.2f}) "
          f"meta=「{rw.meta_var.get()}」 hint={'显示' if hint_visible else '收起'}")
    rw.win.destroy()
    root.update()
    root.destroy()


def main() -> None:
    print("结果窗换行 / 自适应：")
    for w, h in [(660, 460), (520, 400), (440, 320), (380, 240)]:
        check(w, h)
    print("通过：所有宽度下均无横向溢出，按钮完整可见")


if __name__ == "__main__":
    main()
