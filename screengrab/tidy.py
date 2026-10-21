"""文本整理：把 OCR 出来的「一堆行」变成「一段能直接读的话」。

版面还原（layout.py）解决的是「字在屏幕上的位置 → 行 + 结构」，
本模块解决的是「行 → 自然语言文本」，两者职责不重叠：

  1. 字符归一  —— 全角字母数字转半角、清零宽字符、去软连字符
  2. 标点统一  —— 中文语境下半角 , ; : ! ? ( ) " 转全角，省略号/重复标点归一
  3. 空格清理  —— 删掉中文之间、标点两侧的 OCR 噪声空格，折叠连续空格
  4. 断行重排  —— 判断「硬换行（排版截断）」还是「真换行（段落结束）」并合并
  5. 段落重组  —— 按标题/列表/缩进/行宽把句子聚成段落，段间留一空行
  6. 纠错      —— 重复虚词折叠、数字串里误识的 O/l/I、高置信错别字表

第 4 步最容易出错，也最依赖上游信息：
  · 传了 RowMeta（layout.build 产出的行元信息）时，用「行右边缘填充率」
    判断这一行是不是被排版截断——比用字符数猜「满行多少字」可靠；
    网格行、标题行、跨字号层级一律不合并；
  · 没传时（外部直接调用 tidy）退化为字符数 75 分位，并用「整页都是短行、
    且没有句末标点」识别「标签列表」，宁可一行一个也不要糊成一段。

设计约束（对应「保留原文语义，不增删改写实质内容」）：

  · 只做「形」的调整。除纠错规则外，任何一步都不改变字符本身；
  · 每条改动都进 ChangeLog，带 before/after 样例，可在界面上查看；
  · 收尾用 `_analyze()` 做保真校验：把原文与结果都归一成「非空白、
    非标点的内容骨架」后比对，骨架一致才算完全保真，不一致时给出
    差异字数和风险等级，界面据此提示用户复核。

纯函数、无 IO、无 UI、无网络依赖，便于单元测试，也不拖慢识别速度
（5000 字文本 < 10 ms）。
"""
from __future__ import annotations

import difflib
import re
import unicodedata
from dataclasses import dataclass, field

from .layout import RowMeta

# ------------------------------------------------------------------ 字符集
# 只放汉字，不含全角标点区（\uff00-\uffef）——标点要单独判定，
# 混在一起会把「，」当成 CJK，导致「中文，」两侧的合并判断全线跑偏。
CJK_RANGE = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
CJK_RE = re.compile(f"[{CJK_RANGE}]")

CJK_PUNCT = "，。！？；：、（）【】《》〈〉「」『』“”‘’…—～·"
# 判「上一行是否已经说完一句话」时用的句末符号。含全角闭合引号，
# 因为「他说：“好。”」这种行尾是先引号再换行。
# 不含分号：中文分号多用于并列分句，后面通常还是同一段，断段会显得很碎。
SENT_END = "。！？…：!?:"
_TAIL_QUOTES = "”’」』》】\"')）"

_LIST_RE = re.compile(
    r"^\s*(?:"
    r"[（(]?\d{1,2}[)）.、]"          # 1. / 1、 / (1) / （1）
    r"|[①-⑳]"                        # ① ②
    r"|[一二三四五六七八九十]{1,3}[、.]"  # 一、 二.
    r"|[·•▪◦●○◆◇■□☐☑→※]\s*"          # 项目符号
    r"|[-*+]\s"                       # markdown 列表（必须后跟空格，避免误伤分隔线）
    r")"
)

# 全角 → 半角只转这类「本该是 ASCII」的字符。全角逗号、句号、括号
# 本身就是中文标点，绝不能转，否则会把正确的中文标点改成英文的。
_FULL2HALF: dict[int, int] = {
    **{0xFF10 + i: ord("0") + i for i in range(10)},
    **{0xFF21 + i: ord("A") + i for i in range(26)},
    **{0xFF41 + i: ord("a") + i for i in range(26)},
    **{c: ord(h) for c, h in {
        "％": "%", "＠": "@", "＃": "#", "＆": "&", "＋": "+", "＝": "=",
        "＜": "<", "＞": ">", "／": "/", "＼": "\\", "｜": "|", "＿": "_",
        "＄": "$", "～": "~", "｛": "{", "｝": "}", "［": "[", "］": "]",
        "＊": "*", "＾": "^", "｀": "`", "＂": '"', "＇": "'",
    }.items()},
}

