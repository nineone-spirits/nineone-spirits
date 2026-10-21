"""文本整理（tidy）单元测试。

覆盖六类行为：断行合并、段落切分、标点统一、空格清理、纠错、保真校验。
运行：python tests/test_tidy.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from screengrab.tidy import TidyOptions, _signature, tidy  # noqa: E402

PASS = 0


def eq(name: str, got, want) -> None:
    global PASS
    if got != want:
        raise AssertionError(f"[{name}]\n  期望: {want!r}\n  实际: {got!r}")
    PASS += 1
    print(f"  ok  {name}")


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS
    if not cond:
        raise AssertionError(f"[{name}] {detail}")
    PASS += 1
    print(f"  ok  {name}")


# ---------------------------------------------------------------- 断行合并
def test_join_wrap() -> None:
    raw = ("本次会议由产品部主持，讨论了第三季度的\r\n"
           "整体进展、存在的问题以及下一阶段的\r\n"
           "重点方向，并对资源投入做了初步测算，\r\n"
           "相关结论将在下周的经营会上同步给各\r\n"
           "业务线负责人确认后正式下发执行。")
    out = tidy(raw)
    eq("硬换行合并为一段", out.text,
       "本次会议由产品部主持，讨论了第三季度的整体进展、存在的问题以及下一阶段的"
       "重点方向，并对资源投入做了初步测算，相关结论将在下周的经营会上同步给各"
       "业务线负责人确认后正式下发执行。")
    check("合并后只有一段", out.paragraphs == 1, f"实际 {out.paragraphs}")
    check("合并计数 > 0", any(c.label == "合并硬换行" for c in out.changes))


def test_keep_sentence_break() -> None:
    """上一行以句号收尾 → 不合并，保持两句。"""
    raw = ("这是一个完整的句子，已经说完了。\n"
           "这一行是另一句话，不应该被接上去。\n"
           "最后一行同样独立成句，保持原有断句。")
    out = tidy(raw)
    eq("句末断行不被合并", out.text.split("\n\n"),
       ["这是一个完整的句子，已经说完了。",
        "这一行是另一句话，不应该被接上去。",
        "最后一行同样独立成句，保持原有断句。"])


def test_blank_line_keeps_paragraph() -> None:
    raw = ("第一段的第一行内容在这里，写得比较长一些，\n"
           "第一段第二行继续，然后结束在这一句。\n"
           "\n"
           "第二段从新的一行开始，也要合成为一段。")
    out = tidy(raw)
    paras = [p for p in out.text.split("\n\n") if p]
    eq("空行分隔的两段都保留", len(paras), 2)
    check("第一段已合并", "第一段第二行" in paras[0] and "\n" not in paras[0])
    eq("第二段独立", paras[1], "第二段从新的一行开始，也要合成为一段。")


def test_list_not_merged() -> None:
    raw = ("准备工作如下：\n"
           "- 收集各部门的反馈意见\n"
           "- 汇总数据并核对口径\n"
           "- 形成初稿提交评审")
    out = tidy(raw)
    check("列表项各自成行", out.text.count("\n- ") == 3, out.text)
    check("列表项之间不用空行", out.text.count("\n\n- ") == 1, out.text)


def test_table_preserved() -> None:
    raw = ("渠道\tGMV（万元）\t同比\n"
           "线上\t1280\t+18.4%\n"
           "线下\t960\t-3.2%")
    out = tidy(raw)
    eq("表格逐行保留", out.text.count("\t"), 6)
    check("表格没有并成一行", out.text.count("\n") == 2, out.text)


# ---------------------------------------------------------------- 标点 / 空格
def test_punctuation() -> None:
    raw = "这是一个测试,包含半角标点;还有(括号)和\"引号\",都要统一。"
    out = tidy(raw)
    eq("半角标点转全角", out.text,
       "这是一个测试，包含半角标点；还有（括号）和“引号”，都要统一。")


def test_numbers_untouched() -> None:
    raw = "版本 3.14 于 2026, 共计 1,000 次调用, 时间 12:30, 详见 https://a.com/x?y=1"
    out = tidy(raw)
    check("千分位逗号保留", "1,000" in out.text, out.text)
    check("小数点保留", "3.14" in out.text, out.text)
    check("时间冒号保留", "12:30" in out.text, out.text)
    check("URL 未被改动", "https://a.com/x?y=1" in out.text, out.text)


def test_ellipsis_and_repeats() -> None:
    eq("三个句号 → 省略号", tidy("他想了很久。。。").text, "他想了很久……")
    eq("重复逗号折叠", tidy("真的吗，，然后呢").text, "真的吗，然后呢")
    eq("多空格折叠（西文）", tidy("hello    world").text, "hello world")


def test_space_cleanup() -> None:
    out = tidy("识 别 结 果 如 下 ：")
    eq("中文之间空格删除", out.text, "识别结果如下：")
    out = tidy("请 查 看 下 图 。")
    eq("中文标点旁空格删除", out.text, "请查看下图。")
    out = tidy("使用 Python 处理数据")
    eq("中英之间的空格保留", out.text, "使用 Python 处理数据")


def test_fullwidth_chars() -> None:
    out = tidy("２０２６ 年第 ３ 季度")
    eq("全角数字转半角", out.text, "2026 年第 3 季度")
    check("字符归一被记录", any(c.label == "全角数字/字母 → 半角" for c in out.changes))


# ---------------------------------------------------------------- 纠错
def test_typo() -> None:
    out = tidy("这个的的方 案因该可以，帐号已开通。")
    eq("重复字 + 错别字纠正", out.text, "这个的方案应该可以，账号已开通。")
    check("纠错后保真等级为 minor", out.fidelity == "minor", out.fidelity)
    check("差异有说明", bool(out.note), out.note)


def test_repeat_safe_words() -> None:
    eq("叠词不被误折叠", tidy("我看看再试试，慢慢来。").text, "我看看再试试，慢慢来。")


def test_digit_confusion() -> None:
    eq("数字里的 O 纠正为 0", tidy("订单号 2O26O9 已生成").text, "订单号 202609 已生成")


# ---------------------------------------------------------------- 保真 / 边界
def test_fidelity_ok() -> None:
    raw = ("这是一个用于验证保真度的段落，内容本身没有被改动，\n"
           "只是把换行和空格重新整理了一遍，标点也做了统一。")
    out = tidy(raw)
    eq("纯格式整理 → 保真 ok", out.fidelity, "ok")
    eq("骨架完全一致", _signature(raw), _signature(out.text))
    check("相似度 1.0", out.similarity > 0.999, str(out.similarity))


def test_empty() -> None:
    out = tidy("")
    eq("空输入返回空", out.text, "")
    eq("空输入不报错", out.total, 0)
    out = tidy("   \n\n  \t ")
    eq("纯空白返回空", out.text, "")


def test_options_off() -> None:
    raw = "这是 一段 文字,带有 半角标点。"
    out = tidy(raw, TidyOptions(fix_punct=False, fix_space=False))
    check("关闭标点整理后保留半角", "," in out.text, out.text)


def test_long_text_perf() -> None:
    import time
    raw = "。".join(["这是一个用于性能验证的句子，包含若干标点和数字 123"] * 400)
    t0 = time.perf_counter()
    out = tidy(raw)
    dt = time.perf_counter() - t0
    check(f"8000 字整理耗时 {dt * 1000:.1f} ms < 300 ms", dt < 0.3, f"{dt:.3f}s")
    check("长文本未丢内容", len(_signature(out.text)) == len(_signature(raw)))


def main() -> None:
    for fn in [
        test_join_wrap, test_keep_sentence_break, test_blank_line_keeps_paragraph,
        test_list_not_merged, test_table_preserved,
        test_punctuation, test_numbers_untouched, test_ellipsis_and_repeats,
        test_space_cleanup, test_fullwidth_chars,
        test_typo, test_repeat_safe_words, test_digit_confusion,
        test_fidelity_ok, test_empty, test_options_off, test_long_text_perf,
    ]:
        print(f"{fn.__name__}:")
        fn()
    print(f"\n通过 {PASS} 项断言")


if __name__ == "__main__":
    main()
