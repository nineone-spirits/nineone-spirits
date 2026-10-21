"""主体文字过滤：从框选区域里挑出「用户真正想要的那一层文字」。

问题：框选一块屏幕，里面通常不止一层文字。典型场景是截图/视频画面上的大字标题，
背后还压着页面本身的正文小字——OCR 会把两层都认出来，按行拼版时彼此穿插，
读出来就是一锅粥（`github.com/xxx/对话用中文展示思考过程帮我安装这个插件：`）。

解法不靠语义（离线、无模型），只靠两个屏幕文字最稳定的视觉事实：

  1. **字号**：主体文字通常比周围背景文字大一个量级（实测 126~173px vs 14~20px）；
  2. **颜色**：主体文字常带品牌色/强调色，背景正文是灰阶（彩度接近 0）。

于是每个 OCR 框量两个数：框高（≈字号）和「墨迹彩度」。再按「尺寸带」筛，
必要时按色系收敛。

为什么不用「文本内容」判断：那需要语言模型，破坏纯离线约定；而字号和颜色是
抄屏场景里最不会骗人的信号。

纯函数 + 只读 numpy，便于单测（见 tests/test_subject.py）。
"""
from __future__ import annotations

import colorsys
import statistics
from dataclasses import dataclass, field

import numpy as np

# 与背景色的差异（RGB 三通道绝对差之和）超过它才算「墨迹」像素。
INK_DISTANCE = 60
# 墨迹像素的彩度（max-min）达到它才算彩色文字；灰阶文字接近 0。
CHROMA_MIN = 30
# 主体字号相对全区域中位字号的最小倍数。低于它说明这页没有「一眼主体」，
# 不做过滤——正常文档里标题只有正文的 1.4~1.6 倍，不该被当成主体。
SIZE_GAP_MIN = 2.0
# 主体带的下沿：不小于最大字号的这个比例。0.45 能容忍同一标题里
# 「中文行高 173 / 西文行高 126」这种自然差异，又不会把正文小字带进来。
BAND_FLOOR = 0.45
# 主体带里彩色框占比达到它，才按色系收敛（把同带的灰阶大字当作背景剔除）。
COLOR_DOMINANCE = 0.7

# 色系划分（Hue 角度，左闭右开；红跨越 0°，单独处理）。切分点按屏幕用色习惯取，
# 与 CSS 命名色大致对齐，够用即可——这里只为「红 / 蓝 / 绿」这种粗分类服务。
FAMILIES: tuple[tuple[str, float, float], ...] = (
    ("红", 315.0, 25.0),
    ("橙", 25.0, 45.0),
    ("黄", 45.0, 70.0),
    ("绿", 70.0, 165.0),
    ("青", 165.0, 200.0),
    ("蓝", 200.0, 260.0),
    ("紫", 260.0, 315.0),
)


@dataclass
class Ink:
    """一个文本框的墨迹（文字本体）颜色特征。"""
    rgb: tuple[int, int, int] = (0, 0, 0)
    chroma: float = 0.0          # 0~255，max-min
    hue: float = -1.0            # 0~360，灰阶时为 -1
    family: str = ""             # 红/橙/黄/绿/青/蓝/紫/黑/灰/白
    colored: bool = False        # 是否彩色（相对灰阶）

    @property
    def label(self) -> str:
        return f"{self.family}色" if self.colored else self.family


@dataclass
class Subject:
    """一次过滤的结论：留下谁、滤掉谁、为什么，以及给人看的说明。"""
    kept: list = field(default_factory=list)
    dropped: list = field(default_factory=list)
    applied: bool = False
    label: str = ""
    reason: str = ""
    family: str = ""

    @property
    def total(self) -> int:
        return len(self.kept) + len(self.dropped)

    def describe(self) -> str:
        if not self.applied:
            return self.reason or "未启用主体过滤"
        return (f"主体 {self.label}：保留 {len(self.kept)} 个框，"
                f"滤掉 {len(self.dropped)} 个干扰框")


# ------------------------------------------------------------------ 颜色采样
def _family_of_hue(hue: float) -> str:
    for name, lo, hi in FAMILIES:
        if lo > hi:                      # 跨越 0° 的红
            if hue >= lo or hue < hi:
                return name
        elif lo <= hue < hi:
            return name
    return "红"


def _neutral_family(rgb: np.ndarray) -> str:
    v = float(rgb.max()) / 255.0
    if v < 0.45:
        return "黑"
    if v > 0.86:
        return "白"
    return "灰"


