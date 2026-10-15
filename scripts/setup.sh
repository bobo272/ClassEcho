#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ "$(uname -m)" != "arm64" || "$(uname -s)" != "Darwin" ]]; then
  echo "当前版本仅支持 Apple Silicon macOS。"
  exit 1
fi
for tool in uv ffmpeg ffprobe redis-server node npm; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "缺少 $tool。请先安装 Homebrew 及 uv、ffmpeg、redis、Node.js（建议 24 LTS）。"
    exit 1
  fi
done
uv sync --locked
npm --prefix frontend ci
npm --prefix frontend run build
echo "安装完成。运行 bash scripts/start.sh，或先运行 uv run python scripts/download_model.py small 下载模型。"
