"""Own the API, one SpawnWorker and a dedicated local Redis; Ctrl+C stops owned children."""

import argparse
import fcntl
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.config import get_settings  # noqa: E402
from backend.app.migrate import migrate  # noqa: E402


def port_free(port):
    with socket.socket() as listener:
        try:
            listener.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def main():
    parser = argparse.ArgumentParser(description="启动 ClassEcho 本地应用；Ctrl+C 停止")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--ready-file", type=Path)
    args = parser.parse_args()
    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    api_port = settings.api_port
    ready = args.ready_file.resolve() if args.ready_file else None
    if ready and not ready.is_relative_to(settings.data_dir):
        raise SystemExit("启动握手文件必须位于当前数据目录。")
    lock = (settings.data_dir / ".run.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit("已有 ClassEcho 启动器正在运行，请先在原终端按 Ctrl+C 停止。") from None
    for tool in ("ffmpeg", "ffprobe", "redis-server"):
        if not shutil.which(tool):
            raise SystemExit(f"缺少 {tool}，请先运行 bash scripts/setup.sh。")
    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        raise SystemExit("尚未构建前端，请先运行 npm --prefix frontend run build。")
    if not port_free(api_port):
        raise SystemExit(f"本机 {api_port} 端口被占用，请先停止之前的 ClassEcho 服务。")
    redis = urlsplit(settings.redis_url)
    if redis.hostname not in ("127.0.0.1", "localhost") or redis.scheme != "redis":
        raise SystemExit("启动器仅支持本机 Redis；其他部署请手动启动各进程。")
    redis_port = redis.port or 6379
    if redis.username or redis.password:
        raise SystemExit("使用带认证的 Redis 时请手动启动各进程，避免将认证信息传入进程参数。")
    if not port_free(redis_port):
        raise SystemExit(f"本机 {redis_port} 端口被占用；启动器不会接管已有的 Redis。")
    migrate()
    log_dir = settings.data_dir / "logs"
    log_dir.mkdir(exist_ok=True)
    redis_dir = settings.data_dir / "redis"
    redis_dir.mkdir(exist_ok=True)
    children, logs = [], []

    def start(name, command):
        log = (log_dir / f"{name}.log").open("ab")
        logs.append(log)
        child = subprocess.Popen(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        children.append(child)
        return child

    def stop(signum=None, frame=None):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    try:
        start(
            "redis",
            [
                "redis-server",
                "--bind",
                "127.0.0.1",
                "--port",
                str(redis_port),
                "--protected-mode",
                "yes",
                "--dir",
                str(redis_dir),
                "--appendonly",
                "yes",
                "--daemonize",
                "no",
            ],
        )
        from backend.app.jobs import connection

        for _ in range(50):
            try:
                if connection().ping():
                    break
            except Exception:
                time.sleep(0.1)
        else:
            raise RuntimeError("Redis 未能启动，请查看 data/logs/redis.log")
        start("worker", [sys.executable, "-m", "backend.app.worker"])
        start(
            "api",
            [
                sys.executable,
                "-m",
                "uvicorn",
                "backend.app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(api_port),
            ],
        )
        for _ in range(100):
            if any(child.poll() is not None for child in children):
                raise RuntimeError("服务启动失败，请查看 data/logs/")
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{api_port}/api/health", timeout=1
                ) as response:
                    content = json.load(response)
                    if response.status == 200 and content.get("instance_id") == os.getenv(
                        "CLASSECHO_INSTANCE_ID"
                    ):
                        break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("本机 API 启动超时，请查看 data/logs/api.log")
        if ready:
            ready.parent.mkdir(parents=True, exist_ok=True)
            temporary = ready.with_suffix(".tmp")
            temporary.write_text(
                json.dumps(
                    {
                        "url": f"http://127.0.0.1:{api_port}",
                        "instance_id": os.getenv("CLASSECHO_INSTANCE_ID"),
                        "pid": os.getpid(),
                    }
                )
            )
            temporary.chmod(0o600)
            temporary.replace(ready)
        print(f"ClassEcho 已启动：http://127.0.0.1:{api_port}", flush=True)
        print(
            "按 Ctrl+C 停止本次启动的 API、worker 和 Redis。日志保存在本机 data/logs/。", flush=True
        )
        if not args.no_browser:
            webbrowser.open(f"http://127.0.0.1:{api_port}")
        while all(child.poll() is None for child in children):
            time.sleep(0.5)
        raise RuntimeError("有服务意外退出，请查看 data/logs/，修复后重新启动。")
    except KeyboardInterrupt:
        print("\n正在停止 ClassEcho…", flush=True)
    finally:
        # Stop the API and worker before Redis so RQ can persist its final state.
        for child in reversed(children):
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    os.killpg(child.pid, signal.SIGKILL)
                    child.wait()
        from sqlalchemy import select

        from backend.app.db import Job, now, session

        with session() as db:
            for job in db.scalars(select(Job).where(Job.state == "running")):
                job.state, job.updated_at = "failed", now()
                job.error = "本机服务停止，任务已中断；可在重启后重试，云端用量未知时先核对账单"
            db.commit()
        for log in logs:
            log.close()
        if ready:
            ready.unlink(missing_ok=True)
        lock.close()


if __name__ == "__main__":
    main()