_HALF_PUNCT = {",": "，", ";": "；", ":": "：", "!": "！", "?": "？"}

_ZW_CHARS = "\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e" \
            "\u2060\ufeff\u00ad"
_ZW_MAP = dict.fromkeys((ord(c) for c in _ZW_CHARS), None)

# 重复一次几乎一定是 OCR 重复框，不是修辞的虚词
_REPEAT_CHARS = "的了是在和与及或而也就都更最不没我你他她它这那"
_REPEAT_RE = re.compile(f"([{_REPEAT_CHARS}])\\1+")

# 高置信错别字表：只收「有唯一正确写法且不涉及语义判断」的搭配。
# 形近字（未/末、己/已、土/士）一律不收——那需要上下文模型才能判，
# 规则表强改只会制造新错误。
_TYPO_TABLE: tuple[tuple[str, str], ...] = (
    ("己经", "已经"), ("因该", "应该"), ("即然", "既然"), ("按装", "安装"),
    ("做为", "作为"), ("部份", "部分"), ("记算", "计算"), ("提共", "提供"),
    ("需耍", "需要"), ("主耍", "主要"), ("交待", "交代"), ("竟争", "竞争"),
    ("偏辟", "偏僻"), ("松驰", "松弛"), ("渡假", "度假"), ("凑和", "凑合"),
    ("侯车", "候车"), ("帐号", "账号"), ("帐户", "账户"), ("一但", "一旦"),
    ("担误", "耽误"), ("自以", "自认"), ("按排", "安排"), ("编缉", "编辑"),
)

MAX_PARA = 1200      # 单段上限，超过就强制断开（防止误判把整篇合成一段）


# ------------------------------------------------------------------ 数据结构
@dataclass
class Change:
    """一类改动 + 一个样例，用于界面上「整理明细」可追溯展示。"""
    kind: str
    label: str
    before: str
    after: str
    count: int = 1


@dataclass
class TidyOptions:
    normalize_width: bool = True
    fix_punct: bool = True
    fix_space: bool = True
    join_wrap: bool = True
    fix_typo: bool = True


@dataclass
class TidyResult:
    text: str                                  # 整理后
    raw: str                                   # 原始识别结果（逐行）
    changes: list[Change] = field(default_factory=list)
    paragraphs: int = 0
    similarity: float = 1.0                    # 内容骨架相似度（忽略空白/标点）
    fidelity: str = "ok"                       # ok | minor | warn
    note: str = ""

    @property
    def total(self) -> int:
        return sum(c.count for c in self.changes)

    def summary(self) -> str:
        if not self.changes:
            return "已整理 · 未发现需要修正的地方"
        return f"已整理 {self.total} 处 · 原文可随时切换查看"


@dataclass
class _Line:
    text: str
    indent: int
    blank: bool = False
    meta: RowMeta = field(default_factory=RowMeta)


class _ChangeLog:
    """按 label 聚合：同一类规则只留第一条样例，免得明细列表刷屏。"""

    def __init__(self) -> None:
        self._d: dict[str, Change] = {}

    def add(self, kind: str, label: str, before: str, after: str, n: int = 1) -> None:
        c = self._d.get(label)
        if c is None:
            self._d[label] = Change(kind, label, before[:60], after[:60], n)
        else:
            c.count += n

    def items(self) -> list[Change]:
        return list(self._d.values())


# ------------------------------------------------------------------ 基础判定
def is_cjk(ch: str) -> bool:
    return bool(ch) and bool(CJK_RE.match(ch))


def _is_punct(ch: str) -> bool:
    if not ch:
        return False
    return unicodedata.category(ch).startswith("P") or ch in "～·＋＝"


def _strip_tail(text: str) -> str:
    """去掉行尾空白与闭合引号，露出真正的句末符号。"""
    return text.rstrip().rstrip(_TAIL_QUOTES).rstrip()


def _ends_sentence(text: str) -> bool:
    t = _strip_tail(text)
    return bool(t) and t[-1] in SENT_END


def _signature(text: str) -> str:
    """内容骨架：NFKC 归一后去掉全部空白与标点，只留「实质字符」。

    全角数字经 NFKC 后与半角一致，所以「字符归一」不会被误判成内容变更；
    真正的改写（错别字纠正）才会让骨架出现差异，由 `_fidelity` 负责量化。
    """
    s = unicodedata.normalize("NFKC", text)
    return "".join(ch for ch in s if not ch.isspace() and not _is_punct(ch))


