"""端到端验证：合成「像真实界面截图」的图片 → 跑 OCR → 还原版面。

覆盖：中英混排、标题/正文/列表缩进、表格列、11px 小字、深色主题反色。
运行：python -m tests.test_pipeline
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab.layout import TextItem, to_text          # noqa: E402
from screengrab.ocr import OcrService                     # noqa: E402

FONT_CANDIDATES = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhl.ttc",
                   r"C:\Windows\Fonts\simhei.ttf"]


def load_font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_ui_image(dark: bool = False, scale: float = 1.0) -> Image.Image:
    W, H = int(760 * scale), int(430 * scale)
    bg = "#1E1F22" if dark else "#FFFFFF"
    fg = "#E6E6E6" if dark else "#1F2328"
    sub = "#9BA1A6" if dark else "#57606A"
    img = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(img)

    f_title = load_font(int(22 * scale))
    f_body = load_font(int(15 * scale))
    f_small = load_font(int(11 * scale))

    def at(x, y, text, font, color=None):
        d.text((int(x * scale), int(y * scale)), text, font=font, fill=color or fg)

    at(28, 22, "第三季度经营分析报告", f_title)
    at(28, 60, "Revenue grew 18.6% QoQ, driven by overseas expansion.", f_body, sub)
    at(28, 92, "一、核心结论", f_body)
    at(52, 122, "1. 华东区域营收 ¥3,482 万元，同比增长 24.3%；", f_body)
    at(52, 152, "2. 客单价提升至 ¥286，复购率 41.2%（环比 +3.1pt）；", f_body)
    at(52, 182, "3. 供应链成本上升，毛利率下降 1.8 个百分点。", f_body)

    at(28, 224, "二、分渠道数据", f_body)
    head_y, row_y = 254, 282
    at(52, head_y, "渠道", f_small, sub)
    at(200, head_y, "GMV（万元）", f_small, sub)
    at(380, head_y, "同比", f_small, sub)
    at(520, head_y, "备注", f_small, sub)
    rows = [("天猫旗舰店", "1,284.5", "+21.4%", "主推新品"),
            ("京东自营", "962.1", "+13.8%", "库存偏低"),
            ("抖音直播", "548.7", "+62.5%", "达人矩阵")]
    for i, (a, b, c, dtx) in enumerate(rows):
        y = row_y + i * 26
        at(52, y, a, f_small)
        at(200, y, b, f_small)
        at(380, y, c, f_small)
        at(520, y, dtx, f_small)

    at(28, 372, "注：数据统计截至 2026-09-30，含税。 Contact: ops@example.com", f_small, sub)
    return img


def run_ocr(svc: OcrService, image: Image.Image, label: str) -> None:
    t0 = __import__("time").perf_counter()
    res = svc.recognize(image)
    total = __import__("time").perf_counter() - t0
    print(f"\n{'=' * 66}\n[{label}]  {res.engine}  识别 {res.elapsed:.2f}s / 总 {total:.2f}s  "
          f"放大 {res.scale:.2f}x  反色 {res.inverted}")
    print("-" * 66)
    print("逐行模式：")
    print(to_text(res.items, "verbatim"))
    print("-" * 66)
    print("智能合段：")
    print(to_text(res.items, "paragraph"))
    print("-" * 66)
    print("统计:", res.stats)


def test_layout_units() -> None:
    """纯逻辑用例：行聚类 / 中文不插空格 / 表格制表符 / 段间距 / 缩进。"""
    def box(x, y, w, h, text, score=0.99):
        return TextItem(text, x, y, x + w, y + h, score)

    items = [
        box(40, 40, 220, 22, "第一章 总则"),
        box(60, 90, 180, 20, "第一条 为规范管理"),
        box(240, 90, 160, 20, "制定本办法。"),
        box(60, 120, 340, 20, "第二条 本办法适用于全体员工。"),
        box(60, 200, 120, 20, "姓名"),
        box(300, 200, 80, 20, "部门"),
        box(60, 230, 120, 20, "张三"),
        box(300, 230, 80, 20, "研发"),
    ]
    out = to_text(items, "verbatim")
    print("\n[layout] verbatim:\n" + out)
    assert "第一章" in out.splitlines()[0]
    assert "第一条 为规范管理制定本办法。" in out, "同一行两段文字应无缝拼成一句"
    assert "\t" in out, "跨列内容应输出制表符以保留表格结构"
    assert "\n\n" in out, "较大行间距应折叠成空行"

    para = to_text(items[:4], "paragraph")
    print("\n[layout] paragraph:\n" + para)
    assert "第一条 为规范管理制定本办法。" in para.replace("\n", "")


if __name__ == "__main__":
    test_layout_units()
    service = OcrService()
    run_ocr(service, make_ui_image(), "浅色界面 100%")
    run_ocr(service, make_ui_image(dark=True), "深色界面 100%")
    run_ocr(service, make_ui_image(scale=0.6), "125% 缩放下的小字模拟")
    run_ocr(service, make_ui_image().crop((40, 100, 430, 205)), "局部小范围")
