"""结果窗口：可编辑文本（自动折行、无横向滚动）+ 一键复制 + 整理/原文双视图。

用普通带标题栏的窗口（而非无边框浮层）的两个原因：
  · 中文编辑依赖输入法候选框，标准窗口的焦点/输入上下文最稳定；
  · 用户常常需要对结果做二次修改，可拖动/可最小化更符合直觉。

双视图的可追溯性设计：
  识别完成后默认展示「整理」后的文本；顶部「原文」按钮一键切回逐行原始
  识别结果，两者随时对照。「整理明细」展开后列出每一类改动（合并了几处
  断行、把哪些半角标点转成了全角、纠正了哪些错字）及其前后样例，并给出
  内容骨架相似度——即「改了什么、改了多少」都可核对，不是黑箱。
"""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

from .tidy import TidyResult

BG = "#FFFFFF"
MUTED = "#6B7280"
ACCENT = "#2563EB"
BORDER = "#E5E7EB"
FONT = ("Microsoft YaHei UI", 10)
FONT_SM = ("Microsoft YaHei UI", 9)


class ResultWindow:
    def __init__(self, root: tk.Misc, on_copy, on_retry, on_mode_change,
                 on_view_change=None, on_toggle_subject=None):
        self.root = root
        self.on_copy = on_copy
        self.on_retry = on_retry
        self.on_mode_change = on_mode_change
        self.on_view_change = on_view_change or (lambda v: None)
        self.on_toggle_subject = on_toggle_subject or (lambda: None)
        self.win: tk.Toplevel | None = None
        self.text: tk.Text | None = None
        self.meta_var: tk.StringVar | None = None
        self.mode_btn: tk.Button | None = None
        self.detail_btn: tk.Button | None = None
        self.subj_btn: tk.Button | None = None
        self._subject: dict = {"applied": False, "on": False, "kept": 0,
                               "total": 0, "label": ""}
        self.mode = "verbatim"
        self.view = "raw"                 # tidy | raw
        self._geometry: str | None = None
        self._vsb: ttk.Scrollbar | None = None
        self._footer: tk.Frame | None = None
        self._hint: tk.Label | None = None
        self._viewbox: tk.Frame | None = None
        self._vb: dict[str, tk.Button] = {}
        self._details: tk.Frame | None = None
        self._details_text: tk.Text | None = None
        self._details_open = False
        self._tidy: TidyResult | None = None
        self._raw = ""
        self._compact = False
        self._density = None
        self._scale = 1.0
        self._hint_shown = True
        self._two_rows = False
        self._wide_mode = True
        self._wide_detail = True
        self._meta_full = ""
        self._meta_short = ""
        self._structure = ""

    # ---------- 构建
    def _build(self) -> None:
        win = tk.Toplevel(self.root)
        win.title("文字提取")
        win.configure(bg=BG)
        win.attributes("-topmost", True)
        # 字体按系统 DPI 放大，窗口尺寸也要跟着放大，否则 150% 缩放下字会显得又大又挤。
        self._scale = max(1.0, win.winfo_fpixels("1i") / 96.0)
        win.geometry(self._geometry or f"{int(660 * self._scale)}x{int(480 * self._scale)}")
        win.minsize(int(380 * self._scale), int(260 * self._scale))
        win.protocol("WM_DELETE_WINDOW", self.hide)

        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=14, pady=(12, 6))
        header.columnconfigure(2, weight=1)      # 吸收多余宽度，把控件推到右侧
        tk.Label(header, text="识别结果", bg=BG, fg="#111827",
                 font=("Microsoft YaHei UI", 12, "bold")).grid(row=0, column=0, sticky="w")
        self.meta_var = tk.StringVar(value="")
        tk.Label(header, textvariable=self.meta_var, bg=BG, fg=MUTED,
                 font=FONT_SM).grid(row=0, column=1, sticky="w", padx=(10, 0), pady=(3, 0))

        self._viewbox = tk.Frame(header, bg="#F3F4F6")
        self._viewbox.grid(row=0, column=3, sticky="e", padx=(8, 0))
        for key, label in (("tidy", "整理"), ("raw", "原文")):
            b = tk.Button(self._viewbox, text=label, relief="flat", bd=0, padx=10, pady=3,
                          cursor="hand2", font=FONT_SM,
                          command=lambda k=key: self.set_view(k))
            b.pack(side="left", padx=1, pady=1)
            self._vb[key] = b

        self.mode_btn = tk.Button(header, text="排版：逐行", command=self._toggle_mode,
                                  bg="#F3F4F6", fg="#111827", activebackground="#E5E7EB",
                                  relief="flat", bd=0, padx=10, pady=3, cursor="hand2",
                                  font=FONT_SM)
        self.mode_btn.grid(row=0, column=4, sticky="e", padx=(8, 0))
        self.detail_btn = tk.Button(header, text="整理明细", command=self._toggle_details,
                                    bg="#EFF6FF", fg=ACCENT, activebackground="#DBEAFE",
                                    activeforeground=ACCENT, relief="flat", bd=0,
                                    padx=10, pady=3, cursor="hand2", font=FONT_SM)
        self.detail_btn.grid(row=0, column=5, sticky="e", padx=(6, 0))

        # 主体过滤按钮：只有真发生了过滤才出现，点一下在「只看主体 / 全部」之间切换，
        # 让用户随时能确认被滤掉的是什么，不至于变成黑箱。
        self.subj_btn = tk.Button(header, text="主体", command=self.on_toggle_subject,
                                  bg="#EFF6FF", fg=ACCENT, activebackground="#DBEAFE",
                                  activeforeground=ACCENT, relief="flat", bd=0,
                                  padx=10, pady=3, cursor="hand2", font=FONT_SM)
        self.subj_btn.grid(row=0, column=6, sticky="e", padx=(6, 0))
        self.subj_btn.grid_remove()

        body = tk.Frame(win, bg=BG)
        # wrap="word"：Tk 8.6 在超长无空格串（URL / base64）与连续中文处会退化为按字符断行，
        # 因此不必再提供横向滚动条 —— 任何内容都能完整折行显示，不会被截断。
        self.text = tk.Text(body, wrap="word", font=FONT, undo=True, padx=12, pady=10,
                            relief="flat", bg="#FCFCFD", fg="#111827",
                            insertbackground="#111827", selectbackground="#BFDBFE",
                            selectforeground="#111827", highlightthickness=1,
                            highlightbackground=BORDER, highlightcolor=ACCENT,
                            spacing1=2, spacing2=1, spacing3=2)
        self._vsb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=self._on_yscroll)
        self.text.grid(row=0, column=0, sticky="nsew")
        self._vsb.grid(row=0, column=1, sticky="ns")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self._details = self._build_details(body)
        self._details.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(6, 0))
        self._details.grid_remove()

        # 先给按钮行占位（side=bottom），再让文本区吃掉剩余空间，
        # 否则窗口变小时 pack 会把按钮行挤到可视区之外。
        footer = tk.Frame(win, bg=BG)
        footer.pack(side="bottom", fill="x", padx=14, pady=(0, 12))
        self._footer = footer
        self._order = ["复制全部", "复制并关闭", "重新识别", "关闭"]
        self._btn = {}
        self._btn["关闭"] = self._button(footer, "关闭", self.hide)
        self._btn["重新识别"] = self._button(footer, "重新识别", self._retry)
        self._btn["复制并关闭"] = self._button(footer, "复制并关闭", self._copy_and_close, primary=True)
        self._btn["复制全部"] = self._button(footer, "复制全部", self._copy, primary=True)
        self._hint = tk.Label(footer, text="Ctrl+Enter 复制", bg=BG,
                              fg="#9CA3AF", font=FONT_SM)
        self._hint.grid(row=0, column=0, sticky="w")
        for idx, key in enumerate(self._order):
            self._btn[key].grid(row=0, column=idx + 1, padx=(8, 0), sticky="")
        footer.columnconfigure(0, weight=1)

        body.pack(fill="both", expand=True, padx=14, pady=(0, 8))

        self.text.bind("<Control-Return>", lambda e: (self._copy(), "break")[1])
        self.text.bind("<Escape>", lambda e: self.hide())
        win.bind("<Escape>", lambda e: self.hide())
        win.bind("<Configure>", self._on_resize)
        self.win = win

    def _build_details(self, parent: tk.Misc) -> tk.Frame:
        """整理明细面板：默认收起，展开后列出每类改动的计数与前后样例。"""
        box = tk.Frame(parent, bg="#F9FAFB", highlightthickness=1,
                       highlightbackground=BORDER)
        bar = tk.Frame(box, bg="#F9FAFB")
        bar.pack(fill="x", padx=10, pady=(6, 2))
        tk.Label(bar, text="整理明细", bg="#F9FAFB", fg="#111827",
                 font=("Microsoft YaHei UI", 9, "bold")).pack(side="left")
        self._details_note = tk.Label(bar, text="", bg="#F9FAFB", fg=MUTED, font=FONT_SM)
        self._details_note.pack(side="left", padx=8)
        tk.Button(bar, text="收起", command=self._toggle_details, bg="#F9FAFB",
                  fg=MUTED, relief="flat", bd=0, cursor="hand2",
                  font=FONT_SM).pack(side="right")

        self._details_text = tk.Text(box, wrap="word", height=5, font=FONT_SM,
                                     bg="#F9FAFB", fg="#374151", relief="flat",
                                     bd=0, padx=10, pady=4, spacing1=1,
                                     spacing3=1, cursor="arrow")
        self._details_text.pack(fill="both", expand=True)
        return box

    # ---------- 自适应
    def _on_yscroll(self, first: str, last: str) -> None:
        """纵向滚动条常驻：自动隐藏会改变文本宽度 → 重新折行 → 再触发本回调，
        在临界内容长度上容易来回翻转，反而显示错乱。"""
        if self._vsb is not None:
            self._vsb.set(first, last)

    def _on_resize(self, event=None) -> None:
        if self.win is None or event is None or event.widget is not self.win:
            return
        self._remember_geometry(event)
        # 断点用逻辑像素，这样 100% / 125% / 150% 缩放下的观感一致
        self._apply_density(event.width / self._scale)

    def _apply_density(self, width: float) -> None:
        """按窗口宽度（逻辑像素）分档：≥620 显示完整元信息，≥600 显示快捷键提示，
        <480 把按钮排成 2×2，<560 收起排版按钮，避免被挤成一条细缝。"""
        state = (width >= 600, width >= 620, width < 480, width >= 560, width >= 430)
        if state == self._density:      # 状态没变就不重排，避免 Configure 反复触发
            return
        self._density = state
        show_hint, show_meta, two_rows, wide_mode, wide_detail = state

        if self._hint is not None and show_hint != self._hint_shown:
            self._hint_shown = show_hint
            if show_hint:
                self._hint.grid()
            else:
                self._hint.grid_remove()

        if two_rows != self._two_rows:
            self._two_rows = two_rows
            self._layout_footer(two_rows)

        compact = not show_meta
        if self.meta_var is not None and compact != self._compact:
            self._compact = compact
            self.meta_var.set(self._meta_short if compact else self._meta_full)

        self._wide_mode = wide_mode
        self._wide_detail = wide_detail
        self._sync_controls()

    def _layout_footer(self, compact: bool) -> None:
        """窄窗口下按钮改排成 2×2 大按钮，比硬挤成一行更好点；宽窗口保持右对齐。"""
        f = self._footer
        if f is None:
            return
        if compact:
            f.columnconfigure(0, weight=1, uniform="btn")
            f.columnconfigure(1, weight=1, uniform="btn")
            for idx, key in enumerate(self._order):
                self._btn[key].grid_configure(row=idx // 2, column=idx % 2, sticky="ew",
                                              padx=(0, 6) if idx % 2 == 0 else (0, 0),
                                              pady=(0, 6))
        else:
            f.columnconfigure(0, weight=1, uniform="")
            for idx, key in enumerate(self._order):
                self._btn[key].grid_configure(row=0, column=idx + 1, sticky="",
                                              padx=(8, 0), pady=0)

    def _button(self, parent, label, cmd, primary=False):
        if primary:
            return tk.Button(parent, text=label, command=cmd, bg=ACCENT, fg="white",
                             activebackground="#1D4ED8", activeforeground="white",
                             relief="flat", bd=0, padx=14, pady=6, cursor="hand2",
                             font=FONT)
        return tk.Button(parent, text=label, command=cmd, bg="#F3F4F6", fg="#111827",
                         activebackground="#E5E7EB", relief="flat", bd=0, padx=14, pady=6,
                         cursor="hand2", font=FONT)

    def _remember_geometry(self, event=None) -> None:
        if self.win and event and event.widget is self.win and self.win.state() == "normal":
            self._geometry = self.win.geometry()

    # ---------- 视图同步
    def _sync_controls(self) -> None:
        """视图相关控件的显隐与高亮集中在这里，避免散落在各处状态不一致。"""
        has_tidy = self._tidy is not None and bool(self._tidy.text.strip())

        if self._viewbox is not None:
            if has_tidy:
                self._viewbox.grid()
            else:
                self._viewbox.grid_remove()
        for key, btn in self._vb.items():
            on = key == self.view and has_tidy
            btn.configure(bg=ACCENT if on else "#F3F4F6",
                          fg="white" if on else "#374151",
                          activebackground="#1D4ED8" if on else "#E5E7EB",
                          activeforeground="white" if on else "#111827")

        # 排版按钮只对「原文」有意义：整理视图已经做过合段，再切换排版会互相打架
        show_mode = self._wide_mode and (not has_tidy or self.view == "raw")
        if self.mode_btn is not None:
            if show_mode:
                self.mode_btn.grid()
            else:
                self.mode_btn.grid_remove()

        total = self._tidy.total if has_tidy else 0
        show_detail = self._wide_detail and has_tidy and total > 0
        if self.detail_btn is not None:
            if show_detail:
                self.detail_btn.configure(
                    text="收起明细" if self._details_open else f"整理明细 {total}")
                self.detail_btn.grid()
            else:
                self.detail_btn.grid_remove()

        self._sync_subject_button()

    def _sync_subject_button(self) -> None:
        """主体按钮：显示「主体 3/8」表示正在只看主体，「全部 8」表示已展开。"""
        if self.subj_btn is None:
            return
        st = self._subject or {}
        show = bool(st.get("applied")) and int(st.get("total", 0)) > 1 and self._wide_detail
        if not show:
            self.subj_btn.grid_remove()
            return
        on = bool(st.get("on"))
        kept, total = int(st.get("kept", 0)), int(st.get("total", 0))
        label = st.get("label") or ""
        self.subj_btn.configure(text=(f"主体 {kept}/{total}" if on else f"全部 {total}"),
                                bg="#EFF6FF" if on else "#F3F4F6",
                                fg=ACCENT if on else "#374151",
                                activebackground="#DBEAFE" if on else "#E5E7EB",
                                activeforeground=ACCENT if on else "#111827")
        # 悬停提示用按钮文本表达不了「按什么规则判的主体」，放到明细面板的备注里
        self._subject_label = label
        self.subj_btn.grid()

    def _paint(self) -> None:
        if not self.text:
            return
        content = self._current_text()
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self._apply_tab_stops(content)
        self.text.edit_reset()
        self.text.mark_set("insert", "1.0")
        self.text.see("1.0")

    def _apply_tab_stops(self, content: str) -> None:
        """网格文本按「实际列宽」定制制表位。

        Tk 默认的制表位是「若干个平均字符宽」，中文是方字，默认值会让第二列
        挤在第一个单元格后面（看着像只隔了一个空格），列就全乱了。
        这里用真实字体量出每列最宽的单元格，累加成停靠位置；
        没有制表符的普通文本恢复默认，避免影响正文排版。
        """
        if self.text is None:
            return
        if "\t" not in content:
            self.text.configure(tabs=())
            return
        rows = [line.split("\t") for line in content.split("\n") if "\t" in line]
        n_cols = max((len(r) for r in rows), default=1)
        if n_cols < 2:
            self.text.configure(tabs=())
            return
        try:
            font = tkfont.Font(font=self.text.cget("font"))
        except Exception:                   # 字体不可用时退回默认制表位
            return
        widths = [0] * (n_cols - 1)
        for row in rows:
            for idx, cell in enumerate(row[:-1]):
                widths[idx] = max(widths[idx], font.measure(cell))
        stops, acc = [], 0
        for width in widths:
            acc += width + 18               # 列间留白，避免两列贴在一起
            stops.append(acc)
        self.text.configure(tabs=tuple(stops))

    def _current_text(self) -> str:
        if self.view == "tidy" and self._tidy is not None:
            return self._tidy.text
        return self._raw

    # ---------- 交互
    def set_view(self, view: str, notify: bool = True) -> None:
        if view == "tidy" and (self._tidy is None or not self._tidy.text.strip()):
            view = "raw"
        self.view = view
        self._paint()
        self._sync_controls()
        if view == "raw" and self._details_open:
            self._toggle_details()      # 看原文时不需要明细，顺手收起
        if notify:
            self.on_view_change(view)

    def _toggle_mode(self) -> None:
        self.mode = "paragraph" if self.mode == "verbatim" else "verbatim"
        if self.mode_btn:
            self.mode_btn.configure(text=f"排版：{'合段' if self.mode == 'paragraph' else '逐行'}")
        self.on_mode_change(self.mode)

    def _toggle_details(self) -> None:
        if self._details is None:
            return
        self._details_open = not self._details_open
        if self._details_open:
            self._fill_details()
            self._details.grid()
        else:
            self._details.grid_remove()
        self._sync_controls()

    def _fill_details(self) -> None:
        t = self._tidy
        if t is None or self._details_text is None:
            return

        def short(s: str, n: int = 22) -> str:
            return s if len(s) <= n else s[:n] + "…"

        lines = []
        for c in t.changes:
            line = f"{c.label} ×{c.count}"
            if c.before or c.after:
                line += f"    {short(c.before)} → {short(c.after)}"
            lines.append(line)
        body = "\n".join(lines) if lines else "未发现需要修正的地方。"
        self._details_text.configure(state="normal")
        self._details_text.delete("1.0", "end")
        self._details_text.insert("1.0", body)
        self._details_text.configure(state="disabled")
        self._details_text.configure(height=max(3, min(7, len(lines) + 1)))
        if self._details_note is not None:
            head = f"{self._structure} · " if self._structure else ""
            subj = self._subject or {}
            if subj.get("applied") and subj.get("on") and subj.get("label"):
                head = f"主体 {subj['label']} · 滤掉 {subj.get('total', 0) - subj.get('kept', 0)} 框 · " + head
            self._details_note.configure(
                text=f"{head}内容相似度 {t.similarity * 100:.1f}% · {t.note}")

    def _copy(self) -> None:
        content = self.text.get("1.0", "end-1c") if self.text else ""
        self.on_copy(content)

    def _copy_and_close(self) -> None:
        self._copy()
        self.hide()

    def _retry(self) -> None:
        self.on_retry()

    # ---------- 展示
    def show(self, raw_text: str, meta: dict, anchor: tuple[int, int] | None = None,
             tidy_result: TidyResult | None = None, view: str | None = None,
             subject: dict | None = None) -> None:
        if self.win is None or not self.win.winfo_exists():
            self._build()
            if anchor:
                self._place_near(anchor)
        self.win.deiconify()
        self.win.lift()
        self.win.attributes("-topmost", True)

        if subject is not None:
            self._subject = dict(subject)
        self._raw = raw_text
        self._tidy = tidy_result
        wanted = view or self.view
        if tidy_result is None or not tidy_result.text.strip():
            wanted = "raw"
        self.view = wanted
        self._paint()

        if self.meta_var:
            lines = meta.get("lines", 0)
            chars = meta.get("chars", 0)
            self._structure = meta.get("structure") or ""
            self._meta_short = f"{lines} 行 · {chars} 字"
            # 结构摘要（网格 9 行 × 4 列 / 分栏 2 栏 / 3 级字号）只在宽窗显示：
            # 窄窗的顶部一行放不下，硬塞会把「整理 / 原文」按钮挤走。
            tail = f" · {self._structure}" if self._structure else ""
            self._meta_full = (
                f"{lines} 行 · {chars} 字{tail} · "
                f"置信度 {meta.get('avg_score', 0) * 100:.0f}% · {meta.get('elapsed', 0):.2f}s"
            )
            self.meta_var.set(self._meta_short if self._compact else self._meta_full)
        if self.mode_btn:
            self.mode_btn.configure(text=f"排版：{'合段' if self.mode == 'paragraph' else '逐行'}")

        # 新结果先收起明细：内容变了，先把正文让出来；用户想看再点开
        if self._details is not None:
            self._details.grid_remove()
        self._details_open = False
        self._sync_controls()

        # 让复制快捷键立即可用
        self.win.focus_force()
        if self.text:
            self.text.focus_set()

    def update_raw(self, raw_text: str) -> None:
        """排版模式切换后重算的原文：只更新缓存，正在看原文时才重绘。"""
        self._raw = raw_text
        if self.view == "raw":
            self._paint()

    def _place_near(self, anchor: tuple[int, int]) -> None:
        """窗口默认出现在选区右下方，超出屏幕则回退到光标附近。"""
        if not self.win:
            return
        self.win.update_idletasks()
        w = self.win.winfo_width() or 620
        h = self.win.winfo_height() or 420
        x, y = anchor
        sw = self.win.winfo_screenwidth()
        sh = self.win.winfo_screenheight()
        x = min(max(0, x + 24), max(0, sw - w - 8))
        y = min(max(0, y + 24), max(0, sh - h - 8))
        self.win.geometry(f"+{x}+{y}")
        self._geometry = self.win.geometry()

    def content(self) -> str:
        return self.text.get("1.0", "end-1c") if self.text else ""

    def hide_for_capture(self) -> bool:
        """截图前隐藏，返回是否原本可见（用于之后恢复）。"""
        if self.win is not None and self.win.winfo_exists() and self.win.state() != "withdrawn":
            self.win.withdraw()
            return True
        return False

    def hide(self) -> None:
        if self.win is not None and self.win.winfo_exists():
            self.win.withdraw()