def _analyze(raw: str, text: str) -> tuple[float, str, str]:
    """一次算完相似度与保真等级，返回 (similarity, fidelity, note)。

    绝大多数整理只动「形」（空白、标点、换行），内容骨架完全相同——这时
    直接早退，连 difflib 都不用跑。只有纠错规则真的改了字，才需要逐个
    比对；且 SequenceMatcher 是 O(n²)，超长文本退化为长度比，避免卡住界面。
    """
    a, b = _signature(raw), _signature(text)
    if a == b:
        return 1.0, "ok", "实质内容与原文完全一致"
    if not a or not b:
        return 0.0, "warn", "整理后内容为空，请对照原文"

    if len(a) + len(b) > 4000:
        ratio = min(len(a), len(b)) / max(len(a), len(b))
        if ratio >= 0.995:
            return ratio, "minor", "已按规则整理，实质内容基本未变"
        return ratio, "warn", "整理前后差异较大，建议对照原文"

    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes()
                  if tag != "equal")
    # 容忍度取「3 字」与「2%」的较大值：短文本里改 2~3 个错别字很正常，
    # 不该因此被判成「改动过大」；长文本则按比例收紧。
    tolerance = max(3.0, len(a) * 0.02)
    if changed <= tolerance:
        return sm.ratio(), "minor", f"实质内容仅 {changed} 字差异（均为纠错规则）"
    return sm.ratio(), "warn", (f"实质内容有 {changed} 字差异"
                                f"（{changed / max(1, len(a)) * 100:.1f}%），建议对照原文")


# ------------------------------------------------------------------ 单行处理
def _translate_fullwidth(text: str, log: _ChangeLog) -> str:
    if not any(ord(ch) in _FULL2HALF for ch in text):
        return text
    out = []
    for ch in text:
        cp = _FULL2HALF.get(ord(ch))
        if cp is None:
            out.append(ch)
        else:
            out.append(chr(cp))
            log.add("char", "全角数字/字母 → 半角", ch, chr(cp))
    return "".join(out)


def _clean_spaces(text: str, log: _ChangeLog) -> str:
    before = text
    text = text.replace("\u00a0", " ").replace("\u3000", " ")
    # 中文与中文之间的空格：几乎全是 OCR 把字切碎后塞进来的噪声
    text = re.sub(rf"(?<=[{CJK_RANGE}])[ \t]+(?=[{CJK_RANGE}])", "", text)
    # 中文与中文标点之间
    text = re.sub(rf"(?<=[{CJK_RANGE}])[ \t]+(?=[{CJK_PUNCT}])", "", text)
    text = re.sub(rf"(?<=[{CJK_PUNCT}])[ \t]+(?=[{CJK_RANGE}])", "", text)
    # 括号内侧
    text = re.sub(r"(?<=[（【《])\s+|\s+(?=[）】》])", "", text)
    text = re.sub(r" {2,}", " ", text)
    text = text.strip()
    if text != before:
        log.add("space", "删除多余空格", before.strip()[:50], text[:50])
    return text


