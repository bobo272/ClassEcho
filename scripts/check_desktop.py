"""macOS artifact smoke test: relocate the app, use only demo data, stop owned services."""

import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
import urllib.request
import uuid
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("app", type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="classecho-package-", dir="/private/tmp") as temporary:
        root = Path(temporary)
        application = root / "ClassEcho.app"
        subprocess.run(["cp", "-cR", str(args.app.resolve()), str(application)], check=True)
        resources = application / "Contents/Resources"
        python = resources / "python/bin/python3.11"
        code = resources / "app"
        environment = {
            name: os.environ[name] for name in ("HOME", "TMPDIR", "LANG") if name in os.environ
        }
        environment.update(
            {
                "PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                "PYTHONPATH": str(code),
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONNOUSERSITE": "1",
            }
        )
        subprocess.run(
            [
                str(python),
                "-B",
                "-c",
                "import sys,sysconfig; import mlx.core,mlx_whisper,torch,scipy.linalg,opencc; assert sysconfig.get_config_var('prefix') == sys.base_prefix; print('移动后的 Python / MLX / Torch / SciPy / OpenCC 加载成功')",
            ],
            cwd=root,
            env=environment,
            check=True,
        )
        data = root / "data"
        identity = str(uuid.uuid4())
        log = (root / "runtime.log").open("wb")
        process = subprocess.Popen(
            [
                str(python),
                "-B",
                str(code / "desktop/runtime.py"),
                "--data-dir",
                str(data),
                "--instance-id",
                identity,
            ],
            cwd=root,
            env=environment,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        ready = data / ".desktop-ready.json"
        address = None
        try:
            deadline = time.monotonic() + 45
            while not ready.exists():
                if process.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError("桌面服务启动失败：" + (root / "runtime.log").read_text())
                time.sleep(0.2)
            handshake = json.loads(ready.read_text())
            assert handshake["instance_id"] == identity
            address = handshake["url"]

            def request(path, method="GET", body=None):
                req = urllib.request.Request(
                    address + path,
                    method=method,
                    data=json.dumps(body).encode() if body is not None else None,
                    headers={"Origin": address, "Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as response:
                    return response.status, response.read()

            assert json.loads(request("/api/health")[1])["instance_id"] == identity
            assert b"<html" in request("/")[1]
            assert json.loads(request("/api/courses")[1]) == []
            status, content = request("/api/demo", "POST")
            assert status == 201
            lecture = json.loads(content)["lecture_id"]
            detail = json.loads(request(f"/api/lectures/{lecture}")[1])
            task = json.loads(
                request(
                    f"/api/lectures/{lecture}/notes",
                    "POST",
                    {"transcript_id": detail["active_transcript_id"], "provider": "extractive"},
                )[1]
            )
            deadline = time.monotonic() + 45
            while task["state"] not in {"succeeded", "failed", "canceled"}:
                if time.monotonic() > deadline:
                    raise RuntimeError("打包后的后台笔记任务超时")
                time.sleep(0.2)
                task = json.loads(request(f"/api/jobs/{task['id']}")[1])
            assert task["state"] == "succeeded", task.get("error")
            for format_name in ("markdown", "srt", "json"):
                assert len(request(f"/api/lectures/{lecture}/export?format={format_name}")[1]) > 20
            assert request(f"/api/lectures/{lecture}/media")[1][:4] == b"RIFF"
            print(
                "隔离 API / Redis / SpawnWorker 本地笔记 / 示例 AIFF 转码拼接 / 媒体 / 三种导出通过"
            )
        finally:
            if process.poll() is None:
                process.terminate()
            process.wait(timeout=35)
            log.close()
            assert not ready.exists(), "退出后握手文件未清理"
            if address:
                port = int(address.rsplit(":", 1)[1])
                with socket.socket() as connection:
                    assert connection.connect_ex(("127.0.0.1", port)) != 0, "退出后 API 仍监听"
        print("退出清理通过；全部临时示例数据已隔离")


if __name__ == "__main__":
    main()
