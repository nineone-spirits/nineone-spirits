"""NineOne Spirits（九一的酒）· 屏幕取字（TextGrabber）—— 屏幕任意区域文字提取工具。

模块职责：
  winutil       Win32 底层（DPI 感知 / 窗口定位 / 显示器枚举 / 单实例 / 剪贴板）
  hotkey        全局热键（RegisterHotKey + 独立消息循环）
  capture       桌面抓图（虚拟屏坐标换算）
  overlay       框选遮罩（每屏一个窗口 + 遮罩 + 放大镜 + 尺寸提示）
  ocr           OCR 后端（RapidOCR 默认 / PaddleOCR 可选）+ 屏幕文本预处理 + 置信度过滤
  subject       主体过滤（墨迹颜色采样 + 尺寸带 + 色系收敛，只留用户要的那层文字）
  structure     结构判定（列候选 / 逐行签名 / 区块切分 / 单元还原 / 字号分层）
  layout        版面还原（按区块分派：网格 / 分栏 / 正文；输出行元信息）
  tidy          文本整理（字符归一 / 标点统一 / 空格清理 / 断行重排 / 段落重组 / 保守纠错）
  pill          悬浮按钮
  result_window 结果窗口（整理/原文双视图 / 整理明细 / 主体切换 / 可编辑 / 复制 / 重新识别）
  app           状态机与线程编排

版本号在本文件里维护（单处来源），打包元数据从 `__version__` 动态读取，
见 pyproject.toml 的 `[tool.setuptools.dynamic]`。
"""

__version__ = "1.3.0"