def _unify_punct(text: str, log: _ChangeLog) -> str:
    if not text:
        return text
    cjk = len(CJK_RE.findall(text)) >= 2
    orig = text

    # 1) 省略号：先于普通重复折叠处理，否则「。。。」会先被折成一个「。」
    if re.search(r"。{3,}", text):
        text = re.sub(r"。{3,}", "……", text)
        log.add("punct", "句号连写 → 省略号", "。。。", "……")
    m = re.search(r"\.{3,}", text)
    if m:
        rep = "……" if cjk else "…"
        text = re.sub(r"\.{3,}", rep, text)
        log.add("punct", "英文省略号统一", m.group(0), rep)

    # 2) 半角逗号/分号/冒号/叹号/问号 → 全角（仅中文语境，且避开 1,000 / 12:30 / URL）
    if cjk:
        chars = list(text)
        for i, ch in enumerate(text):
            full = _HALF_PUNCT.get(ch)
            if full is None:
                continue
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            if prev.isdigit() and nxt.isdigit():
                continue
            # 用元组而非字符串做成员判断：`"" in ":/"` 为 True，
            # 会让行首/行尾的标点全部被误跳过。
            if prev in (":", "/") or nxt in (":", "/"):
                continue
            if is_cjk(prev) or is_cjk(nxt) or (prev and prev in CJK_PUNCT):
                chars[i] = full
                log.add("punct", f"半角{ch} → 全角{full}", ch, full)
        text = "".join(chars)

        # 3) 半角句号 → 中文句号：只当前面是汉字（3.14 / v1.2 不受影响）
        def _dot(m: re.Match) -> str:
            log.add("punct", "半角句号 → 中文句号", ".", "。")
            return m.group(1) + "。"

        text = re.sub(rf"([{CJK_RANGE}])\s*\.(?=\s|$|[^\x00-\x7f])", _dot, text)

        # 4) 括号与引号：内容含中文才转，纯英文/公式保持原样
        def _paren(m: re.Match) -> str:
            inner = m.group(1)
            if not CJK_RE.search(inner):
                return m.group(0)
            log.add("punct", "半角括号 → 全角括号", f"({inner[:12]})", f"（{inner[:12]}）")
            return f"（{inner}）"

        text = re.sub(r"\(([^()\n]{0,200})\)", _paren, text)

        def _quote(m: re.Match) -> str:
            inner = m.group(1)
            if not CJK_RE.search(inner):
                return m.group(0)
            log.add("punct", '直引号 → 中文引号', f'"{inner[:12]}"', f"“{inner[:12]}”")
            return f"“{inner}”"

        text = re.sub(r'"([^"\n]{0,200})"', _quote, text)

    # 5) 重复标点折叠（任何语境都做，「，，」「；；」没有正常用途）
    text, n = re.subn(r"([。，、；：])\1+", r"\1", text)
    if n:
        log.add("punct", "重复标点折叠", "，，", "，", n)
    text, n = re.subn(r"([！？])[！？]{2,}", r"\1", text)
    if n:
        log.add("punct", "连续叹号/问号折叠", "！！！", "！", n)

    if text != orig:
        text = text.strip()
    return text


def _fix_typos(text: str, log: _ChangeLog) -> str:
    if not text:
        return text

    def _fold(m: re.Match) -> str:
        ch = m.group(1)
        log.add("typo", "重复字折叠", m.group(0), ch)
        return ch

    text = _REPEAT_RE.sub(_fold, text)

    # 数字串里被误识成字母的三个高频混淆（只在前/后是数字时生效）
    for pat, rep, label in (
        (r"(?<=\d)[OoQ](?=\d)", "0", "数字 0 误识为 O"),
        (r"(?<=\d)[lI](?=\d)", "1", "数字 1 误识为 l/I"),
        (r"(?<=\d)[lI](?=[.,]\d)", "1", "数字 1 误识为 l/I"),
    ):
        text, n = re.subn(pat, rep, text)
        if n:
            log.add("typo", f"数字纠错：{label}", "O", "0", n)

    for wrong, right in _TYPO_TABLE:
        if wrong == right or wrong not in text:
            continue
        n = text.count(wrong)
        text = text.replace(wrong, right)
        log.add("typo", "常见错别字", wrong, right, n)

    return text


# 文件名 / 路径 / 版本号：点号是内容的一部分，不能统一成中文句号
_FILE_TAIL = re.compile(r"\.[A-Za-z0-9]{1,5}$")


def _punct_safe(text: str) -> bool:
    """这一格能不能做标点统一。

    网格单元里大量是文件名、URL、版本号（`软件结构.docx`、`v1.2.3`、`a/b`），
    把它们的点号、斜杠改成全角就是改内容；被省略号截断的标签
    （Windows 会显示成 `Plain Craft Launche...`）同理，`...` 是原文。
    """
    body = text.strip()
    if not body:
        return False
    if "://" in body or _FILE_TAIL.search(body) or body.endswith("..."):
        return False
    return True


def _clean_cell(cell: str, opt: TidyOptions, log: _ChangeLog) -> str:
    """网格单元（表格单元格 / 图标名）的清理。

    只做「确定安全」的三步：全角字母数字转半角、空格清理、纠错。
    标点统一要先过 `_punct_safe`——单元格里的点号多半是文件名而不是句号。
    """
    if opt.normalize_width:
        cell = _translate_fullwidth(cell, log)
    if opt.fix_space:
        cell = _clean_spaces(cell, log)
    if opt.fix_typo:
        cell = _fix_typos(cell, log)
    if opt.fix_punct and _punct_safe(cell):
        cell = _unify_punct(cell, log)
    return cell


