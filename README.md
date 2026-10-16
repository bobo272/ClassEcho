# ClassEcho

中文课堂 AI 笔记工具：把课程录音整理成能回听核对、能编辑导出的课程笔记。

> 当前为本地开发预览版。课程工作区、转录修订、后台任务、引用回听和导出已实现；笔记流程先用本地逐段摘录验证。真实录音质量评测和用户自选 API 的联调尚未完成。

## 使用流程

1. 导入课程音视频，或点击右上角「录音」使用麦克风，在 Apple Silicon Mac 上完成本地转录。
2. 笔记以文档视图为主；课程列表可折叠，课堂原文和播放器按需展开，点击引用会自动打开回听。核对转录文字与专业术语；可使用本地逐段摘录，或在「设置 → AI 接口」填写自己的 API URL、模型与密钥，再选择「AI 接口整理」。
3. 为笔记关联原始转录片段与时间戳，便于回听核对。
4. 点击笔记条目的编辑图标修改正文，也可填写「我的补充」。Markdown 导出修订后的正文并标明用户修订，JSON 备份保留原始正文和修改；SRT 导出转录。

原始音视频留在本机；选择 AI 接口整理时，会将当前版本的转录文字与片段 ID 发送到用户填写的接口地址，不发送音频。

## 技术栈

- 前端：React、TypeScript、Vite
- 后端：Python、FastAPI、Pydantic
- 本地转录与音视频处理：MLX Whisper、FFmpeg
- 数据与后台任务：SQLite、SQLAlchemy、RQ、Redis
- AI 笔记：用户自选的 Chat Completions 兼容接口，支持自定义服务或中转地址

当前目标平台为 Apple Silicon macOS。本机已验证 macOS 27.0.1 / arm64；尚未在其他系统版本验收，也未承诺 Windows/Linux 的本地识别支持。

## 本地运行

需要 Apple Silicon Mac、Homebrew 和 Node.js（建议 24 LTS；本机使用 26.4.0）。Python 3.11 由 uv 管理，无需替换全局 Python。

```bash
# 安装环境管理与音频工具（已经安装的工具可跳过）
brew install uv ffmpeg redis

# 在仓库根目录执行：建立 .venv，安装前端依赖并构建页面
bash scripts/setup.sh

# 启动本机 API、一个 SpawnWorker 和项目专用 Redis
bash scripts/start.sh
```

打开 <http://127.0.0.1:8765>。在启动终端按 `Ctrl+C` 停止本次启动的服务。默认 API 端口为 8765，Redis 端口为 6387；端口被占用时，启动器会报错并拒绝接管已有进程。

`uv.lock` 与 `frontend/package-lock.json` 固定依赖。依赖安装在项目 `.venv` 和 `frontend/node_modules` 内。演示入口会使用项目自写文本和 macOS Tingting 合成语音，转录与笔记明确标记为预生成示例。

第一次真实转录会下载选定的模型。也可以提前下载：

```bash
uv run --locked python scripts/download_model.py small

# 大文件下载经常中断时，使用可恢复的分段下载并核对官方 LFS SHA256
uv run --locked python scripts/download_model.py small --http-chunks
```

模型的仓库与 revision 固定在 `backend/app/asr.py`；权重保存在本机 `data/models/`，不进入 Git。

