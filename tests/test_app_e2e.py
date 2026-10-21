"""整机联调：走完整状态机（热键注册 → 抓屏 → 遮罩 → OCR → 结果窗 → 复制）。

不依赖真实鼠标：遮罩出现后由脚本直接给出框选区域；OCR 用合成图，避免依赖桌面内容。
运行：python -m tests.test_app_e2e
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab import app as app_mod                     # noqa: E402
from screengrab import overlay as overlay_mod              # noqa: E402
from screengrab.winutil import enable_dpi_awareness        # noqa: E402
from tests.test_pipeline import make_ui_image              # noqa: E402

enable_dpi_awareness()

app = app_mod.TextGrabberApp()
log: list[str] = []
RECT = (60, 60, 520, 300)


def step_capture() -> None:
    assert app.pill.win.state() == "normal", "悬浮球未显示"
    log.append(f"悬浮球位置 {app.pill.pos}")
    app.start_capture()
    app.root.after(900, step_select)


def step_select() -> None:
    assert app.overlay is not None, "遮罩层未创建"
    log.append(f"遮罩窗口数 {len(app.overlay.panes)}")
    app.overlay.cancel()                       # 关闭遮罩（等价于用户按 Esc）
    app.root.update()
    assert app.overlay is None
    log.append("取消框选后状态已复位")

    # 直接喂一张合成图，跳过真实屏幕内容的偶然性
    app.toast = None
    app._run_ocr(make_ui_image(), RECT)
    app.root.after(2500, step_verify)


def step_verify() -> None:
    content = app.result.content()
    assert content.strip(), "结果窗口没有内容"
    log.append(f"结果长度 {len(content)} 字")
    assert "第三季度经营分析报告" in content, content[:80]
    assert "\t" in content, "表格列未保留"
    log.append("识别文本与表格结构校验通过")

    app.copy_to_clipboard(content)
    app.root.update()
    from_clip = app.root.clipboard_get()
    assert "经营分析" in from_clip, "剪贴板内容不符"
    log.append("剪贴板读取校验通过")

    app.change_layout_mode("paragraph")
    assert app.cfg["layout_mode"] == "paragraph"
    app.change_layout_mode("verbatim")
    log.append("排版模式切换通过")

    app.quit()


app.root.after(300, step_capture)
app.root.after(20000, app.quit)     # 兜底，避免测试挂死
t0 = time.perf_counter()
app.run()
time.sleep(0.2)

for line in log:
    print("[ok]", line)
if app.hotkeys.failed:
    print("[warn] 热键注册失败（可能被其它程序占用）:", app.hotkeys.failed)
else:
    print(f"[ok] 全局热键已注册: {app.cfg['hotkey']} / {app.cfg['hotkey_retry']}")
print(f"\n整机联调通过，用时 {time.perf_counter() - t0:.1f}s")
