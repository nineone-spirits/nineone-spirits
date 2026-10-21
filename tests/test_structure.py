"""版面结构单测：网格 / 表格 / 分栏 / 多字号混排。

全部用合成坐标（不跑 OCR、不依赖模型），断言的是「结构判定 + 拼字结果」，
所以任何时候都能跑，也跑得很快。真实截图的端到端验证在 test_grid_e2e.py。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from screengrab.layout import TextItem, build            # noqa: E402
from screengrab.tidy import TidyOptions, tidy           # noqa: E402

_passed = 0


def check(name: str, cond: bool, detail: object = "") -> None:
    global _passed
    if cond:
        _passed += 1
        print(f"  ok  {name}")
    else:
        print(f"  FAIL {name}\n       {detail}")
        raise AssertionError(name)


def cjk(ch: str) -> bool:
    return "\u4e00" <= ch <= "\u9fff"


def item(text: str, cx: float, y: float, h: float = 14.0,
         width: float | None = None) -> TextItem:
    """以中心点摆放一个文本框（图标名是居中排列的，用中心点更贴近真实）。"""
    if width is None:
        width = sum(h if cjk(c) else h * 0.55 for c in text)
    return TextItem(text, cx - width / 2, y, cx + width / 2, y + h, 0.99)


def left_item(text: str, x: float, y: float, h: float = 14.0) -> TextItem:
    width = sum(h if cjk(c) else h * 0.55 for c in text)
    return TextItem(text, x, y, x + width, y + h, 0.99)


# ------------------------------------------------------------------ 网格
def test_icon_grid() -> None:
    print("图标网格（居中排列 + 标签折行 + 跨列框）：")
    items = [
        # 第 1 行
        item("此电脑", 60, 40), item("剪映专业版", 180, 40),
        item("百度网盘", 300, 40), item("豆包", 420, 40),
        # 第 2 行：第 1 列与第 4 列的标签各折成两行
        item("Plain Craft", 60, 120), item("ToDesk", 180, 120),
        item("实践", 300, 120), item("DeepSeek", 420, 120),
        item("Launche...", 60, 141), item("Harness", 420, 141),
        # 第 3 行：OCR 把两个标签吞进了一个框
        TextItem("Honeyview 联想超级文件", 2, 220, 242, 240, 0.97),
        item("明日方舟", 300, 220),
    ]
    doc = build(items)
    check("识别为网格", doc.kind == "grid", doc.kind)
    check("四列", doc.n_cols == 4, doc.n_cols)
    rows = doc.text.split("\n")
    check("三行", len(rows) == 3, rows)
    check("第 1 行四列对齐",
          rows[0] == "此电脑\t剪映专业版\t百度网盘\t豆包", rows[0])
    check("折行标签在单元内接回",
          rows[1] == "Plain Craft Launche...\tToDesk\t实践\tDeepSeek Harness", rows[1])
    check("跨列框被切开并各归其列",
          rows[2] == "Honeyview\t联想超级文件\t明日方舟", rows[2])
    check("网格行全部带结构标记", all(r.kind == "grid" for r in doc.rows), doc.rows)


def test_table() -> None:
    print("左对齐参数表：")
    items = []
    for i, (a, b, c) in enumerate([
        ("名称", "默认值", "说明"),
        ("hotkey", "ctrl+alt+q", "全局热键"),
        ("min_score", "0.5", "置信度下限"),
        ("layout_mode", "verbatim", "排版模式"),
    ]):
        y = 40 + i * 30
        items += [left_item(a, 20, y), left_item(b, 140, y), left_item(c, 300, y)]
    doc = build(items)
    check("识别为网格/表格", doc.kind == "grid", doc.kind)
    rows = doc.text.split("\n")
    check("四行三列", len(rows) == 4 and all(r.count("\t") == 2 for r in rows), rows)
    check("表头完整", rows[0] == "名称\t默认值\t说明", rows[0])


def test_dense_table_rows() -> None:
    """紧密表格：行距（10px）小于 0.6 倍字高（12px），不能被当作折行并掉。"""
    print("紧密两列表格（行距小于字高的一半）：")
    items = []
    for i, (k, v) in enumerate([("姓名", "张三"), ("部门", "研发"), ("工号", "A1024")]):
        y = 40 + i * 30
        items += [left_item(k, 20, y), left_item(v, 160, y)]
    doc = build(items)
    rows = doc.text.split("\n")
    check("三行不塌成一行", len(rows) == 3, rows)
    check("键值各归其列", rows[0] == "姓名\t张三", rows[0])
    check("每行都有制表符", all("\t" in r for r in rows), rows)


def test_single_column_labels() -> None:
    print("单列标签（无句末标点、行行短）：")
    items = [left_item(t, 20, 40 + i * 26) for i, t in enumerate(
        ["此电脑", "回收站", "控制面板", "微信", "QQ"])]
    doc = build(items)
    check("不是网格（只有一列）", doc.kind == "prose", doc.kind)
    out = tidy(doc.text, rows=doc.rows)
    check("一行一个，不糊成一段", out.text.count("\n") == 4, out.text)


# ------------------------------------------------------------------ 分栏
def test_two_columns() -> None:
    print("报纸式两栏：")
    left = [
        "本次改版把识别链拆成三段：",
        "抓屏、版面还原、文本整理。",
        "版面还原把零散文本框拼回行，",
        "文本整理负责纠错与合段。",
    ]
    right = [
        "第二栏从另一个角度说同一件事：",
        "所有中间结果都可序列化，",
        "因此可以离线回放一次识别过程，",
        "排查问题时比凭记忆描述可靠。",
    ]
    items = []
    for i, t in enumerate(left):
        items.append(left_item(t, 20, 40 + i * 22, 14))
    for i, t in enumerate(right):
        items.append(left_item(t, 340, 40 + i * 22, 14))
    doc = build(items)
    check("识别为分栏", doc.kind == "columns", (doc.kind, doc.n_cols))
    first_left = doc.text.find("本次改版")
    last_left = doc.text.find("文本整理负责")
    first_right = doc.text.find("第二栏")
    check("读完整栏再换栏", -1 < first_left < last_left < first_right, doc.text)


# ------------------------------------------------------------------ 多字号
def test_mixed_sizes() -> None:
    print("多字号混排（标题 32 / 小标题 20 / 正文 14 / 注释 10）：")
    items = [
        item("识 别 引 擎 选 型 报 告", 300, 10, h=32),
        item("第三季度评审稿", 300, 56, h=16),
        left_item("一、为什么不用云端大模型", 20, 110, 20),
        left_item("因为屏幕截图里经常有客户名、合同金额、内部链接，", 20, 150),
        left_item("一旦上行就意味着数据出境，合规上过不了评审。", 20, 172),
        left_item("本地模型虽然慢一点，但整条链路可以断网运行。", 20, 194),
        left_item("二、为什么选 PP-OCRv6", 20, 240, 20),
        left_item("旧版 mobile 模型会把英文单词之间的空格吃掉，", 20, 280),
        left_item("而界面文字里中英混排是常态，空格丢失后几乎不可读。", 20, 302),
        left_item("注：以上结论基于本机 200 张界面截图的回归测试。", 20, 360, 10),
    ]
    doc = build(items)
    out = tidy(doc.text, rows=doc.rows)
    lines = out.text.split("\n")
    check("标题独立成行且前后留空",
          lines[0].strip() == "识别引擎选型报告" and lines[1] == "", lines[:4])
    check("标题层最大字号", doc.rows[0].level == 0, doc.rows[0])
    check("正文层字号小于标题", doc.rows[3].level > doc.rows[0].level,
          (doc.rows[3].level, doc.rows[0].level))
    check("正文同段合并（跨行接起来）",
          "因为屏幕截图里经常有客户名、合同金额、内部链接，一旦上行就意味着数据出境"
          in out.text.replace("\n", ""), out.text)
    check("小标题不与正文粘连", "一、为什么不用云端大模型因为" not in out.text, out.text)
    check("注释不与正文粘连",
          "本地模型虽然慢一点，但整条链路可以断网运行。注：" not in out.text, out.text)
    check("注释单独成段", lines[-1].startswith("注："), lines[-2:])


# ------------------------------------------------------------------ 图标徽标
def test_glyph_drop() -> None:
    print("图标被识成单个字母：")
    items = [
        # 2 列 × 3 行，构成一个网格；第 2 列第 1 行是 Word 图标
        item("此电脑", 60, 40), item("软件结构.", 180, 40),
        item("W", 180, 20, 17),           # Word 图标被识别成字母
        item("docx", 180, 61, 17),
        item("回收站", 60, 120), item("WorkBuddy", 180, 120),
        item("微信", 60, 200), item("腾讯会议", 180, 200),
    ]
    doc = build(items)
    check("徽标被剔除", doc.dropped == ["W"], doc.dropped)
    out = tidy(doc.text, rows=doc.rows, dropped=doc.dropped)
    check("整理稿里没有孤立字母", "W 软件结构" not in out.text, out.text)
    check("单元内接回文件名", "软件结构.docx" in out.text, out.text)
    check("剔除动作进明细",
          any(c.label == "忽略图标/徽标字符" for c in out.changes),
          [c.label for c in out.changes])
    check("原文视图仍保留（可追溯）", "W" in build(items, keep_glyphs=True).text,
          build(items, keep_glyphs=True).text)


def test_filename_punct() -> None:
    print("文件名 / 省略号不被当成标点改写：")
    items = [
        item("软件结构.docx", 60, 40), item("Plain Craft Launche...", 250, 40),
        item("v1.2.3", 60, 120), item("a/b", 180, 120),
        item("报告.pdf", 60, 200), item("setup.exe", 180, 200),
    ]
    doc = build(items)
    out = tidy(doc.text, rows=doc.rows)
    check("扩展名点号保留", "软件结构.docx" in out.text, out.text)
    check("真正的省略号保留", "Launche..." in out.text, out.text)
    check("版本号保留", "v1.2.3" in out.text, out.text)


def test_wrap_join_still_works() -> None:
    print("单栏正文的硬换行仍然合并：")
    items = [
        left_item("本周完成了三项主要工作，分别是接口联调、性能优化", 20, 40),
        left_item("和灰度发布。接口平均耗时从 380ms 降到 210ms，", 20, 62),
        left_item("性能优化主要针对数据库慢查询，新增了 4 个联合索引。", 20, 84),
    ]
    doc = build(items)
    out = tidy(doc.text, rows=doc.rows)
    check("三行合成一段", out.text.count("\n") == 0, out.text)
    check("中文之间不插空格", "性能优化和灰度发布" in out.text, out.text)


def test_verbatim_mode_untouched() -> None:
    print("逐行模式不做合段：")
    items = [left_item(t, 20, 40 + i * 22) for i, t in enumerate(
        ["第一行内容不算长", "第二行也不长", "第三行同样短"])]
    check("verbatim 保持三行",
          build(items, "verbatim").text.count("\n") == 2,
          build(items, "verbatim").text)
    check("paragraph 会合并",
          build(items, "paragraph").text.count("\n") <= 1,
          build(items, "paragraph").text)


def main() -> None:
    test_icon_grid()
    test_table()
    test_dense_table_rows()
    test_single_column_labels()
    test_two_columns()
    test_mixed_sizes()
    test_glyph_drop()
    test_filename_punct()
    test_wrap_join_still_works()
    test_verbatim_mode_untouched()
    print(f"通过：{_passed} 项结构断言")


if __name__ == "__main__":
    main()
