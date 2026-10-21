"""结果窗双视图（整理 / 原文）与整理明细面板的回归测试。

断言四件事：
  1. 默认展示整理稿，一键可切回逐行原文，内容与原始识别结果逐字一致；
  2. 明细面板能展开，列出真实改动（可追溯）；
  3. 任何宽度下顶部控件都不超出窗口，正文不出现横向溢出；
  4. 复制拿到的是「当前视图」的内容，不是写死的某一版。
"""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab.result_window import ResultWindow  # noqa: E402
from screengrab.tidy import tidy  # noqa: E402

RAW = ("2026 年第三季度经营分析,整体表现符合预期;\r\n"
       "线上渠道贡献了主要增量,线下渠道同比略有下滑，\r\n"
       "主要原因是大客户预算收紧,以及部分项目延后交付。\r\n"
       "\r\n"
       "下一阶段将重点投入三个方向:\r\n"
       "- 提升线上转化率\r\n"
       "- 拓展区域代理商\r\n"
       "- 优化交付流程，把平均周期压缩到十天以内")

META = {"lines": 8, "chars": 160, "avg_score": 0.97, "elapsed": 0.41}


def _widgets_within(win_right: int, items) -> None:
    for label, w in items:
        if w is None or not w.winfo_ismapped():
            continue
        r = w.winfo_rootx() + w.winfo_width()
        assert r <= win_right + 1, f"「{label}」右溢出 {r - win_right}px"
        assert w.winfo_width() + 1 >= w.winfo_reqwidth(), f"「{label}」被挤扁"


def check_width(logical_w: int, logical_h: int) -> None:
    root = tk.Tk()
    root.withdraw()
    copied: list[str] = []
    views: list[str] = []
    rw = ResultWindow(root, on_copy=copied.append, on_retry=lambda: None,
                      on_mode_change=lambda m: None, on_view_change=views.append)
    tidied = tidy(RAW)
    rw.show(RAW, META, tidy_result=tidied, view="tidy")
    width = int(logical_w * rw._scale)
    height = int(logical_h * rw._scale)
    rw.win.geometry(f"{width}x{height}")
    root.update()
    root.update_idletasks()

    # 1) 默认是整理稿
    assert rw.view == "tidy", f"默认视图应为 tidy，实际 {rw.view}"
    assert rw.content() == tidied.text, "展示内容与整理结果不一致"
    assert "整体表现符合预期" in rw.content()
    assert "，\r\n" not in rw.content() and "\r" not in rw.content()

    # 2) 切回原文 → 逐字等于识别结果
    rw.set_view("raw")
    root.update()
    assert rw.content() == RAW, "原文视图内容被改动"
    assert views == ["raw"], f"视图偏好未通知宿主：{views}"

    # 3) 切回整理 → 内容还原
    rw.set_view("tidy")
    root.update()
    assert rw.content() == tidied.text

    # 4) 复制拿当前视图
    rw._copy()
    assert copied[-1] == tidied.text, "复制内容应为当前视图"

    # 5) 明细面板
    assert rw.detail_btn.winfo_ismapped(), f"{width}px 下「整理明细」按钮不可见"
    rw._toggle_details()
    root.update()
    root.update_idletasks()
    assert rw._details_open and rw._details.winfo_ismapped(), "明细面板未展开"
    detail = rw._details_text.get("1.0", "end-1c")
    assert "合并硬换行" in detail, f"明细未记录断行合并：{detail[:120]}"
    assert "内容相似度" in rw._details_note.cget("text")
    x0, x1 = rw._details_text.xview()
    assert x1 >= 0.999, f"{width}px 下明细文本横向溢出：({x0:.2f},{x1:.2f})"
    rw._toggle_details()
    root.update()
    assert not rw._details.winfo_ismapped(), "明细面板未收起"

    # 6) 顶部控件与正文都不越界
    x0, x1 = rw.text.xview()
    assert x1 >= 0.999, f"{width}px 下正文横向溢出：({x0:.2f},{x1:.2f})"
    win_right = rw.win.winfo_rootx() + rw.win.winfo_width()
    _widgets_within(win_right, [
        ("标题", None), ("整理/原文", rw._viewbox), ("排版", rw.mode_btn),
        ("整理明细", rw.detail_btn),
    ] + [(k, b) for k, b in rw._btn.items()])

    print(f"  {logical_w}x{logical_h}: 整理 {tidied.total} 处 · 明细 {len(detail.splitlines())} 行 · "
          f"分段={'显示' if rw._viewbox.winfo_ismapped() else '隐藏'} "
          f"排版={'显示' if rw.mode_btn.winfo_ismapped() else '隐藏'} "
          f"明细={'显示' if rw.detail_btn.winfo_ismapped() else '隐藏'}")

    rw.win.destroy()
    root.update()
    root.destroy()


def check_without_tidy() -> None:
    """整理被关闭（tidy_result=None）时，不应该出现空的整理视图。"""
    root = tk.Tk()
    root.withdraw()
    rw = ResultWindow(root, on_copy=lambda t: None, on_retry=lambda: None,
                      on_mode_change=lambda m: None)
    rw.show("第一行\n第二行", META, tidy_result=None, view="tidy")
    root.update()
    assert rw.view == "raw", "无整理结果时应回退到原文"
    assert not rw._viewbox.winfo_ismapped(), "无整理结果时不应显示视图切换"
    assert not rw.detail_btn.winfo_ismapped(), "无整理结果时不应显示明细按钮"
    assert rw.content() == "第一行\n第二行"
    print("  整理关闭：自动回退原文视图，切换控件隐藏")
    rw.win.destroy()
    root.destroy()


def check_reopen_state() -> None:
    """连续两次识别之间不能残留上一次的明细面板与视图状态。"""
    root = tk.Tk()
    root.withdraw()
    rw = ResultWindow(root, on_copy=lambda t: None, on_retry=lambda: None,
                      on_mode_change=lambda m: None)
    first = tidy(RAW)
    rw.show(RAW, META, tidy_result=first, view="tidy")
    root.update()
    rw._toggle_details()
    root.update()
    assert rw._details_open

    second = tidy("第二段文字,带半角标点。\n换行后的内容。")
    rw.show("第二段文字,带半角标点。\n换行后的内容。", META, tidy_result=second, view="tidy")
    root.update()
    assert not rw._details_open, "新结果应自动收起上一次的明细面板"
    assert not rw._details.winfo_ismapped(), "明细面板残留"
    assert rw.content() == second.text, "新结果未刷新正文"
    assert rw._tidy is second
    print("  连续识别：明细自动收起、正文与整理结果同步更新")
    rw.win.destroy()
    root.destroy()


def main() -> None:
    print("结果窗双视图 / 明细面板：")
    for w, h in [(660, 480), (520, 400), (440, 320)]:
        check_width(w, h)
    check_without_tidy()
    check_reopen_state()
    print("通过：默认整理视图、原文可追溯、明细可展开、多宽度无溢出")


if __name__ == "__main__":
    main()
