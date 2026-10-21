"""悬浮按钮：无边框可拖动的胶囊按钮，单击开始框选，右键出菜单。

它同样是「随时调用」的入口之一——热键记不住、或者平板触屏场景下用鼠标点更直接。
"""
from __future__ import annotations

import tkinter as tk

from .overlay import cursor_pos
from .winutil import place_window

W, H = 74, 30
IDLE_BG = "#2563EB"
HOVER_BG = "#1D4ED8"
TEXT = "OCR"


class FloatingPill:
    def __init__(self, root: tk.Misc, on_click, on_retry, on_quit, on_save_pos,
                 hint: str = "", tidy_enabled: bool = True, on_toggle_tidy=None,
                 subject_enabled: bool = True, on_toggle_subject=None):
        self.root = root
        self.on_click = on_click
        self.on_retry = on_retry
        self.on_save_pos = on_save_pos
        self.on_toggle_tidy = on_toggle_tidy or (lambda v: None)
        self.on_toggle_subject = on_toggle_subject or (lambda v: None)
        self.win = tk.Toplevel(root)
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.attributes("-alpha", 0.94)
        self.win.configure(bg="#F3F4F6")  # 供圆角外沿做近似键控色

        self.canvas = tk.Canvas(self.win, width=W, height=H, highlightthickness=0,
                                bd=0, bg=root.cget("bg"), cursor="hand2")
        self.canvas.pack()
        self._shape = self._round_rect(1, 1, W - 1, H - 1, 14, IDLE_BG)
        self.canvas.create_text(W / 2, H / 2, text=TEXT, fill="white",
                                font=("Segoe UI", 10, "bold"))

        self._menu = tk.Menu(self.win, tearoff=0, font=("Microsoft YaHei UI", 9))
        if hint:
            self._menu.add_command(label=hint, state="disabled")
            self._menu.add_separator()
        self._menu.add_command(label="框选识别", command=self.on_click)
        self._menu.add_command(label="重新识别上次区域", command=self.on_retry)
        self._menu.add_separator()
        self._tidy_var = tk.BooleanVar(value=bool(tidy_enabled))
        self._menu.add_checkbutton(label="自动整理识别结果", variable=self._tidy_var,
                                   command=lambda: self.on_toggle_tidy(self._tidy_var.get()))
        self._subject_var = tk.BooleanVar(value=bool(subject_enabled))
        self._menu.add_checkbutton(label="只提取主体文字（大字/彩色）",
                                   variable=self._subject_var,
                                   command=lambda: self.on_toggle_subject(self._subject_var.get()))
        self._menu.add_separator()
        self._menu.add_command(label="退出", command=on_quit)
        self.canvas.bind("<Enter>", lambda e: self._paint(HOVER_BG))
        self.canvas.bind("<Leave>", lambda e: self._paint(IDLE_BG))
        self.canvas.bind("<Button-1>", self._press)
        self.canvas.bind("<B1-Motion>", self._drag)
        self.canvas.bind("<ButtonRelease-1>", self._release)
        self.canvas.bind("<Button-3>", self._popup)
        self._press_pt: tuple[int, int] | None = None
        self._win_pt: tuple[int, int] | None = None
        self._dragging = False
        self.pos: tuple[int, int] = (0, 0)   # 自己记坐标，不依赖 Tk 的 winfo_x

    def _round_rect(self, x0, y0, x1, y1, r, fill):
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y1 - r, x1, y1,
               x1 - r, y1, x0 + r, y1, x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        return self.canvas.create_polygon(pts, smooth=True, splinesteps=12,
                                          fill=fill, outline="")

    def _paint(self, color: str) -> None:
        self.canvas.itemconfigure(self._shape, fill=color)
        if color == HOVER_BG:
            self.canvas.itemconfigure(self._shape, outline=HOVER_BG, width=1)

    # ---------- 拖动 / 点击
    def _press(self, event) -> None:
        self._press_pt = cursor_pos()
        self._win_pt = self.pos
        self._dragging = False

    def _drag(self, _event) -> None:
        if not self._press_pt or not self._win_pt:
            return
        cx, cy = cursor_pos()
        dx, dy = cx - self._press_pt[0], cy - self._press_pt[1]
        if not self._dragging and abs(dx) + abs(dy) > 5:
            self._dragging = True
        if self._dragging:
            self.pos = (self._win_pt[0] + dx, self._win_pt[1] + dy)
            place_window(self.win, self.pos[0], self.pos[1], W, H)

    def _release(self, _event) -> None:
        if self._dragging:
            self.on_save_pos(*self.pos)
        else:
            self.on_click()
        self._dragging = False
        self._press_pt = None

    def _popup(self, event) -> None:
        try:
            self._menu.tk_popup(event.x_root, event.y_root)
        finally:
            self._menu.grab_release()

    # ---------- 显隐
    def place(self, x: int, y: int) -> None:
        self.pos = (int(x), int(y))
        place_window(self.win, self.pos[0], self.pos[1], W, H)
        self.win.deiconify()

    def withdraw(self) -> None:
        self.win.withdraw()

    def destroy(self) -> None:
        try:
            self.win.destroy()
        except tk.TclError:
            pass
