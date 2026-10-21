"""主体文字过滤单测：颜色采样 / 色系判定 / 尺寸带 / 规则解析 / 端到端。

分三层：
  1. 纯几何 + 人工指定 Ink：验证选择规则本身（毫秒级、无依赖）；
  2. 合成像素：验证「从真实像素里读出文字颜色」这件事；
  3. 真 OCR 端到端：把合成图喂给识别引擎，确认整条链路只留下主体文字。
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from screengrab import subject                            # noqa: E402
from screengrab.layout import TextItem, build, group_lines  # noqa: E402
from tests.fonts import cjk_font, skip_note               # noqa: E402

_passed = 0
RED = (214, 32, 74)
BLUE = (32, 96, 214)
GRAY = (150, 150, 150)


def check(name: str, cond: bool, detail: object = "") -> None:
    global _passed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        print(f"  FAIL {name}\n       {detail}")
        raise AssertionError(name)


def ink(family: str, colored: bool, hue: float = -1.0) -> subject.Ink:
    return subject.Ink(rgb=(200, 100, 100), chroma=80.0 if colored else 0.0,
                       hue=hue, family=family, colored=colored)


def item(text: str, x: float, y: float, h: float, family: str = "灰",
         colored: bool = False) -> TextItem:
    width = sum(h if "\u4e00" <= c <= "\u9fff" else h * 0.58 for c in text)
    it = TextItem(text, x, y, x + width, y + h, 0.98)
    it.ink = ink(family, colored)
    return it


def font(size: int) -> ImageFont.FreeTypeFont:
    """合成图要画中文，拿不到中文字体时直接抛——调用方会先判断再进来。"""
    f = cjk_font(size)
    if f is None:
        raise RuntimeError("no cjk font")
    return f


def draw_line(draw: ImageDraw.ImageDraw, xy, text: str, f, color):
    """画一行字，返回它紧贴的包围盒（TextItem 用它当坐标）。"""
    x, y = xy
    draw.text((x, y), text, font=f, fill=color)
    box = draw.textbbox((x, y), text, font=f)
    return box


# --------------------------------------------------------------- 1. 选择规则
def test_rules() -> None:
    big_red = [item(f"标题{i}", 40, 20 + i * 150, 145, "红", True) for i in range(3)]
    small_gray = [item(f"背景正文{i}", 40, 520 + i * 22, 15) for i in range(5)]
    mixed = big_red + small_gray

    sub = subject.select(mixed, "auto")
    check("auto 认出大号红字主体", sub.applied and len(sub.kept) == 3, sub.describe())
    check("auto 滤掉背景小字", len(sub.dropped) == 5, sub.describe())
    check("主体说明含色系与字号", "红" in sub.label and "145" in sub.label, sub.label)

    doc = [item("第一章 概述", 40, 20, 22, "黑")] + \
          [item(f"正文第{i}行内容", 40, 80 + i * 26, 15, "黑") for i in range(8)]
    sub = subject.select(doc, "auto")
    check("普通文档（标题仅略大）不过滤", not sub.applied, sub.reason)
    check("普通文档保留全部", len(sub.kept) == len(doc))

    sub = subject.select([item("就一行", 40, 20, 30, "黑")], "auto")
    check("单行不过滤", not sub.applied and len(sub.kept) == 1)

    sub = subject.select([], "auto")
    check("空输入不炸", sub.kept == [] and not sub.applied)

    sub = subject.select(mixed, "off")
    check("off 模式全保留", not sub.applied and len(sub.kept) == len(mixed))

    sub = subject.select(mixed, "large")
    check("large 强制只留最大档", sub.applied and len(sub.kept) == 3, sub.describe())


def test_color_rule() -> None:
    red = [item("红标题", 40, 20, 140, "红", True)]
    blue = [item("蓝标题", 40, 200, 140, "蓝", True)]
    gray = [item(f"小字{i}", 40, 400 + i * 20, 15) for i in range(4)]
    pool = red + blue + gray

    sub = subject.select(pool, "red")
    check("color:red 只留红字", sub.applied and sub.kept == red, sub.describe())
    check("color:red 滤掉蓝字与小字", len(sub.dropped) == 5)

    sub = subject.select(pool, "color:blue")
    check("color:blue 只留蓝字", sub.kept == blue, sub.describe())

    sub = subject.select(gray + [item("黑大字", 40, 20, 140, "黑")], "green")
    check("找不到该色系时不过滤（不误删）", not sub.applied, sub.reason)

    many_red = [item(f"红{i}", 40, 20 + i * 150, 140, "红", True) for i in range(3)]
    sub = subject.select(many_red + [blue[0]] + gray, "auto")
    check("同带彩色占多数时按色系收敛", sub.applied and len(sub.kept) == 3, sub.describe())


def test_parse_rule() -> None:
    check("parse off", subject.parse_rule("off")["mode"] == "off")
    check("parse None -> off", subject.parse_rule(None)["mode"] == "off")
    check("parse auto", subject.parse_rule("auto")["mode"] == "auto")
    check("parse large", subject.parse_rule("large")["mode"] == "large")
    check("parse red", subject.parse_rule("red")["family"] == "红")
    check("parse 红色", subject.parse_rule("红色")["family"] == "红")
    check("parse color:blue", subject.parse_rule("color:blue")["family"] == "蓝")
    check("parse dict", subject.parse_rule({"mode": "color", "family": "green"})["family"] == "绿")


def test_hue_family() -> None:
    cases = [(0, "红"), (350, "红"), (330, "红"), (30, "橙"), (55, "黄"),
             (120, "绿"), (180, "青"), (220, "蓝"), (285, "紫")]
    for hue, want in cases:
        got = subject._family_of_hue(hue)
        check(f"色相 {hue}° → {want}", got == want, got)


# --------------------------------------------------------------- 2. 像素采样
def make_poster(w: int = 900, h: int = 620):
    """白底：红色大标题 3 行 + 灰色小字 6 行（模拟「大字压在正文上」）。"""
    img = Image.new("RGB", (w, h), "white")
    draw = ImageDraw.Draw(img)
    big = font(72)
    small = font(15)
    boxes = []
    for i, text in enumerate(("帮我安装这个插件", "github.com/Small-tailqwq/", "dsh-deep-whale")):
        box = draw_line(draw, (60, 30 + i * 100), text, big, RED)
        boxes.append(("big", text, box))
    for i in range(6):
        box = draw_line(draw, (60, 380 + i * 34), f"这是页面本身的正文第 {i + 1} 行说明", small, GRAY)
        boxes.append(("small", f"这是页面本身的正文第 {i + 1} 行说明", box))
    return img, boxes


def to_items(boxes) -> list[TextItem]:
    out = []
    for _kind, text, box in boxes:
        out.append(TextItem(text, box[0], box[1], box[2], box[3], 0.97))
    return out


def test_sampling() -> None:
    img, boxes = make_poster()
    items = to_items(boxes)
    import numpy as np
    subject.annotate(np.asarray(img, dtype=np.uint8), items)

    big = [i for i in items if i.h > 40]
    small = [i for i in items if i.h <= 40]
    check("大字被判为彩色", all(i.ink.colored for i in big),
          [(i.text[:8], i.ink.family, i.ink.chroma) for i in big])
    check("大字色系为红", all(i.ink.family == "红" for i in big),
          [(i.ink.hue, i.ink.family) for i in big])
    check("小字被判为灰阶", all(not i.ink.colored for i in small),
          [(i.text[:8], i.ink.family, i.ink.chroma) for i in small])

    sub = subject.select(items, "auto")
    check("合成海报：主体=3 行大字", sub.applied and len(sub.kept) == 3, sub.describe())
    check("合成海报：滤掉 6 行小字", len(sub.dropped) == 6)

    dark = Image.new("RGB", (700, 240), (18, 18, 20))
    d = ImageDraw.Draw(dark)
    b1 = draw_line(d, (30, 20), "深色主题的大标题", font(54), (250, 250, 250))
    b2 = draw_line(d, (30, 150), "这是一行灰阶小字说明", font(15), (150, 150, 150))
    items = [TextItem("深色主题的大标题", b1[0], b1[1], b1[2], b1[3], 0.97),
             TextItem("这是一行灰阶小字说明", b2[0], b2[1], b2[2], b2[3], 0.97)]
    subject.annotate(np.asarray(dark, dtype=np.uint8), items)
    check("深色主题：白字仍是灰阶", not items[0].ink.colored, items[0].ink.family)
    sub = subject.select(items, "auto")
    check("深色主题：按字号仍能选出主体", sub.applied and len(sub.kept) == 1, sub.describe())


# --------------------------------------------------------------- 3. 行聚合
def test_line_grouping() -> None:
    """大标题与背后小字在同一垂直带时，不能被聚成一行。"""
    big = TextItem("大标题文字", 40, 100, 400, 220, 0.98)
    tiny = TextItem("背后的正文小字", 60, 150, 260, 166, 0.98)
    lines = group_lines([big, tiny])
    check("字号悬殊时不并成一行", len(lines) == 2, [(l.text if hasattr(l, 'text') else len(l.items)) for l in lines])

    a = TextItem("同一行的前半段", 40, 100, 260, 116, 0.98)
    b = TextItem("后半段", 270, 101, 340, 117, 0.98)
    check("同字号仍正常并行", len(group_lines([a, b])) == 1)

    # 竖向堆叠的大字：检测框彼此重叠，只有「水平压盖」能拦住
    top = TextItem("帮我安装这个插件", 60, 100, 760, 240, 0.98)
    mid = TextItem("github.com/xxx/", 90, 190, 800, 330, 0.98)
    check("竖向堆叠的大字不并成一行", len(group_lines([top, mid])) == 2)


# --------------------------------------------------------------- 4. 端到端
def test_e2e() -> None:
    from screengrab.ocr import OcrService

    img, _boxes = make_poster()
    svc = OcrService(min_score=0.5)
    res = svc.recognize(img)
    check("端到端识别到文字", len(res.items) >= 6, len(res.items))
    check("每个框都带颜色特征", all(getattr(i, "ink", None) is not None for i in res.items))

    sub = subject.select(res.items, "auto")
    check("端到端 auto 触发过滤", sub.applied, sub.describe())

    text = build(sub.kept, "verbatim").text
    check("结果含大标题", "帮我安装这个插件" in text.replace(" ", ""), text)
    check("结果不含背景小字", "页面本身的正文" not in text, text)
    check("被滤掉的框都是灰阶小字",
          all(not subject.ink_of(i).colored for i in sub.dropped),
          [(i.text[:10], subject.ink_of(i).family) for i in sub.dropped])


def main() -> int:
    print("== 选择规则 ==")
    test_rules()
    print("== 色系规则 ==")
    test_color_rule()
    print("== 规则解析 ==")
    test_parse_rule()
    print("== 色相归类 ==")
    test_hue_family()
    # 下面两节要真的把中文画进图里，没有中文字体就无法执行（CI 镜像默认没装）
    if cjk_font(24) is None:
        print("== 像素采样 / 端到端 ==")
        print("  " + skip_note("像素采样与端到端用例"))
    else:
        print("== 像素采样 ==")
        test_sampling()
        print("== 行聚合 ==")
        test_line_grouping()
        print("== 端到端 ==")
        test_e2e()
    print(f"\n通过：{_passed} 项主体过滤断言")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