def _prepare(raw: str, opt: TidyOptions, log: _ChangeLog,
             rows: list[RowMeta] | None = None) -> list[_Line]:
    body_rows = raw.split("\n")
    metas = rows if rows and len(rows) == len(body_rows) else None
    lines: list[_Line] = []
    for idx, row in enumerate(body_rows):
        meta = metas[idx] if metas else RowMeta()
        row = row.rstrip()
        if not row.strip():
            lines.append(_Line("", 0, True, meta))
            continue
        body = row.lstrip(" \u3000\t")
        indent = len(row) - len(body)
        if "\t" in body:
            # 含制表符 = 网格/表格行。结构一旦按段落合并就毁了，
            # 所以逐格清理、保留列结构、整行独立输出。
            body = "\t".join(_clean_cell(c, opt, log) for c in body.split("\t"))
        else:
            if opt.normalize_width:
                body = _translate_fullwidth(body, log)
            if opt.fix_space:
                body = _clean_spaces(body, log)
            if opt.fix_punct:
                body = _unify_punct(body, log)
            if opt.fix_typo:
                body = _fix_typos(body, log)
        lines.append(_Line(body, indent, False, meta))
    return lines


# ------------------------------------------------------------------ 断行与合段
def _full_width(lines: list[_Line]) -> int:
    """估计「满行」有多少字：取非空、非表格行长度的 75 分位。

    用它判断「这一行是不是被排版截断的」——被判为截断才会跟下一行合并。
    """
    lens = sorted(len(l.text) for l in lines if l.text.strip() and "\t" not in l.text)
    if len(lens) < 3:
        return 0
    return lens[min(len(lens) - 1, int(len(lens) * 0.75))]


def _looks_like_labels(lines: list[_Line]) -> bool:
    """整页都是短行、又没有句末标点 → 这是标签列表，不是被截断的正文。

    图标名竖排一列、菜单项、卡片标题都属于这种：它们的行宽天然参差，
    任何「按行宽 / 标点判断该不该合并」的启发式都会把它们糊成一段。
    宁可一行一个（用户还能自己删），也比拼成一句读不通的话强。
    """
    bodies = [l.text.strip() for l in lines if l.text.strip() and "\t" not in l.text]
    if len(bodies) < 4:
        return False
    if any(_ends_sentence(t) for t in bodies):
        return False
    if any(_LIST_RE.match(t) for t in bodies):
        return False
    return max(len(t) for t in bodies) <= 10


def _should_break(prev: _Line, cur: _Line, full_width: int,
                  has_meta: bool = False) -> bool:
    """cur 是否应该另起一段（而不是接在 prev 后面）。"""
    if "\t" in prev.text or "\t" in cur.text:
        return True                      # 表格行永远独占
    if prev.meta.kind == "grid" or cur.meta.kind == "grid":
        return True                      # 网格的单列行（无制表符）也不并肩
    if cur.meta.kind == "heading" or prev.meta.kind == "heading":
        return True                      # 标题自成一段
    if has_meta and abs(prev.meta.level - cur.meta.level) >= 1:
        return True                      # 跨字号层级不合并（标题/正文/注释）
    if _LIST_RE.match(cur.text):
        return True                      # 列表项 / 编号行是新段起点
    if cur.indent > prev.indent:
        return True                      # 下一行缩进加深 = 新段首行
    if cur.indent < prev.indent - 1:
        return True                      # 从缩进回到顶格 = 上一段结束
    if _ends_sentence(prev.text):
        return True                      # 上一行已经收句
    if len(prev.text.strip()) == 1 and not _LIST_RE.match(prev.text):
        return False                     # 单字残行，多半是 OCR 碎片，直接接上
    if has_meta and prev.meta.fill < 0.8:
        return True                      # 几何：上一行连版心的 80% 都没写到
    if full_width and len(prev.text) < full_width * 0.72:
        return True                      # 上一行明显没写满 = 段尾
    return False


def _merge(prev: str, cur: str, log: _ChangeLog) -> str:
    a, b = prev.rstrip(), cur.lstrip()
    if not b:
        return a
    if a.endswith("-") and b[:1].islower() and not is_cjk(b[0]):
        log.add("wrap", "英文断词还原", a[-6:] + "⏎" + b[:6], a[-6:-1] + b[:6])
        return a[:-1] + b
    if b[0] in "，。、；：！？…）】》」』”’%,.;:!?)":
        return a + b                     # 下一行以标点开头：直接接
    if a[-1] in CJK_PUNCT or a[-1] in ",.;:!?":
        return a + b                     # 上一行以标点结尾：中文标点后不留空格
    if is_cjk(a[-1]) and is_cjk(b[0]):
        return a + b                     # 中文接中文：不加空格
    return a + " " + b                   # 其余（含中英混排）补一个空格


