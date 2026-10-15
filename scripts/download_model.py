import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json

from backend.app.asr import MODELS, download_model, model_directory
from backend.app.model_download import download_ranges

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="下载固定 revision 的公开 MLX Whisper 模型；不上传录音"
    )
    parser.add_argument("model", choices=list(MODELS))
    parser.add_argument(
        "--http-chunks",
        action="store_true",
        help="大文件传输中断时使用可恢复的分段下载，并核对 LFS SHA256",
    )
    args = parser.parse_args()
    if args.http_chunks:
        spec = MODELS[args.model]
        directory = download_ranges(spec["repo"], spec["revision"], model_directory(args.model))
        (directory / ".ready").write_text(json.dumps(spec))
        print(directory)
    else:
        print(download_model(args.model))
