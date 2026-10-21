# NineOne Spirits (九一的酒)

**屏幕取字 · TextGrabber**

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![Platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-lightgrey.svg)](#环境要求)
[![Offline](https://img.shields.io/badge/100%25-offline-success.svg)](#隐私)
[![Version](https://img.shields.io/badge/version-1.3.0-blue.svg)](CHANGELOG.md)

在**任意软件窗口、网页或 PDF** 上按一次热键框选，本地识别中英文混排文字，
**只留下你真正要的那层文字**，自动整理成通顺段落，可编辑、可一键复制。
纯离线运行，截图不出本机。

![结果窗](docs/img/subject.png)

## 它解决什么问题

截图取字这件事本身不难，难的是**取出来能直接用**。现成方案通常在三处掉链子：

1. **把不该要的文字也认出来**。视频上的大字标题底下压着页面正文，两层文字一起进结果，读出来是一锅粥。
2. **版式全丢**。表格变成一列、两栏正文左右串行、标题和正文粘在同一个段落里。
3. **认完还得手工收拾**。一段话被窗口切成四行、汉字之间夹着 OCR 的空格、半角标点混在全角里。

这个工具针对的就是这三点。同一块区域，1.2.0 和 1.3.0 的差别：

<table>
<tr><th width="50%">1.2.0 输出（1 行 122 字）</th><th width="50%">1.3.0 输出（3 行 47 字）</th></tr>
<tr><td><code>github.com/Small-tailqwq/对话用中文展示思考过程轨迹帮我安装这个插件： dsh-deep直接展示后面合温导现能物的是给出结构化的推 o-whale提，判断体据，备选方案为什么选它原始思到全的疑点 反复推翻的中间结论。15:45</code></td>
<td><code>帮我安装这个插件：<br>github.com/Small-tailqwq/<br>dsh-deep-whale</code></td></tr>
</table>

## 功能特性

**取字**

- 全局热键 `Ctrl+Alt+Q` 框选，任意窗口/网页/PDF 通用；`Ctrl+Alt+D` 重新识别上次区域（内容滚动、刷新时最省事）
- 9× 像素放大镜跟随光标，左上角实时显示选区尺寸，方便精确框住一行字
- 多显示器、负坐标、100%/125%/150% 缩放都能正确取到目标区域

**主体文字过滤**

- 按「字号 × 墨迹彩度」判断哪一层是主体，自动滤掉压在主体上的背景小字
- 结果窗「主体 3/8」按钮一键切回全部文字，滤掉了什么随时可查，不是黑箱
- 可指定色系（`subject_filter: red`），也可整体关闭

**版面还原**

- 桌面图标网格、参数表按原列位输出，列间用制表符对齐，不靠空格凑
- 分栏正文按整栏阅读顺序还原，不会左右串行
- 多字号页面按字号分层，标题自成一档、不与正文粘连

**文本整理**

- 合并被窗口截断的硬换行、统一中英文标点、清掉汉字之间的噪声空格、按标题/列表重新分块
- 保守纠错：只做重复字、数字串混淆与 24 条高置信错别字，不做形近字替换、不接云端模型改写内容
- 每类改动都有计数与前后样例，附内容相似度；随时可切回逐行原文

**隐私**

- 识别全程在本机完成，**不联网、不上传**任何截图或文本
- 不做键盘记录、不注入其它进程、不读取其它程序内存
- 配置只落在本机 `%APPDATA%\TextGrabber\config.json`

## 截图

| 框选与放大镜 | 网格 / 表格还原 |
| --- | --- |
| ![overlay](docs/img/overlay.png) | ![grid](docs/img/grid.png) |

| 整理明细（改了什么一目了然） | 全部文字（点「主体 3/8」切回） |
| --- | --- |
| ![tidy](docs/img/tidy-details.png) | ![all](docs/img/subject-off.png) |

## 快速开始

### 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（依赖 `RegisterHotKey` 与 GDI 抓屏，**暂不支持 macOS / Linux**） |
| Python | 3.10+，且必须带 `tkinter`（python.org 官方安装包默认自带） |
| 磁盘 | 约 300 MB（依赖约 110 MB） |
| GPU | 不需要，CPU 推理；单张截图约 0.4 s，首次启动预热 2–3 s |

自检解释器：

```bat
python -c "import tkinter; print('ok')"
```

### 安装

**方式一：一键脚本（推荐）**

```bat
git clone https://github.com/nineone-spirits/nineone-spirits.git
cd textgrabber
install.bat
```

脚本会依次探测 `py -3` / `python` / 常见安装路径，要求候选解释器带 `tkinter`，
然后创建 `.venv` 并安装依赖（走清华镜像，约 110 MB）。

**方式二：pip 安装（可当普通包用）**

```bat
git clone https://github.com/nineone-spirits/nineone-spirits.git
cd textgrabber
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e .
```

装完后 `.venv\Scripts\textgrabber.exe` 即为启动器（`gui-scripts` 入口，不弹控制台），
也可以 `python -m screengrab`。

**方式三：不装，直接跑**

只要依赖齐全（`pip install -r requirements.txt`），克隆下来就能 `python run.py`。

### 运行

```bat
run.bat                        :: 推荐：先校验依赖再启动
.venv\Scripts\pythonw run.py   :: 无控制台
.venv\Scripts\python  run.py   :: 有控制台，能看到具体报错
```

启动成功后右下角出现蓝色 **OCR** 悬浮球。没有悬浮球 = 启动失败，
用带控制台的方式启动看报错。

首次运行会预热 OCR 模型（2–3 秒），之后热键响应基本无感。

### 装机后的两个小设置（可选）

**开机自启**：把启动器的快捷方式放进
`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup`。

**桌面图标 / 固定到任务栏**：给 `.venv\Scripts\pythonw.exe` 建快捷方式，
参数填 `<项目路径>\run.py`，起始位置填项目目录，图标选 `icon.ico`。
（Windows 快捷方式会把参数与路径写死，换目录后需要重建。）

## 使用

| 操作 | 方式 |
| --- | --- |
| 框选识别 | `Ctrl+Alt+Q`，或点悬浮球 |
| 重新识别上次区域 | `Ctrl+Alt+D` |
| 取消框选 | `Esc` / 右键 / 点击不拖动 |
| 复制 | `Ctrl+Enter` 全量复制，`Ctrl+C` 复制选中，或点「复制全部」 |
| 看原文 | 结果窗右上「整理 / 原文」切换 |
| 看改了什么 | 点「整理明细 N」展开每类改动的次数与样例 |
| 只看主体 | 默认开启；点「主体 3/8」切回全部文字 |
| 切换排版 | 原文视图下「逐行 / 合段」，只重排不重识别 |
| 退出 | 悬浮球右键 → 退出 |

典型场景：

- **抄一段视频里的字幕/标题**：框住文字区域即可，背后的页面正文会被主体过滤掉
- **从 PDF 抄表格**：框住表格，输出按制表符对齐，粘进 Excel 自动分列
- **抄报错信息**：框住控制台，`Ctrl+Enter` 复制，比手打快得多
- **对照改稿**：结果窗里直接编辑，改完再复制

## 配置

配置文件：`%APPDATA%\TextGrabber\config.json`（首次运行自动生成，改完重启生效）

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `hotkey` | `ctrl+alt+q` | 框选识别热键，须含 ctrl/alt/shift/win 之一 |
| `hotkey_retry` | `ctrl+alt+d` | 重识别上次区域 |
| `layout_mode` | `verbatim` | `verbatim` 逐行保留 / `paragraph` 智能合段 |
| `tidy_enabled` | `true` | 识别后是否自动整理 |
| `result_view` | `tidy` | 结果窗默认视图：`tidy` 整理稿 / `raw` 原文 |
| `subject_filter` | `auto` | 主体过滤：`auto` / `off` / `large` / `red` / `color:blue` |
| `min_score` | `0.5` | 低于该置信度的文本框直接丢弃 |
| `auto_invert` | `true` | 深色主题自动反色后再识别 |
| `pill_pos` | `null` | 悬浮球位置，拖动后自动记录 |
| `last_region` | `null` | 上次框选区域，供重识别使用 |

热键被其它软件占用时启动会弹提示，改完配置重启即可。

## 项目结构

```
screengrab/
  main.py            入口：DPI 感知 → 单实例 → 启动
  app.py             状态机与线程编排（热键 → 抓屏 → 框选 → OCR → 主体过滤 → 结果）
  winutil.py         Win32 适配：DPI、窗口摆放、显示器枚举、单实例、剪贴板
  hotkey.py          全局热键（RegisterHotKey + 独立消息循环）
  capture.py         桌面抓图（虚拟屏坐标换算）
  overlay.py         框选遮罩（每屏一窗、压暗+提亮、放大镜、尺寸标签、Toast）
  ocr.py             识别服务（可插拔后端 + 反色/BGR 预处理 + 置信度过滤）
  subject.py         主体过滤（墨迹颜色采样 / 尺寸带 / 色系收敛 / 规则解析）
  structure.py       结构判定（列候选 / 逐行签名 / 区块切分 / 单元还原 / 字号分层）
  layout.py          版面还原（按区块分派：网格 / 分栏 / 正文）
  tidy.py            文本整理（字符归一 / 标点统一 / 空格清理 / 断行重排 / 段落重组 / 保守纠错）
  pill.py            悬浮球
  result_window.py   结果窗（整理/原文双视图 / 整理明细 / 主体切换 / 自动折行 / 复制）
  config.py          配置读写
run.py               启动入口（等价于 python -m screengrab）
install.bat          一键创建 .venv 并装依赖
run.bat              校验依赖后启动
docs/技术方案.html    技术方案与实现说明（选型依据、架构、算法、实测数据、限制）
tests/               10 套独立测试脚本（结构 / 整理 / 主体 / 版面 / GUI / 端到端）
```

## 开发与测试

```bat
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python tests\test_structure.py   :: 结构判定 36 项（图标网格/表格/分栏/多字号/徽标）
.venv\Scripts\python tests\test_tidy.py        :: 文本整理 38 项（合段/标点/空格/纠错/保真/性能）
.venv\Scripts\python tests\test_subject.py     :: 主体过滤 47 项（色系/尺寸带/像素采样/端到端）
.venv\Scripts\python tests\test_pipeline.py    :: 版面单测 + 合成界面端到端
.venv\Scripts\python tests\test_grid_e2e.py    :: 真实桌面截图端到端（会抓当前屏幕）
.venv\Scripts\python tests\test_tidy_e2e.py    :: 合成窄栏截图 → OCR → 整理
.venv\Scripts\python tests\test_result_wrap.py :: 结果窗换行与窄窗自适应
.venv\Scripts\python tests\test_result_tidy.py :: 双视图切换、明细面板、多宽度不溢出
.venv\Scripts\python tests\test_gui_smoke.py   :: GUI 冒烟（剪贴板 / 遮罩 / 组件）
.venv\Scripts\python tests\test_app_e2e.py     :: 整机联调（热键 → 抓屏 → OCR → 复制）
```

`test_pipeline.py` 会打印浅色/深色/小字三种界面的识别结果，可直接肉眼比对准确率；
`test_tidy.py` 会打印「整理前 / 整理后」对照文本。

贡献流程、代码地图与风格约定见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 常见问题

**双击启动没反应 / 右下角没有悬浮球？**
说明启动失败。先用带控制台的方式跑一次：`.venv\Scripts\python run.py`，报错会直接打印出来。
最常见的是依赖没装全（`No module named rapidocr`）或解释器没有 `tkinter`。

**热键按了没反应？**
热键可能被其它软件（截图工具、录屏、IDE）占用，启动时右下角会弹提示。
改 `config.json` 的 `hotkey` 后重启，或直接点悬浮球。

**截出来是黑块 / 只有黑屏？**
硬件加速或 DRM 保护的窗口（部分播放器、受保护流媒体、独占全屏游戏）抓不到，
把窗口切成非独占模式再试。彻底解决需要换 Windows Graphics Capture，见路线图。

**为什么识别结果是竖排、旋转的文字时很差？**
PP-OCR 对旋转超过 15°、竖排中文、艺术字的识别率会明显下降，这是模型能力边界，不是拼版问题。

**能离线用吗？能商用吗？**
完全离线，模型随依赖包分发。许可为 MIT，可商用、可闭源再分发，保留版权声明即可。

## 已知限制

- **仅 Windows**：`RegisterHotKey` / `SetWindowPos` / GDI 抓屏都是 Win32 专有。
- **抓不到的画面**：硬件加速或 DRM 保护的窗口会得到黑块。
- **不擅长**：手写体、艺术字、竖排中文、旋转 >15°、字号 <8px、极低对比度的文字。
- **格式只还原到文本层**：换行 / 空行 / 缩进 / 制表符对齐；不还原字体、字重、颜色，表格不还原合并单元格。
- **列位依赖检测框**：OCR 若把整行多个单元格连成一个框，只能按位置比例 + 就近空格切开。
- **主体过滤只按字号与颜色**：不读内容，整屏同字号彩色海报不会触发过滤；深色主题的白字属灰阶，只靠字号区分。
- 结果窗是置顶窗口，全屏独占应用下会被遮挡。

完整限制与风险说明见 [docs/技术方案.html](docs/技术方案.html) 第 13 节。

## 路线图

四项待办的评估如下（「约束冲突」指的是与项目已声明的取舍相矛盾，需要先做设计决策，不能直接开工）：

| 待办 | 价值 | 成本 | 约束 / 风险 | 状态 |
| --- | --- | --- | --- | --- |
| 抓屏换 Windows Graphics Capture | 高：解决硬件加速窗口黑屏 | 大：需要 `Windows.Graphics.Capture` 互操作层 + D3D11 帧读取，约 400–600 行，且要有受保护窗口才能验证 | 现有 GDI 抓屏是所有坐标换算的基础，替换后需重跑全部抓屏相关测试 | 待办 |
| 托盘图标 + 设置界面 | 高：不再手改 JSON | 中：`Shell_NotifyIcon`（ctypes）+ Tk 设置窗，约 300–400 行 | 托盘图标会影响常驻进程生命周期，需保证「关窗口≠退出」的行为不回归 | 待办 |
| 免安装单文件 exe | 中：非技术用户双击即用 | 中：PyInstaller spec + 打包脚本，产物约 120–180 MB | 不能进仓库，只能挂 Release 附件；模型文件需 `collect-data` 显式带上 | 待办 |
| 表格结构识别（PP-Structure） | 中：输出 Markdown/HTML 表格 | 大：新增模型（数百 MB）与后处理 | **约束冲突**：与「模型随包分发、四个轻依赖、纯离线」的定位矛盾 | 需决策 |
| 语义级整理（本地小模型） | 低：现规则已覆盖常见场景 | 大：GB 级依赖 + 推理耗时 | **约束冲突**：与「不做改写、不改实质内容」的承诺矛盾 | 需决策 |

取舍原则：优先做**不改变现有契约**的增量（托盘、exe 打包），再做需要重写底层的能力（WGC），
最后才考虑引入大模型的方向——后者需要先想清楚是否值得牺牲「离线 + 轻量」这个卖点。

## 贡献

欢迎 Issue 与 PR。开始之前请读 [CONTRIBUTING.md](CONTRIBUTING.md)，
参与即表示同意 [行为准则](CODE_OF_CONDUCT.md)。变更记录见 [CHANGELOG.md](CHANGELOG.md)。

## 许可证

[MIT](LICENSE) © 2026 Jiuyi Jiu · NineOne Spirits (九一的酒)

## 致谢

- [RapidOCR](https://github.com/RapidAI/RapidOCR) 与 PP-OCR 系列模型：离线中英混排识别的底座
- [ONNX Runtime](https://github.com/microsoft/onnxruntime)：CPU 推理
- [Pillow](https://github.com/python-pillow/Pillow)、[NumPy](https://numpy.org/)：图像处理
- Tkinter：零依赖的界面方案
