"""端到端验证：合成「窄栏正文」截图 → OCR → 版面还原 → 文本整理。

模拟的是最常见的一类目标：网页正文 / 聊天记录 / PDF 段落，被窗口宽度切成
一堆短行，且带着 OCR 常见的半角标点、汉字间空格。验证整理能否把这种
「一堆行」还原成能直接粘贴使用的段落，同时不丢内容。

运行：python tests/test_tidy_e2e.py
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab.layout import to_text            # noqa: E402
from screengrab.ocr import OcrService            # noqa: E402
from screengrab.tidy import _signature, tidy     # noqa: E402

FONT_CANDIDATES = [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\simhei.ttf"]

LINES = [
    "项目周报（2026 年第 41 周）",
    "",
    "本周完成了三项主要工作,分别是接口联调、性能",
    "优化和灰度发布。接口联调覆盖了 12 个外部服务,",
    "平均响应时间从 380ms 降到 210ms;性能优化主",
    "要针对数据库慢查询,新增了 4 个联合索引。",
    "",
    "下 周 计 划:",
    "- 推进第二阶段的容量压测",
    "- 补齐监控告警的覆盖盲区",
    "- 完成 2026 年度预算的初稿编制",
]


def load_font(size: int):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                continue
    return ImageFont.load_default()


def make_image() -> Image.Image:
    W, H = 620, 60 + len(LINES) * 28
    img = Image.new("RGB", (W, H), "#FFFFFF")
    d = ImageDraw.Draw(img)
    font = load_font(16)
    y = 26
    for line in LINES:
        if line:
            d.text((30, y), line, font=font, fill="#1F2328")
        y += 28
    return img


def main() -> None:
    from tests.fonts import has_cjk_font, skip_note
    if not has_cjk_font():
        print(skip_note("合成窄栏截图的端到端用例"))
        return
    image = make_image()
    out_path = Path(__file__).resolve().parents[1] / "docs" / "img" / "tidy-source.png"
    image.save(out_path)

    svc = OcrService()
    svc.warmup()
    t0 = time.perf_counter()
    res = svc.recognize(image)
    ocr_s = time.perf_counter() - t0

    raw = to_text(res.items, "verbatim")
    t1 = time.perf_counter()
    result = tidy(raw)
    tidy_ms = (time.perf_counter() - t1) * 1000

    print("=" * 70)
    print(f"OCR {ocr_s:.2f}s · {res.engine} · {len(res.items)} 个文本框 · "
          f"置信度 {res.stats['avg_score'] * 100:.1f}%")
    print("-" * 70)
    print("【逐行原文】")
    print(raw)
    print("-" * 70)
    print("【整理后】")
    print(result.text)
    print("-" * 70)
    print(f"整理 {result.total} 处 / {tidy_ms:.1f} ms / {result.paragraphs} 段 / "
          f"相似度 {result.similarity * 100:.1f}% / {result.fidelity}：{result.note}")
    for c in result.changes:
        print(f"  · {c.label} ×{c.count}   {c.before} → {c.after}")
    print("=" * 70)

    # ---- 断言：能合段、去噪、保真
    assert result.text.count("\n") < raw.count("\n"), "断行没有被合并"
    assert "分别是接口联调" in result.text.replace("\n", ""), "合并处丢了内容"
    assert "工作," not in result.text, "半角逗号未转全角"
    assert "ms;" not in result.text, "半角分号未转全角"
    assert "下 周 计 划" not in result.text, "汉字之间的空格未清理"
    assert result.text.count("\n- ") == 3, f"列表项应保持 3 行，实际：{result.text}"
    assert "，\n" not in result.text.replace("\r", ""), "段落内部仍有硬换行"
    assert result.paragraphs >= 2, "标题与正文、正文与列表之间应分段"
    assert result.fidelity in ("ok", "minor"), f"保真校验异常：{result.fidelity}"
    assert len(_signature(raw)) - len(_signature(result.text)) <= 4, "内容骨架差异过大"
    print("通过：合段、标点统一、空格清理、列表保留、内容保真")


if __name__ == "__main__":
    main()
