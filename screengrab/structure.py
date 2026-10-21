"""二维版面结构分析：把一页分成「区块」，再逐块决定怎么拼字。

layout.py 的 `group_lines` 只回答「这些框属于哪一行」，它隐含一个假设：整页是
**一栏连续文字**。真实截图很少这么规整——桌面图标是网格，报表是「标题 + 正文 +
四列表格」纵向拼接，PDF 是两栏，同一页里字号还常常有四五级。

只按「行」拼字会在两处出错：

  1. 行内间距阈值摇摆。网格里两个单元之间的空隙（实测同屏 22~43px）
     与「词间距」不可区分，阈值恰好落在中间，于是同一行里有的地方连、有的地方断：
     `此电脑剪映专业版百度网盘→豆包`。
  2. 全局列边界会切碎正文。下半页的表格投出三条列边界，上半页的正文行
     也被按这些边界切开，两行文字上下合并成一个「单元格」，读出来就是
     `第一条 为规范管理第二条 本办法适用于全体员工。`。

所以这里不追求「整页一个列模型」，而是：

  1. 列候选   —— 收集各行内部「大空隙」区间，按区间重叠聚类成候选列边界；
  2. 逐行签名 —— 每一行自己判断「这些空隙里有没有列边界」。正文行的
                 空隙里没有边界（它的两个框是同一句话被切开的），
                 表格行的空隙里正好有边界；
  3. 区块聚合 —— 签名相同的连续行并成一个区块，相邻区块之间按纵向间距留空行；
  4. 区块定性 —— 单元格短 → 标签网格（逐行、制表符对齐）；单元格长 →
                 分栏正文（整栏读完再换栏）；没有边界 → 单栏正文；
  5. 单元还原 —— 列内纵向相邻的框并成一个单元（图标名折行）；OCR 偶尔把
                 相邻两个单元吞进一个框，按比例 + 就近空格切开。

只做几何判断、不改字符内容；纯函数，可直接单测。
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field

# 判定「这是列间距」的最小空隙：行高的 0.9 倍。再小就与词间距不可区分。
MIN_GAP_RATIO = 0.9

# 跨列切分后两侧至少保留的字数。1 个字的尾片多半是同一单元被边界擦到。
SPLIT_MIN_PART = 2

MAX_COLUMNS = 8          # 再多就不是版面，是噪点
GRID_MAX_CELL_CHARS = 22  # 单元格平均字数超过这个值，按「分栏正文」而不是网格处理
TABLE_PIECE_MAX_CHARS = 12  # 短框（≤12 字）才启用「同行有邻列 → 不并单元」规则


@dataclass
class Piece:
    """分析用的矩形块，与 layout.TextItem 同构（鸭子类型，避免循环 import）。"""
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    score: float = 1.0

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


@dataclass
class Cell:
    """一列里纵向相连的一组框 = 一个语义单元（一个图标名 / 一个单元格）。"""
    col: int
    pieces: list = field(default_factory=list)

    @property
    def x0(self) -> float:
        return min(p.x0 for p in self.pieces)

    @property
    def x1(self) -> float:
        return max(p.x1 for p in self.pieces)

    @property
    def y0(self) -> float:
        return min(p.y0 for p in self.pieces)

    @property
    def y1(self) -> float:
        return max(p.y1 for p in self.pieces)

    @property
    def chars(self) -> int:
        return sum(len(p.text.strip()) for p in self.pieces)


@dataclass
class Row:
    cells: list = field(default_factory=list)
    y0: float = 0.0
    y1: float = 0.0


@dataclass
class Block:
    """一段结构一致的连续行。"""
    kind: str                                   # prose | grid | columns
    items: list = field(default_factory=list)
    rows: list = field(default_factory=list)    # 视觉行（list[list[Piece]]）
    bounds: list[float] = field(default_factory=list)
    n_rows: int = 0
    n_cols: int = 1

    @property
    def y0(self) -> float:
        return min(p.y0 for p in self.items)

    @property
    def y1(self) -> float:
        return max(p.y1 for p in self.items)


# --------------------------------------------------------------- 基础几何
def _median(values, default: float = 0.0) -> float:
    vals = [v for v in values if v > 0]
    return statistics.median(vals) if vals else default


def cluster_rows(items) -> list[list]:
    """按 y 中心把框分成视觉行。容差取行高的一半，容忍轻微倾斜与字号差异。"""
    rows: list[list] = []
    for it in sorted(items, key=lambda i: i.cy):
        if rows:
            last = rows[-1]
            ref = _median([i.h for i in last], it.h)
            mid = _median([i.cy for i in last], it.cy)
            if abs(it.cy - mid) <= 0.5 * max(ref, it.h):
                last.append(it)
                continue
        rows.append([it])
    return rows


def size_levels(items) -> list[float]:
    """按框高聚类得到字号层级（降序）。相邻层相差 >18% 才算不同层。

    框高 ≈ 字高，同一段正文的框高波动在 5% 以内；标题通常是正文的 1.4~2.4 倍，
    注释小一号。用「排序后顺序聚类」而不是 k-means：层数未知、样本量小，
    顺序聚类更稳，也不会因为一个离群大框把正文层拆成两层。
    """
    clusters: list[list[float]] = []       # [均值, 计数]
    for h in sorted(i.h for i in items if i.h > 0):
        if clusters and h <= clusters[-1][0] * 1.18:
            mean, count = clusters[-1]
            clusters[-1] = [(mean * count + h) / (count + 1), count + 1]
        else:
            clusters.append([h, 1.0])
    keep = max(1, int(len(items) * 0.04))
    levels = [round(m, 1) for m, c in clusters if c >= keep]
    levels.sort(reverse=True)
    return levels or [_median([i.h for i in items], 12.0)]


def level_of(height: float, levels: list[float]) -> int:
    """框高属于第几层（0 = 最大字号）。"""
    for idx, lv in enumerate(levels):
        if height >= lv * 0.9:
            return idx
    return max(0, len(levels) - 1)


# --------------------------------------------------------------- 列边界
def _row_gaps(row: list, med_h: float) -> list[tuple[float, float]]:
    """一行内部的「大空隙」区间。"""
    if len(row) < 2:
        return []
    ordered = sorted(row, key=lambda i: i.x0)
    row_h = _median([i.h for i in ordered], med_h)
    threshold = max(row_h, med_h) * MIN_GAP_RATIO
    return [(left.x1, right.x0)
            for left, right in zip(ordered, ordered[1:])
            if right.x0 - left.x1 >= threshold]


def detect_boundaries(items) -> list[float]:
    """全页候选列边界。

    聚类用「空隙区间是否重叠」，而不是「空隙中点距离是否够近」：
    图标名长短不一，同一条列间缝在不同行里会漂移十几像素（居中对齐时，
    两列标签越窄，缝越宽），固定容差会把同一条边界拆成两条。
    """
    rows = cluster_rows(items)
    med_h = _median([i.h for i in items], 12.0)
    gaps: list[tuple[float, float]] = []
    multi = 0
    for row in rows:
        row_gaps = _row_gaps(row, med_h)
        if not row_gaps:
            continue
        multi += 1
        gaps.extend(row_gaps)
    if multi < 2 or not gaps:
        return []

    # 丢掉「跨了好几个单元」的巨缝：某一行缺了中间单元时，相邻两项之间会出现
    # 比正常列间隙宽几倍的空隙（实测 295px vs 50px），它会把几条真实边界
    # 连成一个区间，导致整页被判成两列。
    if len(gaps) >= 4:
        med_gap = statistics.median([hi - lo for lo, hi in gaps])
        gaps = [(lo, hi) for lo, hi in gaps if hi - lo <= med_gap * 3]

    spans: list[list[float]] = []          # [lo, hi, 支持行数]
    for lo, hi in sorted(gaps):
        if spans and lo <= spans[-1][1] + med_h * 0.3:
            spans[-1][1] = max(spans[-1][1], hi)
            spans[-1][2] += 1
        else:
            spans.append([lo, hi, 1])

    # 支持度：至少 2 行，且不少于「多单元行数」的 22%。用比例而非绝对数，
    # 避免整页只有两三行时判不出列，也避免某一行特别宽的词间距被当成列边界。
    need = max(2, math.ceil(multi * 0.22))
    bounds = sorted((lo + hi) / 2 for lo, hi, n in spans if n >= need)

    clean: list[float] = []
    for b in bounds:
        if not clean or b - clean[-1] > med_h * 1.2:
            clean.append(b)
    clean = clean[:MAX_COLUMNS - 1]
    return _trim_sparse_edges(clean, items, med_h)


def _trim_sparse_edges(bounds: list[float], items, med_h: float) -> list[float]:
    """去掉边缘的「稀疏窄列」。

    截一个完整窗口时，右侧常有一条滚动条 + 几个按钮（复制、关闭…），它们在
    每一行都投出同一条「空隙」，会被当成第二栏，于是正文按栏切开、阅读顺序
    变成「先读正文左半，再读按钮」——比不切难读得多。

    真列与 UI 挂件的区别很明确：真列**每一行都有内容**（两栏正文、表格、
    图标网格都是如此），挂件只在少数几行出现，字符量也小。三个条件同时满足
    才丢掉这条边界，避免误伤「序号」这类窄而密的列。
    """
    if not bounds or len(items) < 8:
        return bounds
    left = min(p.x0 for p in items)
    right = max(p.x1 for p in items)
    width = max(1.0, right - left)
    total_chars = sum(len(p.text.strip()) for p in items) or 1
    n_rows = len(cluster_rows(items))
    bounds = list(bounds)

    def sparse(edge: list) -> bool:
        if not edge:
            return False
        rows = len(cluster_rows(edge))
        chars = sum(len(p.text.strip()) for p in edge)
        return rows <= n_rows * 0.5 and chars < total_chars * 0.2

    while bounds:
        edge = [p for p in items if p.cx >= bounds[-1]]
        if sparse(edge) and right - bounds[-1] < width * 0.3:
            bounds.pop()
        else:
            break
    while bounds:
        edge = [p for p in items if p.cx <= bounds[0]]
        if sparse(edge) and bounds[0] - left < width * 0.3:
            bounds.pop(0)
        else:
            break
    return bounds


def _row_signature(row: list, bounds: list[float], med_h: float) -> tuple[int, ...]:
    """这一行命中了哪些列边界。

    正文行里，边界通常落在某个框**内部**（那句话横跨了表格列的投影位置），
    或者是两个紧邻框之间的缝（缝里没有边界）——两种情况都判「无列」。
    只有边界真的落在这行的空隙里，才认为这一行有列结构。
    """
    if not bounds:
        return ()
    gaps = _row_gaps(row, med_h)
    if not gaps:
        return ()
    hit = []
    for idx, bound in enumerate(bounds):
        for lo, hi in gaps:
            if lo - med_h * 0.3 <= bound <= hi + med_h * 0.3:
                hit.append(idx)
                break
    return tuple(hit)


def _columns_from(bounds: list[float], items) -> list[tuple[float, float]]:
    if not bounds:
        return [(min(i.x0 for i in items), max(i.x1 for i in items))]
    edges = [-math.inf] + list(bounds) + [math.inf]
    return [(edges[i], edges[i + 1]) for i in range(len(edges) - 1)]


def column_of(piece, bounds: list[float]) -> int:
    """按中心点归列。居中排列的图标用中心点比用左边缘可靠得多。"""
    cx = piece.cx
    for idx, bound in enumerate(bounds):
        if cx < bound:
            return idx
    return len(bounds)


# --------------------------------------------------------------- 跨列框切分
def _snap_index(text: str, ratio: float) -> int | None:
    """把「按比例算出的切点」吸附到最近的空格；没有空格就不切。

    空格是唯一可以安全切开的字符：中文没有词边界，硬切会产生
    「Honeyvie / w 联想超级文件」这种把单词剁开的碎片。
    """
    if len(text) < 4:
        return None
    idx = max(1, min(len(text) - 1, round(ratio * len(text))))
    span = max(2, round(len(text) * 0.18))
    for dist in range(span + 1):
        for cand in (idx - dist, idx + dist):
            if 1 <= cand < len(text) and text[cand] == " ":
                return cand + 1
    return None


def _split_one(piece, bounds: list[float], med_h: float) -> list:
    inner = [b for b in bounds
             if piece.x0 + med_h * 0.6 < b < piece.x1 - med_h * 0.6]
    if not inner or len(piece.text.strip()) < 4:
        return [piece]

    parts: list[tuple[str, float, float]] = [(piece.text, piece.x0, piece.x1)]
    for bound in inner:
        text, x0, x1 = parts[-1]
        idx = _snap_index(text, (bound - x0) / max(1.0, x1 - x0))
        if idx is None:
            continue
        left, right = text[:idx].strip(), text[idx:].strip()
        if len(left) < 1 or len(right) < SPLIT_MIN_PART:
            continue
        parts[-1] = (left, x0, bound)
        parts.append((right, bound, x1))
    if len(parts) == 1:
        return [piece]
    return [Piece(t, a, piece.y0, b, piece.y1, piece.score) for t, a, b in parts]


def split_spanning(items, bounds: list[float], med_h: float) -> list:
    """把跨越列边界的框切开，让每个单元各自归列。"""
    if not bounds:
        return list(items)
    out: list = []
    for it in items:
        out.extend(_split_one(it, bounds, med_h))
    return out


# --------------------------------------------------------------- 单元与行
def _row_mates(pieces, bounds: list[float]) -> dict:
    """标出「占满整行列数」的行，这些行是真正的表格换行，不是一个单元的折行。

    两种纵向相邻在几何上无法区分，只能看整块的规律：

      · 表格换行 —— 姓名/部门、张三/研发，每行都**占满**这一块常见的列数；
      · 图标名折行 —— `Plain Craft` 下面是 `Launche...`，邻列的 `DeepSeek`
        下面是 `Harness`，这一行只占了 2 列，而这一块绝大多数行占 4 列。

    所以先统计「每行占了几列」的众数（modal），只有占到 modal 的行才算表格行。
    两列正文不在此列：它们的框很长，`grid_cells` 里已经按字数关掉了这条规则。
    """
    counts = [len({column_of(p, bounds) for p in row}) for row in cluster_rows(pieces)]
    modal = statistics.mode(counts) if counts else 0
    mates: dict = {}
    for row in cluster_rows(pieces):
        cols = {column_of(p, bounds) for p in row}
        shared = modal >= 2 and len(cols) >= modal
        for p in row:
            mates[id(p)] = shared
    return mates


def _badge_like(piece) -> bool:
    """像「图标徽标」的框：单个字母数字，或 2~4 个大写字母（Word 的 W、压缩包的 ZIP）。

    这类框本来就不该独占一行：它是图标上的字母，下面/上面才是真名字。它们常
    恰好和邻行的标签同高，被当成表格行，从而挡住与名字的合并——所以单独放行。
    """
    text = piece.text.strip()
    if not text:
        return False
    if len(text) == 1:
        return text.isalnum()
    return 2 <= len(text) <= 4 and text.isupper() and text.isalnum()


def grid_cells(items, bounds: list[float], med_h: float) -> list[Cell]:
    """按列分桶 → 列内纵向合并成单元。"""
    n_cols = len(bounds) + 1
    pieces = split_spanning(items, bounds, med_h)
    buckets: list[list] = [[] for _ in range(n_cols)]
    for piece in pieces:
        buckets[min(column_of(piece, bounds), n_cols - 1)].append(piece)

    # 只对「短框」启用表格行规则：两栏正文的每一行也有邻列，但它的框很长，
    # 行距又小，一旦禁止合并就会把整段正文化成一格一格的碎片。
    short = _median([len(p.text.strip()) for p in pieces], 0) <= TABLE_PIECE_MAX_CHARS
    mates = _row_mates(pieces, bounds) if short else {}

    cells: list[Cell] = []
    for col, bucket in enumerate(buckets):
        bucket.sort(key=lambda p: (p.y0, p.x0))
        current: Cell | None = None
        for piece in bucket:
            if current is not None:
                gap = piece.y0 - current.y1
                # 行距 ≤0.6 倍字高（含轻微重叠）视为同一单元的折行；
                # 但这一行占满了整块列数（== 表格换行）时不并，否则两行表格会塌成一行。
                if gap <= max(2.0, med_h * 0.6) and (not mates.get(id(piece))
                                                     or _badge_like(piece)
                                                     or any(_badge_like(p) for p in current.pieces)):
                    current.pieces.append(piece)
                    continue
            current = Cell(col, [piece])
            cells.append(current)
    return cells


def visual_rows(cells: list[Cell]) -> list[Row]:
    """把单元按纵向重叠度聚成视觉行（一行里可能有被折成两行的单元）。"""
    rows: list[Row] = []
    for cell in sorted(cells, key=lambda c: (c.y0, c.col)):
        if rows:
            last = rows[-1]
            overlap = min(last.y1, cell.y1) - max(last.y0, cell.y0)
            ref = min(last.y1 - last.y0, cell.y1 - cell.y0)
            if ref > 0 and overlap / ref >= 0.45:
                last.cells.append(cell)
                last.y0 = min(last.y0, cell.y0)
                last.y1 = max(last.y1, cell.y1)
                continue
        rows.append(Row([cell], cell.y0, cell.y1))
    return rows


def split_columns(items, bounds: list[float], med_h: float) -> list[list]:
    """分栏排版：按列分桶，每桶内部按 y 排序（阅读顺序＝先读完左栏）。"""
    n_cols = len(bounds) + 1
    buckets: list[list] = [[] for _ in range(n_cols)]
    for piece in split_spanning(items, bounds, med_h):
        buckets[min(column_of(piece, bounds), n_cols - 1)].append(piece)
    for bucket in buckets:
        bucket.sort(key=lambda p: (p.y0, p.x0))
    return [b for b in buckets if b]


def _grid_is_plausible(cells: list[Cell], items) -> bool:
    """网格自检：有没有单元横跨整个区块宽度、还合并了多行文字。

    正文被列边界切碎时，上下两行会被并进同一个单元，宽度接近整块版心。
    真正的单元格（图标名、表头、参数值）不可能这么宽。
    """
    width = max(i.x1 for i in items) - min(i.x0 for i in items)
    if width <= 0:
        return False
    return all(not (len(c.pieces) >= 2 and (c.x1 - c.x0) >= width * 0.75) for c in cells)


# --------------------------------------------------------------- 区块切分
def _is_label_row(row: list, band: dict, med_h: float) -> bool:
    """这一行像不像网格/表格的续行（而不是正文）。"""
    pieces = [p for p in row if p.text.strip()]
    if not pieces or len(pieces) > 6:
        return False
    total = sum(len(p.text.strip()) for p in pieces)
    if total > 48:
        return False
    for p in pieces:
        text = p.text.strip()
        if not text:
            continue
        if any(ch in text for ch in "。！？；："):
            return False
        if len(text) > 24:            # 一个单元最多两行标签的量
            return False
    return (min(p.x0 for p in pieces) >= band["x0"] - med_h * 2
            and max(p.x1 for p in pieces) <= band["x1"] + med_h * 2)


def segment(items) -> tuple[list[Block], float, list[float]]:
    """把一页切成区块，每块自带「怎么拼字」的结论。

    做法：先看每一行有没有列结构，把连续的「有列结构」的行合成一条**带**；
    带的两端各放宽 1.2 倍字高，把贴着网格的孤立行（图标名折行的第一行、
    最后一行）吸进来。之所以要放宽：`W`（Word 图标被识成字母）与下面的
    文件名分属两行，那一行只有一个框、天然没有列结构，不吸进来就会被
    当成独立正文，网格里就少了一行。
    """
    items = list(items)
    if not items:
        return [], 12.0, []
    med_h = _median([i.h for i in items], 12.0)
    rows = cluster_rows(items)
    bounds = detect_boundaries(items)

    if not bounds:
        return [Block("prose", items, rows)], med_h, []

    hits = [_row_signature(row, bounds, med_h) for row in rows]
    n = len(rows)

    # 1) 连续的「有列结构」行 → 粗带；中间夹一行没有列结构的（折行标签）也连上
    bands: list[dict] = []
    i = 0
    while i < n:
        if not hits[i]:
            i += 1
            continue
        j = i
        while j + 1 < n:
            if hits[j + 1]:
                j += 1
            elif j + 2 < n and hits[j + 2]:
                j += 2                     # 跨过中间那行折行标签
            else:
                break
        span_rows = rows[i:j + 1]
        y0 = min(r[0].y0 for r in span_rows)
        y1 = max(p.y1 for r in span_rows for p in r)
        union: set[int] = set()
        for k in range(i, j + 1):
            union.update(hits[k])
        bands.append({"y0": y0 - med_h * 1.2, "y1": y1 + med_h * 1.2,
                      "bounds": sorted(bounds[t] for t in union),
                      "x0": min(p.x0 for r in span_rows for p in r),
                      "x1": max(p.x1 for r in span_rows for p in r),
                      "end": j})
        i = j + 1

    # 带向下吸收「标签续行」：OCR 有时把一个图标行的两个标签吞进同一个框，
    # 那一行内部就没有足够大的空隙（实测 15px < 阈值 17px），会被判成无列结构，
    # 于是一个九行网格在最后三行断掉。标签续行的特征很明确：没有句末标点、
    # 每段都很短、横向不出带的左右边界。
    for band in bands:
        for k in range(band["end"] + 1, n):
            span = rows[k]
            if not _is_label_row(span, band, med_h):
                break
            band["y1"] = max(band["y1"], max(p.y1 for p in span) + med_h * 0.2)

    def band_of_point(cy: float) -> int | None:
        for idx, band in enumerate(bands):
            if band["y0"] <= cy <= band["y1"]:
                return idx
        return None

    def band_of(row: list) -> int | None:
        return band_of_point(_median([p.cy for p in row], 0))

    # 2) 按行的归属逐个产出区块：正文行攒成 prose 块，带内所有行并成一个 grid/columns 块
    blocks: list[Block] = []
    prose_rows: list[list] = []

    def flush_prose() -> None:
        if not prose_rows:
            return
        block_items = [p for row in prose_rows for p in row]
        blocks.append(Block("prose", block_items, list(prose_rows)))
        prose_rows.clear()

    done: set[int] = set()
    for row in rows:
        idx = band_of(row)
        if idx is None:
            prose_rows.append(row)
            continue
        if idx in done:                   # 同一带的后几行，已随块输出
            continue
        flush_prose()
        done.add(idx)
        band = bands[idx]
        # 只收「归属这一带」的框：带两端各放宽了 1.2 倍字高，相邻带会重叠，
        # 直接按 y 区间取会把同一批文字算进两个区块，输出就重复了。
        band_items = [p for p in items if band_of_point(p.cy) == idx]
        band_rows = [r for r in rows if band_of(r) == idx]
        cells = grid_cells(band_items, band["bounds"], med_h)
        typical = _median([c.chars for c in cells], 0)
        if typical and typical <= GRID_MAX_CELL_CHARS and _grid_is_plausible(cells, band_items):
            kind = "grid"
        else:
            kind = "columns"
        blocks.append(Block(kind, band_items, band_rows, band["bounds"],
                            n_rows=len(visual_rows(cells)) if kind == "grid" else len(band_rows),
                            n_cols=len(band["bounds"]) + 1))
    flush_prose()
    return blocks, med_h, bounds


def describe(blocks: list[Block]) -> str:
    """给界面用的一句话结构摘要。"""
    parts: list[str] = []
    for blk in blocks:
        if blk.kind == "grid":
            parts.append(f"网格 {blk.n_rows} 行 × {blk.n_cols} 列")
        elif blk.kind == "columns":
            parts.append(f"分栏 {blk.n_cols} 栏")
        else:
            parts.append("正文")
    # 连续多个「正文」区块合并描述，避免刷屏
    merged: list[str] = []
    for p in parts:
        if p == "正文" and merged and merged[-1].startswith("正文"):
            continue
        merged.append(p)
    return " + ".join(merged)
