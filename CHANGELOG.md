# 变更日志

本项目的所有重要变更都记录在这里。格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)：`主版本.次版本.修订号`。

- **主版本**：不兼容的行为变化（配置项改名、命令行参数变化、最低 Python 版本提升）
- **次版本**：向下兼容的新功能
- **修订号**：向下兼容的问题修复

## [未发布]

（暂无）

## [1.3.0] - 2026-10-21

### 新增

- **主体文字过滤**（`screengrab/subject.py`）：按「字号 × 墨迹彩度」自动识别框选区域里用户真正要的那一层文字，
  滤掉压在主体上的背景小字。默认开启，可从结果窗「主体 3/8」按钮一键切回全部，或在悬浮球右键整体关闭。
- 配置项 `subject_filter`：`auto`（默认）/ `off` / `large` / `red` / `color:blue`。
- 结果窗新增主体切换按钮；「整理明细」会写明判定依据（`主体 红色 · 144px 大字号 · 滤掉 5 框`）。
- `python -m screengrab` 启动方式与 `textgrabber` 命令入口。

### 修复

- **大标题与背景小字被拼成一行**：行聚类新增两道闸——行内框高差 >2.2 倍、水平重叠率 >0.35 均不并成一行。
  修复前，同一区域会输出 122 字的乱序文本；修复后正确还原为 3 行。
- 主体过滤在「找不到指定色系」时不再删除任何文字，改为回退全部。

### 变更

- 手写笔/美术字场景下「原文」视图的阅读顺序更接近原图。
- 文档：`docs/技术方案.html` 新增第 09 节（主体文字过滤），原 09~12 节顺延。
- **首次公开发布**：项目归属与品牌统一为 **NineOne Spirits（九一的酒）**（README 标题、应用窗口标题、
  技术方案文档标题），许可证署名为 `Copyright (c) 2026 Jiuyi Jiu`，仓库地址为
  `github.com/nineone-spirits/nineone-spirits`。
- README 路线图改为带成本与约束评估的待办表；「表格结构识别」「语义级整理」两项与
  「离线 + 轻量 + 不改写内容」的既有取舍冲突，标记为待决策。

## [1.2.0] - 2026-10-21

### 新增

- **文本整理**（`screengrab/tidy.py`）：识别后自动合并被窗口截断的硬换行、统一中英文标点、
  清理汉字之间的噪声空格、按标题/列表重新分块，并对高置信错别字做保守纠错。
- 结果窗「整理 / 原文」双视图与「整理明细」面板：每类改动的次数、前后样例、内容相似度都可核对。
- 配置项 `tidy_enabled`、`result_view`；悬浮球右键可关闭自动整理。

### 变更

- 结果窗改为自动折行、无横向滚动条；窄窗下按钮自动排成 2×2。

## [1.1.0] - 2026-10-20

### 新增

- **结构判定**（`screengrab/structure.py`）：列候选聚类 / 逐行签名 / 区块切分 / 单元还原 / 字号分层，
  区分桌面图标网格、参数表、分栏正文三种版面。
- `layout.py` 重写为「按块分派」排版：网格按列位输出制表符对齐，分栏按整栏阅读顺序，多字号标题自成一档。

### 修复

- 网格里相邻两行被塌成一行（`姓名张三 部门研发`）；单字母徽标（`W`、`ZIP`）不再独占一行。

## [1.0.0] - 2026-10-20

### 新增

- 首次发布：全局热键 `Ctrl+Alt+Q` 框选 → 本地 RapidOCR 识别 → 结果窗可编辑/一键复制。
- 悬浮球入口、9× 像素放大镜、`Ctrl+Alt+D` 重识别上次区域、多显示器与高 DPI 适配。
- 可插拔 OCR 后端与降级链：RapidOCR 3.x → RapidOCR 1.x → PaddleOCR。
- 配置持久化到 `%APPDATA%\TextGrabber\config.json`。

[未发布]: https://github.com/nineone-spirits/nineone-spirits/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.3.0
[1.2.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.2.0
[1.1.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.1.0
[1.0.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.0.0
