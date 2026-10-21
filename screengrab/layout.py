"""版面还原：把 OCR 的零散文本框拼回「像原文一样」的文本。

OCR 只给出一堆 (四点框, 文本, 置信度)。直接按行拼接会丢掉缩进、段间距和表格列，
所以这里做四件事：

  1. 结构判定  —— 先问「这页是单栏正文、标签网格，还是分栏排版」（structure.py），
                 不同结构的拼字规则完全不同，判错了后面全错
  2. 行聚类    —— 按垂直重叠率把框分到同一行（容忍轻微倾斜/字号不一）
  3. 行内拼接  —— 按 x 间距决定 空格 / 制表符 / 直接相连（中文不应插空格）
  4. 段落切分  —— 按行间距、左边缘对齐与行末留白判断换行还是分段

还原结果除了文本，还带一份「行元信息」（RowMeta）：字号层级、是否网格行、
是否标题、右边缘填充率。整理阶段（tidy.py）靠它判断「这行是不是被排版截断的」，
比用字符数猜宽度可靠得多。

纯函数、无 IO、无 UI 依赖，便于单元测试。
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field

from . import structure

CJK_RE = re.compile(r"[\u3000-\u303f\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\uff00-\uffef]")


@dataclass
class TextItem:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float = 1.0
    ink: object = None        # subject.Ink：墨迹颜色特征，由 ocr 阶段采样后挂上

    @property
    def w(self) -> float:
        return self.x1 - self.x0

    @property
    def h(self) -> float:
        return self.y1 - self.y0

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2

    @classmethod
    def from_quad(cls, quad, text: str, score: float) -> "TextItem":
        xs = [float(p[0]) for p in quad]
        ys = [float(p[1]) for p in quad]
        return cls(text, min(xs), min(ys), max(xs), max(ys), float(score))


@dataclass
class Line:
    items: list[TextItem] = field(default_factory=list)

    @property
    def x0(self) -> float:
        return min(i.x0 for i in self.items)

    @property
    def x1(self) -> float:
        return max(i.x1 for i in self.items)

    @property
    def y0(self) -> float:
        return min(i.y0 for i in self.items)

    @property
    def y1(self) -> float:
        return max(i.y1 for i in self.items)

    @property
    def h(self) -> float:
        return statistics.median(i.h for i in self.items)

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class RowMeta:
    """一行文本的几何与语义信息，供整理阶段做「是否合并」的判断。"""
    level: int = 0        # 字号层级，0 = 最大
    kind: str = ""        # "" 普通行 / grid 网格行 / heading 标题
    fill: float = 1.0     # 行右边缘占版心宽度的比例（判断是否被排版截断）
    noise: bool = False   # 疑似图标/徽标字符（不是正文）


@dataclass
class Doc:
    text: str = ""
    rows: list[RowMeta] = field(default_factory=list)
    kind: str = "prose"                 # prose | grid | columns
    n_cols: int = 1
    levels: list[float] = field(default_factory=list)
    note: str = ""
    dropped: list[str] = field(default_factory=list)

    @property
    def is_grid(self) -> bool:
        return self.kind == "grid"


def _overlap(a0: float, a1: float, b0: float, b1: float) -> float:
    return max(0.0, min(a1, b1) - max(a0, b0))


def _estimate_char_width(items: list[TextItem]) -> float:
    """用「框宽 / 字符数」的中位数估计一个字宽，作为间距阈值基准。"""
    ratios = [i.w / max(1, len(i.text.strip())) for i in items if i.text.strip()]
    if not ratios:
        return 10.0
    return max(2.0, statistics.median(ratios))


# 同一行内允许的最大字号差（高比）。超过这个比例一定不是同一行文字：
# 大号标题压在页面小字上时，两者垂直重叠率很高，只看重叠率会被搓成一行。
MAX_LINE_HEIGHT_RATIO = 2.2
# 同一行内允许的最大水平重叠率。同一行的文字块左右并排、互不压盖；
# 竖向堆叠的美术字（三行大标题）检测框会彼此重叠，只看纵向就会被并成一行。
MAX_LINE_X_OVERLAP = 0.35


def group_lines(items: list[TextItem], min_overlap: float = 0.45) -> list[Line]:
    """垂直重叠率聚类成行；自顶向下逐行吸收，最终按 y 排序。

    除了纵向重叠，还要过两道闸：字号差太大、水平方向互相压盖，都不是同一行。
    """
    lines: list[Line] = []
    for it in sorted(items, key=lambda i: (i.cy, i.x0)):
        best, best_ov = None, 0.0
        for ln in lines:
            ov = _overlap(it.y0, it.y1, ln.y0, ln.y1)
            ref = max(1.0, min(it.h, ln.h))
            if ov / ref < min_overlap or ov / ref <= best_ov:
                continue
            # 字号差得太远就不是同一行的字（见 MAX_LINE_HEIGHT_RATIO 注释）
            lo, hi = sorted((it.h, ln.h))
            if hi > lo * MAX_LINE_HEIGHT_RATIO:
                continue
            # 水平压盖说明是上下堆叠而不是左右相邻（见 MAX_LINE_X_OVERLAP 注释）
            x_ov = _overlap(it.x0, it.x1, ln.x0, ln.x1) / max(1.0, min(it.w, ln.x1 - ln.x0))
            if x_ov > MAX_LINE_X_OVERLAP:
                continue
            best, best_ov = ln, ov / ref
        if best is None:
            lines.append(Line([it]))
        else:
            best.items.append(it)
    for ln in lines:
        ln.items.sort(key=lambda i: i.x0)
    lines.sort(key=lambda l: (l.y0, l.x0))
    return lines


def is_cjk(ch: str) -> bool:
    return bool(ch) and bool(CJK_RE.match(ch))


def _line_char_width(items: list[TextItem]) -> float:
    """按「本行」估计字宽：同一行字号一致，用行内中位数比全局中位数稳。"""
    ratios = [i.w / max(1, len(i.text.strip())) for i in items if i.text.strip()]
    if not ratios:
        return 10.0
    return max(2.0, statistics.median(ratios))


def _join(items: list[TextItem], line_h: float) -> tuple[str, float]:
    """行内拼接：中文相邻不加空格；西文/数字相邻补一个空格；大间距转制表符。

    阈值同时参考「字宽」和「行高」：表格列间距通常既远大于字宽、也大于行高，
    而普通句子被 OCR 切成多段时，间距几乎为 0。

    注意：网格版面不走这里——网格的列边界由 structure.detect_boundaries 定，
    用「间距阈值」判列在图标网格上必然摇摆（实测同屏空隙 22~43px，
    而阈值恰好落在 30px 附近，于是同一行里有的地方连、有的地方断）。
    """
    char_w = _line_char_width(items)
    tab_gap = max(char_w * 1.8, line_h * 1.35)
    space_gap = char_w * 0.45
    out = ""
    for idx, it in enumerate(items):
        txt = it.text.strip()
        if idx == 0:
            out = txt
            continue
        gap = it.x0 - items[idx - 1].x1
        left = out[-1:] if out else ""
        right = txt[:1]
        if gap > tab_gap:
            sep = "\t"                      # 跨列（表格 / 目录 / 参数说明）
        elif is_cjk(left) and is_cjk(right):
            sep = ""                        # 中文之间不加空格
        elif gap > space_gap:
            sep = " "
        else:
            sep = ""
        out += sep + txt
    return out, char_w


def _indent_width(x0: float, base_left: float, char_w: float, limit: int = 8) -> int:
    delta = x0 - base_left
    if delta <= char_w * 0.6:
        return 0
    return max(0, min(limit, round(delta / char_w)))


# --------------------------------------------------------------- 单元内拼接
_TAIL_OPEN = "，。、；：！？…（【《「『“‘,.;:!?("
_HEAD_CLOSE = "，。、；：！？…）】》」』”’%,.;:!?)"


def _vjoin(parts: list[str]) -> str:
    """把一个单元里被折成多行的文字接回去（图标名、单元格内换行）。"""
    out = ""
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if not out:
            out = part
            continue
        if part[0] in _HEAD_CLOSE:
            out += part                       # 下一行以标点开头
        elif out[-1] in _TAIL_OPEN:
            out += part                       # 上一行以标点结尾（含「软件结构.」→ docx）
        elif is_cjk(out[-1]) and is_cjk(part[0]):
            out += part
        else:
            out += " " + part
    return out


def _is_glyph(piece, cell: structure.Cell) -> bool:
    """单元格里混进来的单个西文字母：几乎都是图标/徽标被识别成了字。

    只认「一个 ASCII 字母数字」+「同一单元里还有别的文字」，范围收得很窄：
    正文里单独一个「W」是合法文字（比如尺寸标注），不该删；只有出现在
    图标网格的单元里、与别的文字挤在一起时才判定为徽标。
    """
    text = piece.text.strip()
    if len(cell.pieces) < 2 or not text:
        return False
    if len(text) == 1:
        return text.isascii() and text.isalnum()
    # 图标角标（压缩包的 ZIP、图章的 PDF）：全大写、2~4 个字母、宽度只占单元的
    # 一小条。放得很窄是为了不误伤「API 文档」这种真的由两段组成的单元格。
    if 2 <= len(text) <= 4 and text.isascii() and text.isupper():
        return piece.w <= (cell.x1 - cell.x0) * 0.35
    return False


# --------------------------------------------------------------- 各类版面
def _prose_rows(items: list[TextItem], levels: list[float], body_level: int,
                med_h: float, mode: str) -> list[tuple[str, RowMeta]]:
    """单栏（或某一栏内部）的顺序排版。"""
    char_w = _estimate_char_width(items)
    lines = group_lines(items)
    line_h = statistics.median([l.h for l in lines]) or char_w
    base_left = min(l.x0 for l in lines)
    col_left = min(i.x0 for i in items)
    col_right = max(i.x1 for i in items)
    span = max(1.0, col_right - col_left)
    body_h = levels[body_level] if levels else line_h

    rows: list[tuple[str, RowMeta]] = []
    prev: Line | None = None
    prev_heading = False

    for ln in lines:
        txt, lchar = _join(ln.items, ln.h)
        indent = 0 if "\t" in txt else _indent_width(ln.x0, base_left, lchar)
        lh = statistics.median(i.h for i in ln.items)
        level = structure.level_of(lh, levels)
        heading = (len(levels) > 1 and lh >= body_h * 1.18 and len(txt) <= 60)
        fill = (ln.x1 - col_left) / span

        gap = (ln.y0 - prev.y1) if prev is not None else 0.0
        big_gap = prev is not None and gap > line_h * 1.35

        # 标题自成一档：前后各留一个空行，层级才不会和正文糊在一起
        if rows and rows[-1][0] != "" and (big_gap or prev_heading or heading):
            rows.append(("", RowMeta(level=level)))

        if (mode == "paragraph" and prev is not None and not big_gap
                and not heading and not prev_heading):
            same_block = (
                gap <= line_h * 0.62
                and abs(ln.x0 - prev.x0) < char_w * 1.6
                and "\t" not in txt
                and rows and rows[-1][0] != ""
                and rows[-1][1].level == level
            )
            if same_block:
                last_text, last_meta = rows[-1]
                sep = "" if (is_cjk(last_text[-1:]) or is_cjk(txt[:1])) else " "
                last_meta.fill = max(last_meta.fill, fill)
                rows[-1] = (last_text + sep + txt, last_meta)
                prev, prev_heading = ln, heading
                continue

        rows.append((" " * indent + txt,
                     RowMeta(level=level, kind="heading" if heading else "", fill=fill)))
        prev, prev_heading = ln, heading
    return rows


def _grid_rows(block: structure.Block, med_h: float,
               keep_glyphs: bool) -> tuple[list, list[str]]:
    """标签网格：每个单元（图标名/单元格）独立，行内用制表符对齐列。"""
    cells = structure.grid_cells(block.items, block.bounds, med_h)
    rows: list[tuple[str, RowMeta]] = []
    dropped: list[str] = []

    for row in structure.visual_rows(cells):
        parts: list[str] = []
        prev_col: int | None = None
        for cell in sorted(row.cells, key=lambda c: c.col):
            keep = []
            for piece in cell.pieces:
                if not keep_glyphs and _is_glyph(piece, cell):
                    dropped.append(piece.text.strip())
                    continue
                keep.append(piece)
            if not keep:
                continue
            if prev_col is not None:
                # 缺列时补空制表符，保持列位对齐（不补前导，避免行首出现空洞）
                parts.append("\t" * max(1, cell.col - prev_col))
            parts.append(_vjoin([p.text for p in keep]))
            prev_col = cell.col
        if parts:
            rows.append(("".join(parts), RowMeta(kind="grid")))
    return rows, dropped


def _column_rows(block: structure.Block, levels: list[float], body_level: int,
                 med_h: float, mode: str) -> list[tuple[str, RowMeta]]:
    """分栏排版：一栏读完再读下一栏，栏间空行。"""
    rows: list[tuple[str, RowMeta]] = []
    for bucket in structure.split_columns(block.items, block.bounds, med_h):
        if rows:
            rows.append(("", RowMeta()))
        rows.extend(_prose_rows(bucket, levels, body_level, med_h, mode))
    return rows


def _normalize_rows(rows: list[tuple[str, RowMeta]]) -> list[tuple[str, RowMeta]]:
    """折叠连续空行、去掉首尾空行（在行级别做，保证文本与 RowMeta 严格对齐）。"""
    out: list[tuple[str, RowMeta]] = []
    for text, meta in rows:
        if text.strip() == "":
            if not out or out[-1][0] == "":
                continue
            out.append(("", meta))
        else:
            out.append((text, meta))
    while out and out[-1][0] == "":
        out.pop()
    return out


def build(items: list[TextItem], mode: str = "verbatim",
          keep_glyphs: bool = False) -> Doc:
    """主入口：区块切分 → 逐块排版 → 文本 + 行元信息。

    mode 只影响正文区块里的「逐行 / 合段」，网格与分栏的拼法由结构决定：
    把一张参数表的四列合成一句话没有任何意义。

    keep_glyphs=True 用于「原文视图」：图标/徽标被识别成的孤立字符保留下来，
    让用户能对照 OCR 的原始输出；整理稿则默认剔除并在明细里记一笔。
    """
    items = [i for i in items if i.text.strip()]
    if not items:
        return Doc("", [], "empty", 0, [])

    levels = structure.size_levels(items)
    if levels:
        counts = [sum(1 for i in items if structure.level_of(i.h, levels) == k)
                  for k in range(len(levels))]
        body_level = counts.index(max(counts))
    else:
        body_level = 0

    blocks, med_h, _bounds = structure.segment(items)
    rows: list[tuple[str, RowMeta]] = []
    dropped: list[str] = []
    prev_block: structure.Block | None = None

    for blk in blocks:
        # 区块之间按纵向间距补空行：这是原文的「段间距」，不属于任何一块
        if prev_block is not None and blk.y0 - prev_block.y1 > med_h * 1.05:
            rows.append(("", RowMeta()))
        if blk.kind == "grid":
            part, lost = _grid_rows(blk, med_h, keep_glyphs)
            rows.extend(part)
            dropped.extend(lost)
        elif blk.kind == "columns":
            rows.extend(_column_rows(blk, levels, body_level, med_h, mode))
        else:
            rows.extend(_prose_rows(blk.items, levels, body_level, med_h, mode))
        prev_block = blk

    kept = _normalize_rows(rows)
    kinds = {b.kind for b in blocks}
    kind = kinds.pop() if len(kinds) == 1 else ("mixed" if kinds else "empty")
    note = structure.describe(blocks)
    if len(levels) > 1 and levels[0] >= levels[-1] * 1.3:
        note += f" · {len(levels)} 级字号"
    return Doc(
        text="\n".join(t for t, _ in kept),
        rows=[m for _, m in kept],
        kind=kind,
        n_cols=max((b.n_cols for b in blocks), default=1),
        levels=levels,
        note=note,
        dropped=dropped,
    )


def to_text(items: list[TextItem], mode: str = "verbatim") -> str:
    """兼容入口：只要文本时用它（内部按结构自动选排版方式）。"""
    return build(items, mode).text


def stats(items: list[TextItem]) -> dict:
    """给 UI 展示的识别质量摘要。"""
    if not items:
        return {"lines": 0, "chars": 0, "avg_score": 0.0, "low": 0}
    scores = [i.score for i in items]
    return {
        "lines": len(group_lines(items)),
        "chars": sum(len(i.text.strip()) for i in items),
        "avg_score": sum(scores) / len(scores),
        "low": sum(1 for s in scores if s < 0.85),
    }
