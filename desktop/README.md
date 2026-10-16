# macOS 桌面预览版

原生 AppKit / WKWebView 窗口复用现有文档工作区，启动随包携带的 Python、API、RQ worker 和 Redis。服务只监听本机随机端口，退出时只清理自己启动的进程。录音权限、导入和导出使用系统对话框；未保存内容在退出前提示。

## 构建

在 Apple Silicon Mac 上准备 Xcode 命令行工具、uv、Node.js 与已安装的前端依赖。在仓库根目录执行：

```bash
uv run --locked python scripts/build_desktop.py
# 生成镜像前，同时执行搬移位置、原生库、本地服务与示例导出检查
uv run --locked python scripts/build_desktop.py --check
```

DMG、SHA256 与构建清单位于 `dist/macos/`，均被 Git 忽略。原生应用在非同步临时目录完成构建和签名后直接装入镜像，避免文档目录的文件同步服务写入 Finder 属性破坏签名；不输出松散的 `.app`。构建脚本创建独立的生产依赖环境；从官方地址获取固定版本、核对 SHA256 后编译 FFmpeg 与 Redis core。不会使用本机 Homebrew 的媒体或 Redis 二进制。首次构建需要网络、Xcode 与充足磁盘空间，依赖和源码缓存放在 `dist/desktop-deps/`。

应用仅复制运行代码、生产前端、自写示例与生产依赖，不复制仓库 `data/`、模型、`.env` 或测试材料。构建时修复运行时库的安装标识与 sysconfig 前缀，去掉轮子的外部编译器搜索目录，并审计原生链接、外部符号链接和最低系统版本，之后重新进行 ad-hoc 签名。

Redis 默认构建标识包含机器名，工具构建使用固定 `SOURCE_DATE_EPOCH` 并清除调试／本地符号。打包时逐文件扫描构建机用户目录与机器名，命中即停止；跨读取块边界的扫描已有回归测试。

当前锁定 MLX 库要求 macOS 26.2，安装包仅支持 arm64；构建清单会记录实际最低版本，不能仅凭 Swift 启动器的目标版本声明兼容旧系统。这里只在 macOS 27.0.1 / M4 Pro 验证，其他设备和真实麦克风长时间录制需单独验收。

## 数据与运行

默认数据目录是 `~/Library/Application Support/ClassEcho/data`；不会自动迁移开发版仓库内的数据。模型需要在桌面版设置中单独下载。测试时可通过 `CLASSECHO_DESKTOP_DATA_DIR` 指定隔离目录，该环境变量不应指向已有开发数据。

日志位于数据目录的 `logs/`，应用菜单提供入口。安装不需要 Node、Homebrew、uv 或系统 Python。应用不自更新，也不提供 Intel、Windows 或 Linux 安装包。

## 签名与第三方组件

目前只使用 ad-hoc 本地签名，不是 Developer ID 签名，也未提交 Apple 公证。DMG 是本地开发预览产物，不能当作已完成跨设备分发验收的正式发布版。

ClassEcho 原创代码继续采用 MIT。Python 依赖保留各自的 dist-info 许可、NOTICE 与元数据，应用内附依赖版本清单。FFmpeg 未启用 GPL/nonfree，按 LGPLv2.1+ 保留许可、精确对应源码与构建参数；Redis 8 core 选择 AGPLv3 许可，原始源码与构建脚本随包提供，可从应用菜单查看。工具作为独立进程运行，没有阻止用户替换工具的技术限制。

上游说明：[FFmpeg 许可](https://ffmpeg.org/legal.html)、[Redis 许可](https://redis.io/legal/licenses/)、[uv Python 运行时](https://docs.astral.sh/uv/concepts/python-versions/)。
