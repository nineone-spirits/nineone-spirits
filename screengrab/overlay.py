"""框选遮罩层。

实现要点：
  · 每个显示器一个无边框置顶 Toplevel，背景铺该显示器「压暗后的截图」，
    选区处再把原图裁一块盖上去，得到干净的聚光灯效果（不用半透明窗口，无闪烁）。
  · 指针坐标一律用 Win32 GetCursorPos 取物理像素，不依赖 Tk 的 winfo_rootx
    （overrideredirect + SetWindowPos 之后 Tk 的窗口坐标记录可能与实际不一致）。
"""
from __future__ import annotations

import ctypes
import tkinter as tk
from ctypes import wintypes

from PIL import Image, ImageEnhance, ImageTk

from .capture import ScreenShot
from .winutil import Monitor, focus_window, place_window

user32 = ctypes.WinDLL("user32", use_last_error=True)

DIM_FACTOR = 0.42          # 选区外压暗系数（平滑压暗，比网点抖动观感干净）
ACCENT = "#3B82F6"
LABEL_BG = "#111827"
MAGNIFIER = 14              # 放大镜取样边长（屏幕像素）
MAGNIFIER_PX = 126          # 放大镜显示边长


class _Point(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


def cursor_pos() -> tuple[int, int]:
    p = _Point()
    user32.GetCursorPos(ctypes.byref(p))
    return p.x, p.y


class _Pane:
    """单个显示器上的遮罩窗口。"""

    def __init__(self, parent: tk.Misc, shot: ScreenShot, mon: Monitor, overlay: "RegionOverlay"):
        self.mon = mon
        self.overlay = overlay
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg="black")

        self.canvas = tk.Canvas(self.win, highlightthickness=0, bd=0, bg="black",
                                cursor="crosshair", width=mon.w, height=mon.h)
        self.canvas.pack(fill="both", expand=True)

        crop = shot.crop(mon.x, mon.y, mon.x + mon.w, mon.y + mon.h)
        # 底层放「压暗后的整屏」，选区用原图裁一块盖上去 = 自然的聚光灯效果
        self._dim_photo = ImageTk.PhotoImage(
            ImageEnhance.Brightness(crop).enhance(DIM_FACTOR))
        self.canvas.create_image(0, 0, image=self._dim_photo, anchor="nw")
        self._sel_photo: ImageTk.PhotoImage | None = None
        self._sel_img = self.canvas.create_image(0, 0, anchor="nw", state="hidden")

        self._border = self.canvas.create_rectangle(0, 0, 0, 0, outline=ACCENT, width=1)
        self._label_bg = self.canvas.create_rectangle(0, 0, 0, 0, fill=LABEL_BG, outline="")
        self._label = self.canvas.create_text(0, 0, anchor="nw", fill="white",
                                              font=("Segoe UI", 9, "bold"))
        self._mag_bg = self.canvas.create_rectangle(0, 0, 0, 0, outline=ACCENT, width=1,
                                                    fill="black", state="hidden")
        self._mag_img = self.canvas.create_image(0, 0, anchor="nw", state="hidden")
        self._mag_cross = [self.canvas.create_line(0, 0, 0, 0, fill=ACCENT, state="hidden")
                           for _ in range(2)]
        self._mag_photo: ImageTk.PhotoImage | None = None

        place_window(self.win, mon.x, mon.y, mon.w, mon.h)
        # SetWindowPos 已让系统把窗口显示出来，但 Tk 内部仍认为它未映射，
        # 会推迟 Canvas 重绘（拖拽时看不到选区变化）。显式 deiconify 补上映射状态。
        self.win.deiconify()
        self.win.update_idletasks()
        self.canvas.bind("<Button-1>", overlay.on_press)
        self.canvas.bind("<B1-Motion>", overlay.on_drag)
        self.canvas.bind("<ButtonRelease-1>", overlay.on_release)
        self.canvas.bind("<Button-3>", lambda e: overlay.cancel())
        self.canvas.bind("<Escape>", lambda e: overlay.cancel())
        self.win.bind("<Escape>", lambda e: overlay.cancel())

    # ---------- 绘制
    def _hide_selection(self) -> None:
        self.canvas.itemconfigure(self._sel_img, state="hidden")
        for item in (self._border, self._label_bg, self._label):
            self.canvas.itemconfigure(item, state="hidden")

    def draw_selection(self, rect: tuple[int, int, int, int] | None) -> None:
        w, h = self.mon.w, self.mon.h
        if rect is None:
            self._hide_selection()
            return

        gx0, gy0, gx1, gy1 = rect
        lx0 = max(0, gx0 - self.mon.x)
        ly0 = max(0, gy0 - self.mon.y)
        lx1 = min(w, gx1 - self.mon.x)
        ly1 = min(h, gy1 - self.mon.y)
        if lx1 - lx0 < 1 or ly1 - ly0 < 1:   # 选区不在本屏（或尚未拉开）
            self._hide_selection()
            return

        # 提亮选区：直接从原始截图裁一块画上去（压暗层之上），像素级还原
        bright = self.overlay.shot.crop(self.mon.x + lx0, self.mon.y + ly0,
                                        self.mon.x + lx1, self.mon.y + ly1)
        self._sel_photo = ImageTk.PhotoImage(bright)
        self.canvas.coords(self._sel_img, lx0, ly0)
        self.canvas.itemconfigure(self._sel_img, image=self._sel_photo, state="normal")

        self.canvas.coords(self._border, lx0, ly0, lx1, ly1)
        self.canvas.itemconfigure(self._border, state="normal")

        label = f"{gx1 - gx0} × {gy1 - gy0}"
        self.canvas.coords(self._label, 0, 0)
        self.canvas.itemconfigure(self._label, text=label, state="normal")
        bx0, by0, bx1, by1 = self.canvas.bbox(self._label) or (0, 0, 0, 0)
        tw, th = bx1 - bx0 + 12, by1 - by0 + 6
        px = lx0 if ly0 > th + 6 else lx0 + 2
        py = ly0 - th - 6 if ly0 > th + 6 else ly0 + 2
        px = min(max(0, px), max(0, w - tw))
        self.canvas.coords(self._label_bg, px, py, px + tw, py + th)
        self.canvas.coords(self._label, px + 6, py + 3)
        self.canvas.itemconfigure(self._label_bg, state="normal")

    def draw_magnifier(self, gx: int, gy: int, visible: bool) -> None:
        """光标处像素级放大镜，用于对齐细小的行距/字符边缘。"""
        items = [self._mag_bg, self._mag_img, *self._mag_cross]
        if not visible:
            for it in items:
                self.canvas.itemconfigure(it, state="hidden")
            return
        half = MAGNIFIER // 2
        patch = self.overlay.shot.crop(gx - half, gy - half, gx + half, gy + half)
        patch = patch.resize((MAGNIFIER_PX, MAGNIFIER_PX), Image.NEAREST)
        self._mag_photo = ImageTk.PhotoImage(patch)

        # 默认放光标右下，贴边时自动翻到另一侧
        ox, oy = gx + 18, gy + 18
        if ox + MAGNIFIER_PX + 8 > self.mon.x + self.mon.w:
            ox = gx - MAGNIFIER_PX - 18
        if oy + MAGNIFIER_PX + 8 > self.mon.y + self.mon.h:
            oy = gy - MAGNIFIER_PX - 18
        lx, ly = ox - self.mon.x, oy - self.mon.y
        self.canvas.coords(self._mag_img, lx + 1, ly + 1)
        self.canvas.itemconfigure(self._mag_img, image=self._mag_photo, state="normal")
        self.canvas.coords(self._mag_bg, lx, ly, lx + MAGNIFIER_PX + 2, ly + MAGNIFIER_PX + 2)
        self.canvas.itemconfigure(self._mag_bg, state="normal")
        cx, cy = lx + 1 + MAGNIFIER_PX / 2, ly + 1 + MAGNIFIER_PX / 2
        self.canvas.coords(self._mag_cross[0], cx, ly + 1, cx, ly + MAGNIFIER_PX)
        self.canvas.coords(self._mag_cross[1], lx + 1, cy, lx + MAGNIFIER_PX, cy)
        for it in self._mag_cross:
            self.canvas.itemconfigure(it, state="normal")

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass


class RegionOverlay:
    """框选流程控制器：按下 → 拖拽 → 释放回调 rect(全局物理像素)。"""

    def __init__(self, parent: tk.Misc, shot: ScreenShot, monitors: list[Monitor],
                 on_done, on_cancel=None):
        self.shot = shot
        self.on_done = on_done
        self.on_cancel = on_cancel
        self.start: tuple[int, int] | None = None
        self.current: tuple[int, int] | None = None
        self._closed = False
        self.panes = [_Pane(parent, shot, m, self) for m in monitors]

        # 选中光标所在屏并抢焦点，保证 Esc 可用
        cx, cy = cursor_pos()
        target = next((p for p in self.panes
                       if p.mon.x <= cx < p.mon.x + p.mon.w and p.mon.y <= cy < p.mon.y + p.mon.h),
                      self.panes[0] if self.panes else None)
        if target:
            focus_window(target.win)
        for p in self.panes:
            p.draw_selection(None)

    # ---------- 事件
    def on_press(self, _event=None) -> None:
        self.start = cursor_pos()
        self.current = self.start
        self._redraw(magnifier=True)

    def on_drag(self, _event=None) -> None:
        if self.start is None:
            return
        self.current = cursor_pos()
        self._redraw(magnifier=True)

    def on_release(self, _event=None) -> None:
        if self.start is None:
            return
        self.current = cursor_pos()
        rect = self._rect()
        self._close()
        if rect[2] - rect[0] < 5 or rect[3] - rect[1] < 5:
            if self.on_cancel:
                self.on_cancel()
            return
        self.on_done(rect)

    def cancel(self) -> None:
        if self._closed:
            return
        self._close()
        if self.on_cancel:
            self.on_cancel()

    # ---------- 内部
    def _rect(self) -> tuple[int, int, int, int]:
        (x0, y0), (x1, y1) = self.start or (0, 0), self.current or (0, 0)
        return (min(x0, x1), min(y0, y1), max(x0, x1), max(y0, y1))

    def _redraw(self, magnifier: bool = False) -> None:
        if self.start is None:
            for p in self.panes:
                p.draw_selection(None)
            return
        rect = self._rect()
        cx, cy = self.current or (0, 0)
        for p in self.panes:
            p.draw_selection(rect)
            inside = (p.mon.x <= cx < p.mon.x + p.mon.w and p.mon.y <= cy < p.mon.y + p.mon.h)
            p.draw_magnifier(cx, cy, magnifier and inside)

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for p in self.panes:
            p.destroy()
        self.panes.clear()


class Toast:
    """轻量浮现提示（识别中/已复制），无边框、自动消失。"""

    def __init__(self, parent: tk.Misc, text: str, x: int, y: int, ms: int = 1200):
        self.win = tk.Toplevel(parent)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        frame = tk.Frame(self.win, bg="#111827", padx=14, pady=8)
        frame.pack()
        tk.Label(frame, text=text, bg="#111827", fg="#F9FAFB",
                 font=("Microsoft YaHei UI", 10)).pack()
        self.win.update_idletasks()
        w, h = self.win.winfo_reqwidth(), self.win.winfo_reqheight()
        place_window(self.win, x - w // 2, y - h - 12, w, h)
        self.win.deiconify()
        if ms > 0:
            self.win.after(ms, self.close)

    def close(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
