"""真实截图端到端：桌面图标网格（复杂场景回归）。

用的是一张桌面截图（4 列 × 9 行的图标网格，含标签折行、OCR 把两个标签吞进一个框、
Word 图标被识成字母 W、压缩包角标 ZIP）。截图不进仓库（含个人文件名），
找不到时自动跳过，不影响其他测试——见 `tests/fixture.py`。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image                                  # noqa: E402

from screengrab.layout import build                    # noqa: E402
from screengrab.ocr import OcrService                  # noqa: E402
from screengrab.tidy import tidy                       # noqa: E402
from tests.fixture import shot_path, skip_note         # noqa: E402

_passed = 0


def check(name: str, cond: bool, detail: object = "") -> None:
    global _passed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        print(f"  FAIL {name}\n       {detail}")
        raise AssertionError(name)


def main() -> None:
    SHOT = shot_path()
    if SHOT is None:
        print(skip_note())
        return
    print(f"桌面图标网格（{SHOT.name}）：")
    res = OcrService().recognize(Image.open(SHOT))
    t0 = time.perf_counter()
    doc = build(res.items)
    tidied = tidy(doc.text, rows=doc.rows, dropped=doc.dropped)
    cost = (time.perf_counter() - t0) * 1000

    check("判定为网格", doc.kind == "grid", doc.kind)
    check("四列", doc.n_cols == 4, doc.n_cols)
    rows = doc.text.split("\n")
    check("九行", len(rows) == 9, rows)
    check("行内按列分隔", all(1 <= r.count("\t") <= 3 for r in rows), rows)
    check("满行的行有四列", sum(1 for r in rows if r.count("\t") == 3) >= 5, rows)
    check("首行四列正确",
          rows[0] == "此电脑\t剪映专业版\t百度网盘\t豆包", rows[0])
    check("不再把四个图标名拼成一句", "此电脑剪映" not in doc.text, doc.text)
    check("折行标签在单元内接回",
          "Microsoft Edge" in rows[2] and "DeepSeek Harness" in rows[1], rows[:3])
    check("同一文件名的两行接回", "软件结构.xoop" in rows[2], rows[2])
    check("跨列框被切开", rows[6] == "Honeyview\t联想超级文件\t明日方舟", rows[6])
    check("末尾图标不被切断", "SakuraFrp 启动器" in rows[8], rows[8])
    check("徽标字符被识别并记录", set(doc.dropped) == {"W", "ZIP"}, doc.dropped)
    check("整理不再改动结构", tidied.text == doc.text.strip(), tidied.text)
    check("明细里能看到徽标剔除",
          any(c.label == "忽略图标/徽标字符" for c in tidied.changes),
          [c.label for c in tidied.changes])
    check("保真", tidied.fidelity == "ok", tidied.note)
    check(f"结构分析耗时可忽略（{cost:.1f} ms）", cost < 80, f"{cost:.1f} ms")

    print("\n整理结果：")
    print(tidied.text)
    print(f"\n通过：{_passed} 项（结构分析 {cost:.1f} ms）")


if __name__ == "__main__":
    main()
