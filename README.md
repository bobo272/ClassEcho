# ClassEcho

中文课堂 AI 笔记工具：把课程录音整理成能回听核对、能编辑导出的课程笔记。

> 当前为本地开发预览版。课程工作区、转录修订、后台任务、引用回听和导出已实现；笔记流程先用本地逐段摘录验证。真实录音质量评测和云模型联调尚未完成。

## 使用流程

1. 导入课程音视频，在 Apple Silicon Mac 上完成本地转录。
2. 核对转录文字与专业术语，先体验本地逐段摘录；配置云模型后可选择云端整理。
3. 为笔记关联原始转录片段与时间戳，便于回听核对。
4. 编辑笔记，导出 Markdown、SRT 与 JSON。

原始音视频默认留在本机；云端笔记整理需要发送相关转录文本，因此整个流程并非完全离线。

## 技术栈

- 前端：React、TypeScript、Vite
- 后端：Python、FastAPI、Pydantic
- 本地转录与音视频处理：MLX Whisper、FFmpeg
- 数据与后台任务：SQLite、SQLAlchemy、RQ、Redis
- 云端笔记：Qwen-Plus 文本模型

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

- 创建课程，导入 MP3、M4A、WAV、MP4；限制 500MB / 90 分钟并校验音轨。
- 本地转录、片段时间戳、原始识别文本与独立修订版本。
- 本地逐段摘录、来源引用回听、独立用户笔记与版本冲突检查。
- 持久后台任务、状态轮询、规范化检查点、失败重试与排队取消。
- 疑问时间标记，Markdown、SRT 与 JSON 备份导出。
- 可选 Qwen 适配、请求费用预留及预算检查；真实服务尚未联调。

## 开发与验证

```bash
uv run --locked python -m pytest backend/tests -q
uv run --locked ruff check backend scripts
uv run --locked ruff format --check backend scripts
npm --prefix frontend test
npm --prefix frontend run build
```

请在仓库根目录使用 `python -m pytest` 启动测试，确保 `backend` 包能够被导入。

当前本机后端 27 项测试、前端 3 项组件测试与生产构建已通过。CI 配置见 `.github/workflows/ci.yml`，远端是否通过以 GitHub Actions 实际结果为准。测试使用临时音频和模拟模型响应，不代表真实识别质量通过。

开发前后端时，可分别运行 `uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8765` 与 `npm --prefix frontend run dev`；转录和笔记任务还需要本机 Redis 和 `uv run python -m backend.app.worker`。统一启动器与手动 API 不应同时占用 8765 端口。

目录分工：`backend/app/` 为业务与 API，`backend/migrations/` 为数据库迁移，`backend/tests/` 为后端测试，`frontend/` 为工作区，`scripts/` 为安装、启动和模型准备，`samples/` 为项目自写示例。

## 数据与云模型

音视频、数据库、转录、日志、模型和导出文件保存在本机 `data/`，该目录被 Git 忽略。删除录音会移除相关媒体、转录、笔记与标记；历史费用记录保留，以免删除材料导致预算错误释放。

本地摘录无需密钥或付费调用。若后续启用 Qwen，将 `.env.example` 复制为本机 `.env`，配置密钥、地域对应的端点、模型、单价和预算后重启。密钥不得提交到 Git，也不要发到 Issue 或日志里。默认预算为 0，未配置密钥或单价时不会发起付费请求。请求超时且费用未知时保留预留费用，需先核对供应商账单。

## 待验证事项

- 真实录音的术语准确率、时间戳偏差、耗时和峰值内存。
- small 与 turbo 在相同材料上的对照，以及 45—60 分钟长录音测试。
- 真实 Qwen 输出质量、费用及故障恢复；当前先以本地摘录跑通流程。
- Safari、另一台 Apple Silicon Mac 的安装与使用，以及真实试用反馈。

这些事项完成前，当前版本不作为正式公开试用版验收。小步开发与 GitHub 同步流程见 [CONTRIBUTING.md](CONTRIBUTING.md)。项目原创代码采用 MIT 许可；模型、FFmpeg 等外部组件的许可分别适用。
