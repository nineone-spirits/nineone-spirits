"""应用主控：把「热键 / 悬浮球 → 截屏 → 框选 → OCR → 结果窗」串成一条状态机。

线程模型：
  · 主线程（Tk mainloop）负责所有 UI：遮罩、悬浮球、结果窗；
  · 热键线程只做一件事——把「开始框选」这个意图丢进队列；
  · OCR 工作线程跑识别，完成后同样把回调丢回队列。
  Tk 不是线程安全的，所有 UI 变更必须回到主线程，队列是唯一的跨线程通道。
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox

from .capture import grab_all_screens, release_modifiers
from .config import load_config, save_config
from .hotkey import HotkeyManager
from .layout import build, stats
from .ocr import OcrService
from .overlay import RegionOverlay, Toast
from .pill import W as PILL_W, FloatingPill
from .result_window import ResultWindow
from . import subject as subject_mod
from .tidy import tidy
from .winutil import enum_monitors, set_clipboard_text, virtual_screen


class TextGrabberApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("屏幕取字 · NineOne Spirits")
        self.root.report_callback_exception = self._on_tk_error

        self.queue: "queue.Queue[callable]" = queue.Queue()
        self.ocr = OcrService(min_score=float(self.cfg["min_score"]))
        self.shot = None
        self.overlay: RegionOverlay | None = None
        self.toast: Toast | None = None
        self._busy = False
        self._last_items: list = []
        self._last_meta_dict: dict = {}
        self._last_raw: str = ""
        self._last_tidy = None
        self._hidden_result = False
        self._subject: subject_mod.Subject | None = None
        self._use_subject = True        # 这次识别是否按主体过滤展示
        self.last_region: list[int] | None = self.cfg.get("last_region")

        self.result = ResultWindow(self.root, on_copy=self.copy_to_clipboard,
                                   on_retry=self.retry_last_region,
                                   on_mode_change=self.change_layout_mode,
                                   on_view_change=self.change_view,
                                   on_toggle_subject=self.toggle_subject_view)
        self.pill = FloatingPill(self.root, on_click=self.start_capture,
                                 on_retry=self.retry_last_region,
                                 on_quit=self.quit, on_save_pos=self.save_pill_pos,
                                 hint=f"热键 {_pretty_hotkey(self.cfg['hotkey'])}",
                                 tidy_enabled=self.cfg.get("tidy_enabled", True),
                                 on_toggle_tidy=self.toggle_tidy,
                                 subject_enabled=subject_mod.parse_rule(
                                     self.cfg.get("subject_filter", "auto"))["mode"] != "off",
                                 on_toggle_subject=self.toggle_subject_filter)
        self.hotkeys = HotkeyManager({
            1: (str(self.cfg["hotkey"]), lambda: self.queue.put(self.start_capture)),
            2: (str(self.cfg["hotkey_retry"]), lambda: self.queue.put(self.retry_last_region)),
        })

    # ------------------------------------------------------------ 生命周期
    def run(self) -> None:
        self.pill.place(*self._pill_initial_pos())
        self.hotkeys.start()
        threading.Thread(target=self._warmup, daemon=True, name="ocr-warmup").start()
        self.root.after(50, self._poll_queue)
        self.root.after(900, self._report_hotkey_state)
        try:
            self.root.mainloop()
        finally:
            self.hotkeys.stop()

    def _report_hotkey_state(self) -> None:
        """热键被别的软件占用时明确告知，而不是让用户以为程序没启动。"""
        failed = self.hotkeys.failed
        if not failed:
            return
        x, y = self.pill.pos
        Toast(self.root, f"热键 {failed[0]} 被占用，可点悬浮球识别", x + 90, y + 6, ms=3200)

    def _warmup(self) -> None:
        """提前加载 ONNX 模型，避免第一次框选卡 1~2 秒。"""
        try:
            self.ocr.warmup()
        except Exception:
            pass

    def quit(self) -> None:
        try:
            self.pill.destroy()
            if self.overlay:
                self.overlay.cancel()
        finally:
            self.hotkeys.stop()
            self.root.quit()
            self.root.destroy()

    def _on_tk_error(self, exc, val, tb) -> None:
        messagebox.showerror("文字提取", f"发生未预期的错误：\n{val}")

    # ------------------------------------------------------------ 主线程队列
    def _poll_queue(self) -> None:
        while True:
            try:
                job = self.queue.get_nowait()
            except queue.Empty:
                break
            try:
                job()
            except Exception as exc:  # 单个任务失败不拖垮主循环
                self._notify_error(str(exc))
        self.root.after(45, self._poll_queue)

    # ------------------------------------------------------------ 框选流程
    def start_capture(self) -> None:
        if self.overlay is not None or self._busy:
            return
        release_modifiers()               # 松开 ctrl/alt，防止输入法/宿主软件误判
        self._hidden_result = self.result.hide_for_capture()
        self.pill.withdraw()
        self.root.update_idletasks()
        # 等一帧，确保自己的窗口真正从 DWM 合成层消失后再抓屏
        self.root.after(90, self._grab_then_overlay)

    def _grab_then_overlay(self) -> None:
        try:
            self.shot = grab_all_screens()
        except Exception as exc:
            self.pill.place(*self._pill_initial_pos())
            self._notify_error(f"屏幕抓取失败：{exc}")
            return
        self.overlay = RegionOverlay(self.root, self.shot, enum_monitors(),
                                     on_done=self._on_region_selected,
                                     on_cancel=self._on_capture_cancelled)

    def _on_capture_cancelled(self) -> None:
        self.overlay = None
        self._restore_ui()

    def _on_region_selected(self, rect: tuple[int, int, int, int]) -> None:
        self.overlay = None
        self._restore_ui()
        self.last_region = list(rect)
        self.cfg["last_region"] = self.last_region
        save_config(self.cfg)

        x0, y0, x1, y1 = rect
        self.toast = Toast(self.root, "识别中…", (x0 + x1) // 2, y1, ms=0)
        image = self.shot.crop(x0, y0, x1, y1)
        self._run_ocr(image, rect)

    def _run_ocr(self, image, rect) -> None:
        self._busy = True
        self._current_rect = rect

        def worker():
            try:
                result = self.ocr.recognize(image)
                self.queue.put(lambda: self._on_ocr_done(result, rect))
            except Exception as exc:
                msg = str(exc)
                self.queue.put(lambda: self._on_ocr_failed(msg))

        threading.Thread(target=worker, daemon=True, name="ocr-worker").start()

    def _on_ocr_done(self, result, rect) -> None:
        self._busy = False
        self._close_toast()
        if not result.items:
            self._notify_error("没有识别到文字，试试放大框选范围或换个区域。")
            return
        self._last_items = result.items
        # 主体判定放在 OCR 之后、拼版之前：它只决定「用哪些框」，
        # 不改变识别本身，所以之后切换「主体 / 全部」不需要重跑 OCR。
        self._subject = subject_mod.select(
            result.items, self.cfg.get("subject_filter", "auto"))
        self._use_subject = bool(self._subject.applied)
        self._last_raw, self._last_tidy = self._compose()

        if not self._active_items():
            self._notify_error("主体过滤把文字全滤掉了，已回退为全部文字。")
            self._use_subject = False
            self._last_raw, self._last_tidy = self._compose()

        meta = self._last_meta_dict
        meta["elapsed"] = result.elapsed
        meta["engine"] = result.engine
        self.result.show(self._last_raw, meta, anchor=(rect[0], rect[3]),
                         tidy_result=self._last_tidy,
                         view=self.cfg.get("result_view", "tidy"),
                         subject=self._subject_state())

    def _subject_state(self) -> dict:
        sub = self._subject
        if sub is None:
            return {"applied": False, "on": False, "kept": 0, "total": 0, "label": ""}
        return {"applied": bool(sub.applied), "on": bool(self._use_subject),
                "kept": len(sub.kept), "total": sub.total, "label": sub.label}

    def _active_items(self) -> list:
        sub = self._subject
        if sub is not None and sub.applied and self._use_subject:
            return sub.kept
        return self._last_items

    def _compose(self) -> tuple[str, object]:
        """一次算出「原文」和「整理稿」。

        整理固定吃逐行（verbatim）结果——它需要靠「这一行有没有写满」来判断
        换行是排版截断还是真的分段，先合段就丢掉这个信息了。原文则按用户
        选的排版模式生成，两者互不影响。

        两次 build 的差别只在 `keep_glyphs`：原文视图保留 OCR 认到的所有字符
        （包括图标被识成「W」这种），整理稿剔除徽标字符并把这件事写进明细，
        这样「原文 → 整理稿」的每一处差异都能对上。
        """
        items = self._active_items()
        base = build(items, "verbatim")
        raw = build(items, self.cfg["layout_mode"], keep_glyphs=True).text
        meta = stats(items)
        meta["structure"] = base.note
        meta["dropped"] = base.dropped
        meta["subject"] = self._subject_state()
        self._last_meta_dict = meta
        tidied = None
        if self.cfg.get("tidy_enabled", True):
            try:
                tidied = tidy(base.text, rows=base.rows, dropped=base.dropped)
            except Exception:
                tidied = None       # 整理失败不影响主流程，降级为直接展示原文
        return raw, tidied

    def _on_ocr_failed(self, message: str) -> None:
        self._busy = False
        self._close_toast()
        hint = ""
        if "rapidocr" in message.lower() or "onnxruntime" in message.lower():
            hint = "\n\n缺少 OCR 依赖，请在命令行执行：pip install -r requirements.txt"
        self._notify_error(f"识别失败：{message}{hint}")

    # ------------------------------------------------------------ 结果操作
    def retry_last_region(self) -> None:
        """对上一次的区域重新识别（内容滚动/更新的场景很常用）。"""
        if self._busy or self.overlay is not None:
            return
        if not self.last_region:
            self.start_capture()
            return
        x0, y0, x1, y1 = self.last_region
        release_modifiers()
        self.result.hide_for_capture()
        self.pill.withdraw()
        self.root.update_idletasks()

        def grab_and_run():
            try:
                shot = grab_all_screens()
                self.shot = shot
                self._restore_ui()
                self.toast = Toast(self.root, "重新识别中…", (x0 + x1) // 2, y1, ms=0)
                self._run_ocr(shot.crop(x0, y0, x1, y1), (x0, y0, x1, y1))
            except Exception as exc:
                self._restore_ui()
                self._notify_error(f"屏幕抓取失败：{exc}")

        self.root.after(90, grab_and_run)

    def change_layout_mode(self, mode: str) -> None:
        """切换排版模式时只重新拼版，不重跑 OCR（0 成本，用户可来回对比）。"""
        self.cfg["layout_mode"] = mode
        save_config(self.cfg)
        if self._last_items:
            self._last_raw = build(self._active_items(), mode, keep_glyphs=True).text
            self.result.update_raw(self._last_raw)

    def change_view(self, view: str) -> None:
        """记住用户偏好：下次识别直接打开整理稿或原文。"""
        self.cfg["result_view"] = view
        save_config(self.cfg)

    def toggle_tidy(self, enabled: bool) -> None:
        """悬浮球右键菜单里开关自动整理，开关只影响之后的识别结果。"""
        self.cfg["tidy_enabled"] = bool(enabled)
        save_config(self.cfg)
        if not self._last_items:
            return
        self._last_raw, self._last_tidy = self._compose()
        self.result.show(self._last_raw, self._last_meta_dict,
                         tidy_result=self._last_tidy,
                         view="tidy" if enabled else "raw",
                         subject=self._subject_state())

    def toggle_subject_filter(self, enabled: bool) -> None:
        """悬浮球菜单「只提取主体文字」：总开关，同时作用于当前这屏结果。"""
        self.cfg["subject_filter"] = "auto" if enabled else "off"
        save_config(self.cfg)
        if not self._last_items:
            return
        self._subject = subject_mod.select(self._last_items, self.cfg["subject_filter"])
        self._use_subject = bool(self._subject.applied)
        self._render()

    def toggle_subject_view(self) -> None:
        """结果窗上的按钮：在「只看主体」和「全部文字」之间切换，不重跑 OCR。"""
        if self._subject is None or not self._subject.applied:
            return
        self._use_subject = not self._use_subject
        self._render()

    def _render(self) -> None:
        """按当前开关状态重算两版文本并刷新结果窗（成本只有拼版，毫秒级）。"""
        self._last_raw, self._last_tidy = self._compose()
        self.result.show(self._last_raw, self._last_meta_dict,
                         tidy_result=self._last_tidy,
                         subject=self._subject_state())

    def copy_to_clipboard(self, text: str) -> None:
        if not text.strip():
            return
        ok = set_clipboard_text(text)
        x, y = _cursor()
        Toast(self.root, "已复制" if ok else "复制失败", x, y, ms=1000)

    # ------------------------------------------------------------ 小工具
    def _restore_ui(self) -> None:
        self.pill.place(*self.pill.pos)
        if getattr(self, "_hidden_result", False):
            self.result.win.deiconify()
            self._hidden_result = False

    def _pill_initial_pos(self) -> tuple[int, int]:
        pos = self.cfg.get("pill_pos")
        if isinstance(pos, (list, tuple)) and len(pos) == 2:
            return int(pos[0]), int(pos[1])
        vs = virtual_screen()
        return vs.x + vs.w - PILL_W - 36, vs.y + vs.h - 120

    def save_pill_pos(self, x: int, y: int) -> None:
        self.cfg["pill_pos"] = [x, y]
        save_config(self.cfg)

    def _close_toast(self) -> None:
        if self.toast:
            self.toast.close()
            self.toast = None

    def _notify_error(self, message: str) -> None:
        self._close_toast()
        x, y = _cursor()
        Toast(self.root, message.split("\n")[0][:60], x, y, ms=2200)


def _cursor() -> tuple[int, int]:
    from .overlay import cursor_pos
    return cursor_pos()


def _pretty_hotkey(spec: str) -> str:
    """"ctrl+alt+q" -> "Ctrl+Alt+Q"，用于界面展示。"""
    return "+".join(p.capitalize() if len(p) > 1 else p.upper()
                    for p in str(spec).split("+"))