def analyze(patch: np.ndarray) -> Ink:
    """量一块像素（一个 OCR 框的内部）的文字本体颜色。

    步骤：量化取众数当背景 → 与背景差异够大的像素算墨迹 → 看墨迹里彩度高不高。
    这样做而不是「取平均色」的原因：大号美术字自带描边、阴影和抗锯齿过渡，
    平均值会把红描边和黑阴影混成脏褐色，反而判不出是红色。
    """
    if patch.size == 0:
        return Ink()

    px = patch.reshape(-1, 3).astype(np.int16)
    # 5-bit 量化：屏幕抗锯齿会产生大量相近色阶，太细的量化会把背景拆散
    key = (px[:, 0] >> 3) * 1024 + (px[:, 1] >> 3) * 32 + (px[:, 2] >> 3)
    uniq, counts = np.unique(key, return_counts=True)
    bg = px[key == uniq[int(counts.argmax())]].mean(axis=0)

    dist = np.abs(px - bg).sum(axis=1)
    ink = px[dist > INK_DISTANCE]
    if len(ink) < max(4, len(px) * 0.02):
        # 对比度极低的浅色字（如水印）：退而取差异最大的那一成像素
        ink = px[dist >= np.percentile(dist, 88)]
    if len(ink) == 0:
        return Ink(rgb=tuple(int(c) for c in bg), family=_neutral_family(bg))

    chroma = ink.max(axis=1) - ink.min(axis=1)
    hi = float(np.percentile(chroma, 92))
    if hi >= CHROMA_MIN:
        sel = ink[chroma >= max(CHROMA_MIN, hi * 0.75)]
        rgb = sel.mean(axis=0)
        r, g, b = (float(v) / 255.0 for v in rgb)
        hue = colorsys.rgb_to_hsv(r, g, b)[0] * 360.0
        return Ink(rgb=tuple(int(v) for v in rgb), chroma=float(hi), hue=hue,
                   family=_family_of_hue(hue), colored=True)

    rgb = ink.mean(axis=0)
    return Ink(rgb=tuple(int(v) for v in rgb), chroma=float(hi),
               family=_neutral_family(rgb), colored=False)


def sample(image: np.ndarray, item) -> Ink:
    """按框坐标从截图里取一块，返回 Ink；坐标越界时自动收敛。"""
    if image is None or getattr(image, "size", 0) == 0:
        return Ink()
    h, w = image.shape[:2]
    x0 = max(0, int(item.x0))
    y0 = max(0, int(item.y0))
    x1 = min(w, int(round(item.x1)))
    y1 = min(h, int(round(item.y1)))
    if x1 - x0 < 2 or y1 - y0 < 2:
        return Ink()
    patch = image[y0:y1, x0:x1]
    # 大框（美术字常常 1000×170）抽稀到 6 万像素以内，颜色统计不受影响
    while patch.size > 60000 and patch.shape[0] > 4 and patch.shape[1] > 4:
        patch = patch[::2, ::2]
    return analyze(patch)


def annotate(image: np.ndarray, items) -> None:
    """给每个 TextItem 挂上 ink 属性（原地修改，失败不影响识别主流程）。"""
    for it in items:
        try:
            it.ink = sample(image, it)
        except Exception:
            it.ink = Ink()


def ink_of(item) -> Ink:
    """取 item 的 Ink；手工构造的 TextItem 没有这个属性时返回空值。"""
    ink = getattr(item, "ink", None)
    return ink if isinstance(ink, Ink) else Ink()


# ------------------------------------------------------------------ 规则
def parse_rule(value) -> dict:
    """把配置值解析成规则字典。

    支持：``"off"`` / ``"auto"`` / ``"large"`` / ``"red"`` / ``"color:red"`` /
    字典 ``{"mode": "color", "family": "红", "ratio": 1.4}``。
    """
    rule = {"mode": "auto", "family": "", "ratio": 1.6}
    if value is None or value is False:
        return {"mode": "off", "family": "", "ratio": 1.6}
    if isinstance(value, dict):
        mode = str(value.get("mode", "auto")).lower()
        rule.update({"mode": mode})
        fam = value.get("family") or value.get("color") or ""
        rule["family"] = _norm_family(str(fam))
        try:
            rule["ratio"] = float(value.get("ratio", rule["ratio"]))
        except (TypeError, ValueError):
            pass
        return rule
    text = str(value).strip().lower()
    if text in ("", "off", "none", "false", "0", "全部"):
        return {"mode": "off", "family": "", "ratio": 1.6}
    if text.startswith("color:"):
        return {"mode": "color", "family": _norm_family(text.split(":", 1)[1]),
                "ratio": 1.4}
    if text in ("auto", "true", "1", "主体"):
        return rule
    if text in ("large", "big", "max", "大字号"):
        return {"mode": "large", "family": "", "ratio": 1.6}
    return {"mode": "color", "family": _norm_family(text), "ratio": 1.4}


_EN_FAMILY = {"red": "红", "orange": "橙", "yellow": "黄", "green": "绿",
              "cyan": "青", "blue": "蓝", "purple": "紫", "violet": "紫"}