def _assemble(lines: list[_Line], opt: TidyOptions, log: _ChangeLog,
              has_meta: bool = False) -> list[tuple[str, str]]:
    """把行聚成块。块返回 (kind, text)，kind ∈ para / list / table。

    区分 kind 是为了输出时选连接符：连续列表项之间用单换行（紧凑的列表），
    段落之间用空行（可读的段落间距）。表格 block 内部已是多行。
    """
    full_width = _full_width(lines)
    labels_only = _looks_like_labels(lines)
    blocks: list[tuple[str, str]] = []
    buf = ""
    table: list[str] = []
    prev: _Line | None = None

    def flush_para(kind: str | None = None) -> None:
        nonlocal buf
        if buf.strip():
            text = buf.strip()
            blocks.append((kind or ("list" if _LIST_RE.match(text) else "para"), text))
        buf = ""

    def flush_table() -> None:
        if table:
            blocks.append(("table", "\n".join(table)))
            table.clear()

    for ln in lines:
        if ln.blank:
            flush_para()
            flush_table()
            prev = None
            continue
        if "\t" in ln.text or ln.meta.kind == "grid":
            flush_para()
            table.append(ln.text)         # 网格行（含单列行）连成一个紧凑块
            prev = ln
            continue
        flush_table()

        if not buf:
            buf = ln.text.strip()
        elif labels_only:
            flush_para("list")            # 标签列表：一行一个，且行间不留空行
            buf = ln.text.strip()
        elif not opt.join_wrap or _should_break(prev, ln, full_width, has_meta):
            flush_para()
            buf = ln.text.strip()
        elif len(buf) >= MAX_PARA:
            flush_para()
            buf = ln.text.strip()
        else:
            cur = ln.text.strip()
            merged = _merge(buf, cur, log)
            # 用竖线标出断点位置（⏎ 之类符号在部分字体里会缺字，显示成方块）
            log.add("wrap", "合并硬换行",
                    "…" + buf[-8:] + "｜" + cur[:8],
                    "…" + (buf[-8:] + merged[len(buf):])[-16:])
            buf = merged
        prev = ln

    flush_para("list" if labels_only else None)
    flush_table()
    return blocks


def _render(blocks: list[tuple[str, str]]) -> str:
    out = ""
    prev_kind = ""
    for kind, text in blocks:
        if out:
            tight = (kind == prev_kind == "list") or (kind == "table" and prev_kind == "table")
            out += "\n" if tight else "\n\n"
        out += text
        prev_kind = kind
    return out


# ------------------------------------------------------------------ 主入口
def tidy(raw: str, options: TidyOptions | None = None,
         rows: list[RowMeta] | None = None,
         dropped: list[str] | None = None) -> TidyResult:
    """整理一段 OCR 结果。空输入返回空结果，不抛异常。

    rows     —— layout.build 产出的行元信息（可为 None，退化为纯文本启发式）
    dropped  —— 结构化阶段判定为图标/徽标、已从正文里剔除的字符，
                这里补一条变更记录，保证「原文 → 整理稿」的差异可追溯
    """
    opt = options or TidyOptions()
    src = (raw or "").translate(_ZW_MAP).replace("\r\n", "\n").replace("\r", "\n")
    if not src.strip():
        return TidyResult("", raw or "", [], 0, 1.0, "ok", "无内容")

    log = _ChangeLog()
    if dropped:
        log.add("noise", "忽略图标/徽标字符",
                "、".join(dropped)[:40], "（已从正文移除）", len(dropped))

    lines = _prepare(src, opt, log, rows)
    has_meta = bool(rows) and len(rows) == len(lines)
    blocks = _assemble(lines, opt, log, has_meta)
    text = re.sub(r"\n{3,}", "\n\n", _render(blocks)).strip()

    paragraphs = sum(1 for b in text.split("\n\n") if b.strip())
    similarity, fidelity, note = _analyze(src, text)
    return TidyResult(text=text, raw=raw, changes=log.items(),
                      paragraphs=paragraphs, similarity=similarity,
                      fidelity=fidelity, note=note)
