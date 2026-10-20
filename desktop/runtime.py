"""Entry point run by the macOS app using its private, relocatable Python runtime."""

import argparse
import os
import signal
import socket
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def available_ports():
    with socket.socket() as api, socket.socket() as redis:
        api.bind(("127.0.0.1", 0))
        redis.bind(("127.0.0.1", 0))
        return api.getsockname()[1], redis.getsockname()[1]


def watch_parent(parent):
    while True:
        time.sleep(1)
        if os.getppid() != parent:
            os.kill(os.getpid(), signal.SIGTERM)
            return


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--instance-id", required=True)
    args = parser.parse_args()
    data = args.data_dir.expanduser().resolve()
    data.mkdir(parents=True, exist_ok=True, mode=0o700)
    api_port, redis_port = available_ports()
    os.environ.update(
        {
            "CLASSECHO_DATA_DIR": str(data),
            "CLASSECHO_API_PORT": str(api_port),
            "CLASSECHO_REDIS_URL": f"redis://127.0.0.1:{redis_port}/0",
            "CLASSECHO_INSTANCE_ID": args.instance_id,
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HF_HUB_DISABLE_TELEMETRY": "1",
            "DO_NOT_TRACK": "1",
        }
    )
    # The app prepends its bundled tools. No package installation or shell is run here.
    tools = ROOT.parent / "tools" / "bin"
    if tools.is_dir():
        os.environ["PATH"] = f"{tools}:/usr/bin:/bin:/usr/sbin:/sbin"
    sys.path.insert(0, str(ROOT))
    parent = os.getppid()
    threading.Thread(target=watch_parent, args=(parent,), daemon=True).start()
    from scripts.run import main as run

    sys.argv = [
        str(ROOT / "scripts/run.py"),
        "--no-browser",
        "--ready-file",
        str(data / ".desktop-ready.json"),
    ]
    run()


if __name__ == "__main__":
    main()