def _norm_family(name: str) -> str:
    name = (name or "").strip().lower()
    if not name:
        return ""
    if name in _EN_FAMILY:
        return _EN_FAMILY[name]
    for key in ("红", "橙", "黄", "绿", "青", "蓝", "紫"):
        if name.startswith(key):
            return key
    return "红"


# ------------------------------------------------------------------ 选择
def _body_height(items) -> float:
    """「正文层」字号：取高度的 25 分位，而不是中位数。

    中位数在大字占比很高时会失真——4 条大标题 + 4 行小字的中位数落在两者之间，
    于是「小字」被当成正文、字号差被算小，主体就判不出来。25 分位稳稳落在
    偏小的那一群上，正好是「背景文字」的位置。
    """
    hs = sorted(i.h for i in items if i.h > 0)
    if not hs:
        return 0.0
    return hs[min(len(hs) - 1, int(len(hs) * 0.25))]


def _size_band(items) -> list:
    """按「最大字号 × BAND_FLOOR」切出主体带；同时把最大字号的离群值兜住。"""
    hs = sorted((i.h for i in items), reverse=True)
    top = hs[0] if hs else 0.0
    if top <= 0:
        return list(items)
    floor = max(top * BAND_FLOOR, _body_height(items) * 1.6)
    return [i for i in items if i.h >= floor]


def _narrow_by_color(band: list) -> tuple[list, str]:
    """主体带里彩色文字占绝对多数时，把同带的灰阶大字也当背景剔掉。

    只在「彩色 ≥70%」时动手：彩色只是点缀（比如标题里一个彩色图标）时不动，
    避免把整行标题拆散。
    """
    if len(band) < 2:
        return band, ""
    colored = [i for i in band if ink_of(i).colored]
    if len(colored) < len(band) * COLOR_DOMINANCE:
        return band, ""
    tally: dict[str, int] = {}
    for it in colored:
        tally[ink_of(it).family] = tally.get(ink_of(it).family, 0) + 1
    fam, count = max(tally.items(), key=lambda kv: kv[1])
    if count < len(band) * COLOR_DOMINANCE:
        return band, ""
    kept = [i for i in band if ink_of(i).colored and ink_of(i).family == fam]
    return kept, fam


def select(items, rule="auto") -> Subject:
    """按规则挑主体。返回 Subject；未触发过滤时 kept 就是全部 items。"""
    items = [i for i in items if i.text.strip()]
    parsed = parse_rule(rule)
    mode = parsed["mode"]
    if mode == "off" or len(items) < 2:
        return Subject(kept=list(items), applied=False, reason="未启用主体过滤")

    if mode == "color":
        return _select_color(items, parsed)
    return _select_size(items, parsed)


def _select_size(items, parsed: dict) -> Subject:
    body = _body_height(items)
    top = max(i.h for i in items)
    if parsed["mode"] == "auto" and (body <= 0 or top < body * SIZE_GAP_MIN):
        # 正常文档：标题只比正文大一点，没有「一眼主体」，全部保留才是对的
        return Subject(kept=list(items), applied=False,
                       reason=f"字号层次平缓（最大 {top:.0f}px / 正文 {body:.0f}px），未过滤")

    band = _size_band(items)
    if len(band) >= len(items):
        return Subject(kept=list(items), applied=False, reason="区域内只有一层文字")

    band, fam = _narrow_by_color(band)
    kept_ids = {id(i) for i in band}
    kept = [i for i in items if id(i) in kept_ids]
    dropped = [i for i in items if id(i) not in kept_ids]
    if not kept:
        return Subject(kept=list(items), applied=False, reason="未能确定主体")

    height = statistics.median(i.h for i in kept)
    label = (f"{fam}色 · " if fam else "") + f"{height:.0f}px 大字号"
    return Subject(kept=kept, dropped=dropped, applied=True, label=label,
                   reason="按字号（+ 色系）判定主体", family=fam)


def _select_color(items, parsed: dict) -> Subject:
    fam = parsed["family"]
    cand = [i for i in items if ink_of(i).colored and ink_of(i).family == fam]
    if not cand:
        return Subject(kept=list(items), applied=False,
                       reason=f"区域内没有{fam}色文字，未过滤")

    top = max(i.h for i in cand)
    body = _body_height(items)
    floor = max(top * BAND_FLOOR, body * parsed["ratio"])
    kept = [i for i in cand if i.h >= floor]
    if not kept:
        kept = [i for i in cand if i.h >= top * 0.8] or list(cand)
    kept_ids = {id(i) for i in kept}
    dropped = [i for i in items if id(i) not in kept_ids]
    if not dropped:
        return Subject(kept=list(items), applied=False, reason="区域内只有主体文字")
    height = statistics.median(i.h for i in kept)
    return Subject(kept=kept, dropped=dropped, applied=True,
                   label=f"{fam}色 · {height:.0f}px 大字号",
                   reason=f"按色系（{fam}）+ 字号判定主体", family=fam)
