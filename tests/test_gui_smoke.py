"""GUI 冒烟测试（会短暂弹出窗口，约 3 秒）。

验证：DPI 设置 → 抓屏 → 遮罩构建 → 模拟框选 → 回调坐标正确 → 悬浮球/结果窗可用。
运行：python -m tests.test_gui_smoke
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab import overlay as overlay_mod                    # noqa: E402
from screengrab.capture import grab_all_screens                  # noqa: E402
from screengrab.overlay import RegionOverlay, Toast               # noqa: E402
from screengrab.pill import FloatingPill                          # noqa: E402
from screengrab.result_window import ResultWindow                 # noqa: E402
from screengrab.winutil import (enable_dpi_awareness, enum_monitors,  # noqa: E402
                                set_clipboard_text, virtual_screen)


def test_clipboard() -> None:
    ok = set_clipboard_text("中文 abc 123\n第二行")
    assert ok, "写入剪贴板失败"
    print("[ok] 剪贴板写入")


def test_units() -> None:
    enable_dpi_awareness()
    vs, mons = virtual_screen(), enum_monitors()
    print(f"[ok] 虚拟屏 {vs.w}x{vs.h} @ ({vs.x},{vs.y})  显示器 {len(mons)} 个 "
          f"{[ (m.x, m.y, m.w, m.h) for m in mons ]}")


def test_overlay_drag() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    shot = grab_all_screens()
    print(f"[ok] 抓屏 {shot.image.size}")

    done: list[tuple[int, int, int, int]] = []
    cancelled: list[bool] = []

    # 用假的指针位置驱动框选，避免依赖真实鼠标
    # 调用顺序：构造（定位光标所在屏）→ 按下 → 拖动 → 抬起
    points = [(10, 10), (120, 140), (356, 288), (356, 288)]
    seq = iter(points)
    overlay_mod.cursor_pos = lambda: next(seq)

    ov = RegionOverlay(root, shot, enum_monitors(),
                       on_done=lambda r: done.append(r),
                       on_cancel=lambda: cancelled.append(True))
    root.update()
    ov.on_press()
    ov.on_drag()
    ov.on_release()
    root.update()

    assert done == [(120, 140, 356, 288)], f"框选回调坐标错误: {done}"
    assert ov.panes == [], "遮罩窗口未清理"
    print(f"[ok] 框选回调 {done[0]}")

    # 单击（拖拽距离过小）应视为取消
    seq2 = iter([(500, 500), (501, 501), (501, 501)])
    overlay_mod.cursor_pos = lambda: next(seq2)
    ov2 = RegionOverlay(root, shot, enum_monitors(),
                        on_done=lambda r: done.append(r),
                        on_cancel=lambda: cancelled.append(True))
    root.update()
    ov2.on_press()
    ov2.on_release()
    root.update()
    assert cancelled == [True], "过小的框选应触发取消"
    print("[ok] 过小选区判定为取消")

    # 裁剪坐标与放大倍数核对
    crop = shot.crop(120, 140, 356, 288)
    assert crop.size == (236, 148), crop.size
    print("[ok] 区域裁剪尺寸正确")

    toast = Toast(root, "识别中…", 400, 400, ms=200)
    root.update()
    toast.close()
    print("[ok] 提示条")

    root.destroy()


def test_floating_and_result() -> None:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    clicks: list[str] = []
    pill = FloatingPill(root, on_click=lambda: clicks.append("click"),
                        on_retry=lambda: clicks.append("retry"),
                        on_quit=lambda: clicks.append("quit"),
                        on_save_pos=lambda x, y: clicks.append(f"pos{x},{y}"))
    pill.place(100, 100)
    root.update()
    assert pill.pos == (100, 100)

    rw = ResultWindow(root, on_copy=lambda t: clicks.append("copy"), on_retry=lambda: None,
                      on_mode_change=lambda m: clicks.append(m))
    rw.show("第一行\n  缩进行\t制表符列", {"lines": 2, "chars": 12, "avg_score": 0.98,
                                        "elapsed": 0.42}, anchor=(200, 200))
    root.update()
    assert rw.content().startswith("第一行")
    rw.on_copy("测试")           # 直接触发复制回调，验证通路
    assert "copy" in clicks
    hidden = rw.hide_for_capture()
    assert hidden is True
    root.update()
    rw.win.deiconify()
    rw.hide()
    root.update()
    pill.destroy()
    root.destroy()
    print("[ok] 悬浮球 / 结果窗 构建与交互通路")


if __name__ == "__main__":
    t0 = time.perf_counter()
    test_clipboard()
    test_units()
    test_overlay_drag()
    test_floating_and_result()
    print(f"\n全部 GUI 冒烟测试通过，用时 {time.perf_counter() - t0:.1f}s")
