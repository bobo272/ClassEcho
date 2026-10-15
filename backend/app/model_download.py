"""Optional resumable HTTP ranges for networks that interrupt large Hub downloads."""

import hashlib
import json
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def download_ranges(repo: str, revision: str, directory: Path):
    def read_json(url):
        with urllib.request.urlopen(url, timeout=60) as response:
            return json.load(response)

    info = read_json(f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true")
    if info["sha"] != revision:
        raise ValueError("模型 revision 与固定版本不一致")
    directory.mkdir(parents=True, exist_ok=True)
    files = {file["rfilename"]: file for file in info["siblings"]}
    for name in ("config.json", "README.md"):
        if name not in files:
            continue
        target = directory / name
        if not target.exists():
            with urllib.request.urlopen(
                f"https://huggingface.co/{repo}/resolve/{revision}/{name}", timeout=60
            ) as response:
                data = response.read(1024 * 1024)
            if len(data) != files[name]["size"]:
                raise ValueError("模型配置下载不完整")
            target.write_bytes(data)
    weight = next((name for name in ("weights.safetensors", "weights.npz") if name in files), None)
    if not weight or "lfs" not in files[weight]:
        raise ValueError("模型未提供可核验的 LFS 权重元数据")
    size = files[weight]["lfs"]["size"]
    sha256 = files[weight]["lfs"]["sha256"]
    parts = directory / ".http-parts"
    parts.mkdir(exist_ok=True)
    block = 8 * 1024 * 1024
    count = (size + block - 1) // block

    def fetch(index):
        start = index * block
        end = min(size, start + block) - 1
        target = parts / f"{index:06d}.part"
        if target.exists() and target.stat().st_size == end - start + 1:
            return target
        for attempt in range(4):
            temporary = target.with_suffix(".tmp")
            try:
                # The byte range is also in the query to avoid proxy cache collisions.
                request = urllib.request.Request(
                    f"https://huggingface.co/{repo}/resolve/{revision}/{weight}?download=true&part={index}",
                    headers={"Range": f"bytes={start}-{end}"},
                )
                with urllib.request.urlopen(request, timeout=90) as response:
                    if (
                        response.status != 206
                        or response.headers.get("Content-Range") != f"bytes {start}-{end}/{size}"
                    ):
                        raise ValueError("下载服务器未正确响应分段范围")
                    with temporary.open("wb") as output:
                        remaining = end - start + 1
                        while remaining:
                            chunk = response.read(min(1024 * 1024, remaining))
                            if not chunk:
                                raise ValueError("模型分段下载中断")
                            output.write(chunk)
                            remaining -= len(chunk)
                temporary.replace(target)
                print(f"模型分段 {index + 1}/{count} 已完成", flush=True)
                return target
            except (OSError, ValueError):
                temporary.unlink(missing_ok=True)
                if attempt == 3:
                    raise ValueError(
                        f"模型第 {index + 1} 段下载失败；再次运行会复用已完成分段"
                    ) from None
                time.sleep(attempt + 1)

    with ThreadPoolExecutor(max_workers=4) as pool:
        completed = list(pool.map(fetch, range(count)))
    temporary = directory / (weight + ".partial")
    digest = hashlib.sha256()
    with temporary.open("wb") as output:
        for part in completed:
            with part.open("rb") as input_file:
                while chunk := input_file.read(1024 * 1024):
                    digest.update(chunk)
                    output.write(chunk)
    if temporary.stat().st_size != size or digest.hexdigest() != sha256:
        temporary.unlink(missing_ok=True)
        raise ValueError("模型哈希核验失败；未将权重标记为可用")
    temporary.replace(directory / weight)
    for part in completed:
        part.unlink()
    parts.rmdir()
    return directory
