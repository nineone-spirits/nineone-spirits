# 贡献指南

感谢你愿意改进 NineOne Spirits 屏幕取字（TextGrabber）。这份文档说明怎么把环境跑起来、改完怎么验证、以及提 PR 时会被关注什么。

> 参与本项目即表示你同意遵守 [行为准则](CODE_OF_CONDUCT.md)。

## 目录

- [环境要求](#环境要求)
- [本地开发](#本地开发)
- [跑测试](#跑测试)
- [代码地图](#代码地图)
- [代码风格](#代码风格)
- [提交规范](#提交规范)
- [提交 PR](#提交-pr)
- [常见改动场景](#常见改动场景)
- [报告问题](#报告问题)

## 环境要求

| 项目 | 要求 |
| --- | --- |
| 操作系统 | Windows 10 / 11（依赖 `RegisterHotKey` / GDI 抓屏，暂不支持 macOS / Linux） |
| Python | 3.10 及以上，**必须带 tkinter**（官方安装包默认自带；部分精简发行版会缺失） |
| 磁盘 | 约 300 MB（其中依赖约 110 MB，venv 约 290 MB） |
| 硬件 | 无 GPU 要求，CPU 推理，单张截图约 0.4 s |

验证解释器是否可用：

```bat
python -c "import tkinter, venv; print('ok')"
```

不打印 `ok` 说明 tkinter 缺失，请换用 python.org 的官方安装包。

## 本地开发

```bat
git clone https://github.com/nineone-spirits/nineone-spirits.git
cd textgrabber

:: 方式 A：一键脚本（创建 .venv 并装依赖，走清华镜像）
install.bat

:: 方式 B：手动
py -3 -m venv .venv
.venv\Scripts\python -m pip install -e ".[paddle]"   :: 加 paddle 之前先看清 200+ MB
```

启动：

```bat
run.bat                       :: 推荐，先校验依赖再启动
.venv\Scripts\pythonw run.py  :: 无控制台
.venv\Scripts\python  run.py  :: 有控制台，能看到报错
```

改代码后**不需要重新安装**：`pip install -e .` 是链接式安装，改完直接重启进程即可。

## 跑测试

测试是**独立脚本**而不是 pytest 用例——每套自带断言和人类可读的输出，直接跑就行：

```bat
.venv\Scripts\python tests\test_structure.py    :: 结构判定 36 项，纯几何，毫秒级
.venv\Scripts\python tests\test_tidy.py         :: 文本整理 38 项
.venv\Scripts\python tests\test_subject.py      :: 主体过滤 47 项（含一次真 OCR）
.venv\Scripts\python tests\test_pipeline.py     :: 版面单测 + 合成界面端到端
.venv\Scripts\python tests\test_result_wrap.py  :: 结果窗换行与窄窗自适应（需要桌面）
.venv\Scripts\python tests\test_result_tidy.py  :: 双视图 / 明细面板（需要桌面）
.venv\Scripts\python tests\test_gui_smoke.py    :: GUI 冒烟（剪贴板 / 遮罩 / 组件，需要桌面）
.venv\Scripts\python tests\test_app_e2e.py      :: 整机联调：热键 → 抓屏 → OCR → 复制（需要桌面）
.venv\Scripts\python tests\test_grid_e2e.py     :: 真实桌面截图端到端（会抓你当前屏幕）
.venv\Scripts\python tests\test_tidy_e2e.py     :: 合成窄栏截图 → OCR → 整理
```

一次跑完：

```bat
for %f in (tests\test_*.py) do @.venv\Scripts\python %f || echo FAILED: %f
```

约定：**改动哪个模块，至少跑对应的那套测试**；改 `layout.py` / `structure.py` / `subject.py`
这类公共几何逻辑时请全跑，它们是所有输出的上游。

> `test_grid_e2e.py` 会抓取你当前桌面，请在非敏感内容的环境下运行。

## 代码地图

| 文件 | 职责 | 改动风险 |
| --- | --- | --- |
| `screengrab/winutil.py` | Win32 适配：DPI 感知、窗口摆放、显示器枚举、单实例、剪贴板 | 高（涉及全部坐标） |
| `screengrab/hotkey.py` | 全局热键与独立消息循环 | 低 |
| `screengrab/capture.py` | 整屏抓图与虚拟屏坐标换算 | 高 |
| `screengrab/overlay.py` | 框选遮罩、放大镜、尺寸提示 | 中 |
| `screengrab/ocr.py` | 可插拔后端 + 降级链 + 预处理 + 置信度过滤 | 中 |
| `screengrab/subject.py` | 主体过滤：墨迹颜色采样、尺寸带、色系收敛 | 中（判据阈值） |
| `screengrab/structure.py` | 结构判定：列候选 / 逐行签名 / 区块 / 单元 / 字号分层 | 高 |
| `screengrab/layout.py` | 版面还原：行聚类、行内拼接、段落切分 | 高 |
| `screengrab/tidy.py` | 文本整理六步流水线与保真校验 | 中 |
| `screengrab/pill.py` | 悬浮球与右键菜单 | 低 |
| `screengrab/result_window.py` | 结果窗（双视图 / 明细 / 主体切换 / 窄窗重排） | 中 |
| `screengrab/app.py` | 状态机、线程编排、队列回调 | 中 |
| `screengrab/config.py` | 配置读写与默认值 | 低（改默认值要同步 README） |

**架构约束**（改代码时请守住）：

1. `structure.py` / `layout.py` / `subject.py` / `tidy.py` **必须是纯函数**——不碰 IO、不碰 UI、不依赖 Tk。
   这是它们能被毫秒级单测覆盖的前提。
2. Tk 不是线程安全的。所有 UI 变更只能通过 `app.py` 里的 `queue` 回到主线程。
3. 新增配置项：加进 `config.py` 的 `DEFAULTS`，同步 README 的配置表；读旧配置要能平滑兼容（`load_config` 已做过滤）。
4. 识别失败/整理失败都要**降级而不是崩**（现有实现：整理异常 → 直接给原文）。

## 代码风格

- **注释和文档字符串用中文**，说明「为什么这么做」，而不是复述代码在做什么。
  这个项目里很多阈值（`MAX_LINE_HEIGHT_RATIO = 2.2`、`CHROMA_MIN = 30`）都是实测调出来的，
  改动时请把新的实测数据写进注释。
- 面向用户的字符串（提示、菜单、按钮）用中文；日志与异常信息可中可英，保持与周围一致。
- 类型提示：公开函数建议标注参数与返回值；内部小函数不强制。
- 行宽 100 字符左右；缩进 4 空格；不要引入 formatter 配置（避免全量重排的历史噪音）。
- 不新增重量级依赖。当前运行时依赖只有 4 个（rapidocr / onnxruntime / pillow / numpy），
  加依赖请在 PR 里说明体积与必要性。

## 提交规范

采用 [Conventional Commits](https://www.conventionalcommits.org/zh-hans/)：`<类型>: <简短描述>`

```text
feat: 主体过滤支持指定色系（color:blue）
fix: 大标题与背景小字被并成一行
docs: 补充 macOS 不受支持的说明
refactor: 行聚类抽出 size_compatible 判定
test: 补竖向堆叠美术字的行聚合用例
chore: 升级 rapidocr 到 3.1
```

- 描述用中文，动词开头，不超过 50 字；正文写「为什么」和「怎么验证的」。
- 一个提交只做一件事；格式化、重命名请单独提交。
- 破坏性变更在正文加 `BREAKING CHANGE:` 段落，并同步 `CHANGELOG.md`。

## 提交 PR

1. Fork 仓库，从 `main` 拉分支：`feat/subject-color-filter`、`fix/line-merge`。
2. 改完跑对应测试，并在 PR 描述里贴出关键输出（哪个测试、多少项通过）。
3. 涉及界面的改动请附截图或录屏。
4. 同步文档：行为变了改 `README.md`，接口/算法变了改 `docs/技术方案.html`，用户可见的变更记入 `CHANGELOG.md` 的「未发布」。
5. 提交 PR 后 CI 会跑纯逻辑测试（无桌面环境的那几套）；需要桌面的测试请在本地跑完并说明结果。

PR 自查清单（模板里也有）：

- [ ] 测试通过，且新增行为有对应用例
- [ ] 新增/修改的阈值写了实测依据
- [ ] 没把本机路径、私有数据、`.workbuddy/`、`.venv/` 提交进来
- [ ] README / CHANGELOG 已同步
- [ ] 面向用户的文案是中文且无错别字

## 常见改动场景

**新增一个配置项**

1. `config.py` 的 `DEFAULTS` 加键（给注释说明取值）；
2. 使用处 `self.cfg.get("键", 默认值)`（用 `get` 以便旧配置兼容）；
3. README 配置表加一行；CHANGELOG「未发布 → 新增」。

**新增一个 OCR 后端**

实现 `ocr.OcrEngine` 子类（`name` + `run(image_ndarray) -> [(四点框, 文本, 置信度)]`），
加进 `OcrService._build_engine()` 的降级链即可；上层完全不用改。

**调整主体过滤/结构判定阈值**

先写一个能复现的场景（合成坐标或合成图，见 `tests/test_subject.py` 里的 `make_poster`），
再改阈值，最后把「改前/改后」的实测数字写进注释和 PR 描述。

## 报告问题

请用 Issue 模板，附上：系统版本、Python 版本、复现步骤、期望结果、实际结果。
涉及识别错误时，**贴一张能复现的截图**（可打码）比文字描述有效得多。