安装依据：[uv 文档](https://docs.astral.sh/uv/)、[MLX Whisper 官方说明](https://github.com/ml-explore/mlx-examples/tree/main/whisper)。

## 当前实现

- 创建课程，导入 MP3、M4A、WAV、MP4、WebM；限制 500MB / 90 分钟并校验音轨。
- 网页麦克风录音：开始、暂停／继续、计时、结束预览、下载与保存到课程；保存失败保留录音。默认结束后自动保存、校准完整转录并整理笔记，也可取消自动整理只保留录音。支持 Chrome 常见的 WebM 和 Safari 常见的 MP4 编码路径，浏览器权限与真实设备仍需实测。
- 麦克风实时转录采用 AudioWorklet 采集单声道 PCM16，约每 10 秒交给本机 RQ/MLX Whisper small 识别；文字是临时预览，支持暂停，不调用浏览器云端语音识别。识别落后时只更新最新窗口，完整录音独立保留；需要提前准备 small 模型。
- 本地转录默认用 OpenCC 转为简体，保留模型原始识别文字、片段时间戳与独立修订版本；繁简转换不会纠正识别错词。
- 重新整理明确创建新笔记版本，任务完成后自动展示新结果；旧笔记保留，有未保存修改时先保护草稿。
- 本地逐段摘录、来源引用回听；笔记正文可逐条修订、查看原始内容和恢复原文，个人补充独立保存，保存时检查版本冲突。
- 文档工作区适配窄窗口；设置和新建课程弹窗支持键盘聚焦、Tab 限制与 Escape 关闭，关闭原文面板保留未保存修订。
- 刷新页面后恢复课程与录音选择，重新查询持久任务；浏览器仅保存课程、录音 ID，不保存课堂文本或密钥。
- 持久后台任务、状态轮询、规范化检查点、失败重试与排队取消；AI 整理支持分块进度与检查点，手动重试复用已完成块。
- 疑问时间标记，Markdown、SRT 与 JSON 备份导出。
- 可在界面保存自定义 AI 接口、模型与密钥；按主题合并口语碎片、校验来源引用，保留旧版笔记和个人补充。兼容性已通过模拟接口验证，真实服务尚未联调。

## 开发与验证

```bash
uv run --locked python -m pytest backend/tests -q
uv run --locked ruff check backend scripts
uv run --locked ruff format --check backend scripts
npm --prefix frontend test
npm --prefix frontend run build
```

请在仓库根目录使用 `python -m pytest` 启动测试，确保 `backend` 包能够被导入。

当前本机后端 72 项测试、前端 34 项前端测试与生产构建已通过。CI 配置见 `.github/workflows/ci.yml`，远端是否通过以 GitHub Actions 实际结果为准。测试使用临时音频和模拟模型响应，不代表真实识别质量通过。

开发前后端时，可分别运行 `uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8765` 与 `npm --prefix frontend run dev`；转录和笔记任务还需要本机 Redis 和 `uv run python -m backend.app.worker`。统一启动器与手动 API 不应同时占用 8765 端口。

目录分工：`backend/app/` 为业务与 API，`backend/migrations/` 为数据库迁移，`backend/tests/` 为后端测试，`frontend/` 为工作区，`scripts/` 为安装、启动和模型准备，`samples/` 为项目自写示例。

## 数据与 AI 接口

音视频、数据库、转录、日志、模型和导出文件保存在本机 `data/`，该目录被 Git 忽略。删除录音会移除相关媒体、转录、笔记与标记。

本地摘录无需密钥或 API 调用。需要 AI 整理时：

1. 打开「设置 → AI 接口」，填写服务商提供的基础 URL（包含 `/v1` 等必要路径）、模型名称与 API Key。也可填写完整的 `/chat/completions` 地址，程序会规范化后使用。
2. 点击「保存接口」，无需重启。密钥保存在 `data/notes-api.json`，文件权限为 `0600`；接口响应只返回是否已配置，浏览器不会读回已保存密钥。该文件为本机私有配置，不得公开或提交 Git。
3. 展开「转录与整理」，选择「AI 接口整理」，核对显示的目标地址后确认发送转录文字，点击「整理笔记」。保存设置本身不调用模型。

接口按 [Chat Completions 协议](https://api-docs.deepseek.com/api/create-chat-completion/)发送 `model`、`messages`、`max_tokens` 与 `stream: false`，不发送供应商专用参数。服务必须返回 `choices[0].message.content` 中的完整 JSON，模型需支持至少 8192 个输出 token；单次转录最多 60000 字符，按每块最多 8000 字符处理，边界保留至多两个片段且不超过 1000 字符的重叠上下文，最多 16 块；单个片段超过 8000 字符时提示核对分段。短转录仅请求一次，实际可用长度仍取决于模型的上下文限制。每块均校验结构与引用，成功后保存检查点；全部完成才发布笔记。同名章节归并、文字相同且类别相同的条目合并来源，汇总不增加模型调用，不宣称可自动识别所有语义重复。超时、输出异常或截断不会自动重试；再次调用由用户手动发起，并跳过检查点中已完成的块；请求成功与检查点落盘之间若进程中断，仍可能重复调用该块。费用以用户自己的服务商规则为准，界面不提供预算和费用统计。

更换接口地址时不会沿用旧地址的密钥；排队期间配置发生变化时，旧任务停止并提示重新确认。旧版 Qwen 环境配置和历史费用记录仅为兼容既有数据保留，新界面不再使用专用 Qwen 入口。

## 待验证事项

- 真实录音的术语准确率、时间戳偏差、耗时和峰值内存。
- small 与 turbo 在相同材料上的对照，以及 45—60 分钟长录音测试。
- 用户自选 API / 中转服务的真实兼容性、笔记质量及故障恢复；自动测试使用模拟接口，不代表真实模型质量通过。
- Safari、另一台 Apple Silicon Mac 的安装与使用，以及真实试用反馈。

这些事项完成前，当前版本不作为正式公开试用版验收。小步开发与 GitHub 同步流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目原创代码采用 MIT 许可；模型、FFmpeg 等外部组件的许可分别适用。

## 麦克风实时预览

在课程页右上角点击「录音」。允许浏览器麦克风权限后开始录音；勾选本地实时转录时，约每 10 秒显示一批文字，实际延迟取决于本机识别速度和队列。预览不是逐字流式识别，短片段可能切断句子，不能直接当作最终笔记来源。模型未就绪或预览失败时仍可保存完整录音；最终转录任务会按已有流程下载模型。

实时分片仅发送到本机 `/api/live-transcriptions`，worker 与完整转录共享推理锁；最多两个待处理预览，任务过期会释放限额。临时音频在推理后删除，预览缓存最多保留约一小时（下次请求时清理）。接口校验 WAV 格式、分片大小、采样率与时间范围。浏览器退出前应先保存或下载录音，当前不支持刷新恢复尚未保存的录音。

2026-10-16 对项目自写示例的 10 秒音频，通过实际 Redis/RQ worker 和 MLX Whisper small 完成一次识别，包含排队耗时约 3.05 秒，返回 1 个片段、45 字；此结果不是课堂准确率评测或长时间麦克风实测。

采音依据：[AudioWorkletNode](https://developer.mozilla.org/en-US/docs/Web/API/AudioWorkletNode)、[getUserMedia](https://developer.mozilla.org/en-US/docs/Web/API/MediaDevices/getUserMedia)。

### 录音结束后自动整理

「结束后自动整理笔记」默认开启。未配置 AI 接口时，明确选择本地摘录（非 AI）；配置接口后可选 AI 整理，必须勾选向显示地址发送转录文字的确认框，才能开始该次录音。录音开始后冻结本次目的地址的配置版本，结束时不重新读取其他地址的密钥并擅自发送。

点击「结束录音」后自动上传并进入课程工作区。后端先处理完整录音；转录成功时，在同一事务保存转录及下一笔笔记任务，随后由 worker 继续整理，不依赖网页保持打开。AI 接口配置变更、识别失败或笔记队列不可用时保留已经保存的音频和转录，按页面提示重试。上传成功而提交任务失败时，弹窗保留下载／重试入口，重试复用已保存录音。取消自动整理时则先预览，再手动保存。

2026-10-16 在临时数据库与独立 TCP Redis 中，用项目内置示例构造的 10 秒 WebM（无时长头）实测：导入、真实 MLX Whisper small 转录、RQ 自动接续本地摘录成功，共约 3.06 秒，1 份笔记及 1 个有效引用。真实外部 AI 的自动整理仍只通过模拟服务验证；真实麦克风设备、Safari 录音和长时间录音尚待人工验收。麦克风原始采集与暂停／继续、页面资源释放、权限失败、采样转换、发送确认及保存重试已覆盖自动化测试。

桌面运行入口位于 `desktop/runtime.py`：为独立数据目录选择本机端口，启动生产页面及其 API/worker/Redis，通过实例握手确认服务归属，退出时清理自己创建的进程；不接管开发服务。桌面安装包的构建与签名验收另行记录。
