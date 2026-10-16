"""Build pinned, self-contained CLI tools; artifacts and corresponding sources stay in dist/."""

import hashlib
import json
import os
import platform
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "dist/desktop-deps"
SOURCES = {
    "ffmpeg": (
        "8.1.2",
        "https://ffmpeg.org/releases/ffmpeg-8.1.2.tar.xz",
        "464beb5e7bf0c311e68b45ae2f04e9cc2af88851abb4082231742a74d97b524c",
    ),
    "redis": (
        "8.10.2",
        "https://download.redis.io/releases/redis-8.10.2.tar.gz",
        "b9ffee226b5eecdba98a679260dad764b2a4ebd90dce4ad5ac9e9f3eef9c02b3",
    ),
}
FFMPEG_FLAGS = [
    "--prefix=/",
    "--disable-autodetect",
    "--disable-gpl",
    "--disable-nonfree",
    "--disable-everything",
    "--disable-shared",
    "--enable-static",
    "--disable-debug",
    "--disable-doc",
    "--disable-network",
    "--enable-ffmpeg",
    "--enable-ffprobe",
    "--enable-protocol=file,pipe",
    "--enable-demuxer=mp3,mov,wav,matroska,ogg,flac,aac,aiff,concat",
    "--enable-decoder=aac,aac_fixed,aac_latm,alac,flac,mp3,mp3float,mp3adu,mp3adufloat,mp3on4,mp3on4float,opus,vorbis,ac3,eac3,pcm_s16le,pcm_s16be,pcm_s24le,pcm_s24be,pcm_s32le,pcm_u8,pcm_f32le,pcm_f64le,pcm_alaw,pcm_mulaw",
    "--enable-parser=aac,aac_latm,mpegaudio,opus,vorbis,flac,ac3",
    "--enable-encoder=pcm_s16le",
    "--enable-muxer=wav",
    "--enable-filter=aresample,aformat,anull,atrim,asetpts,abuffer,abuffersink",
    "--extra-cflags=-mmacosx-version-min=14.0",
    "--extra-ldflags=-mmacosx-version-min=14.0",
]
REDIS_FLAGS = [
    "MALLOC=libc",
    "BUILD_TLS=no",
    "BUILD_COMPRESSION=no",
    "DEBUG=",
    "OPTIMIZATION=-O2",
    "CFLAGS=-mmacosx-version-min=14.0",
    "LDFLAGS=-mmacosx-version-min=14.0",
]


def source(name):
    version, url, digest = SOURCES[name]
    archives = BUILD / "sources"
    archives.mkdir(parents=True, exist_ok=True)
    archive = archives / url.rsplit("/", 1)[1]
    if not archive.exists():
        temporary = archive.with_suffix(".part")
        with urllib.request.urlopen(url, timeout=60) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        temporary.replace(archive)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != digest:
        raise RuntimeError(
            f"{name} 源码校验失败；请删除 dist/desktop-deps/sources 内对应下载后重试"
        )
    directory = BUILD / "src" / f"{name}-{version}"
    if not directory.exists():
        with tarfile.open(archive) as content:
            content.extractall(BUILD / "src", filter="data")
    return directory


def run(command, cwd, name):
    log = BUILD / f"{name}.log"
    with log.open("ab") as output:
        result = subprocess.run(command, cwd=cwd, stdout=output, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(f"编译失败，请查看 {log.relative_to(ROOT)}")


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("桌面工具构建仅支持 Apple Silicon macOS")
    tools = BUILD / "tools/bin"
    tools.mkdir(parents=True, exist_ok=True)
    stamp = BUILD / "tools/build.json"
    spec = {"sources": SOURCES, "ffmpeg_flags": FFMPEG_FLAGS, "redis_flags": REDIS_FLAGS}
    expected = json.loads(json.dumps(spec))
    if (
        stamp.exists()
        and json.loads(stamp.read_text()) == expected
        and all((tools / name).is_file() for name in ("ffmpeg", "ffprobe", "redis-server"))
    ):
        print("内置工具已构建且版本一致", flush=True)
        return
    ffmpeg, redis = source("ffmpeg"), source("redis")
    threads = str(min(os.cpu_count() or 4, 12))
    print("正在构建独立 FFmpeg / ffprobe…", flush=True)
    run(["./configure", *FFMPEG_FLAGS], ffmpeg, "ffmpeg")
    run(["make", "-j", threads], ffmpeg, "ffmpeg")
    for name in ("ffmpeg", "ffprobe"):
        shutil.copy2(ffmpeg / name, tools / name)
    print("正在构建独立 Redis core…", flush=True)
    run(["make", "-C", "src", "-j", threads, "redis-server", *REDIS_FLAGS], redis, "redis")
    shutil.copy2(redis / "src/redis-server", tools / "redis-server")
    for path in tools.iterdir():
        dependencies = subprocess.check_output(["otool", "-L", str(path)], text=True).splitlines()[
            1:
        ]
        if any(
            not line.strip().startswith(("/usr/lib/", "/System/Library/")) for line in dependencies
        ):
            raise RuntimeError(f"{path.name} 仍依赖非系统动态库，拒绝打包")
    stamp.write_text(json.dumps(spec, indent=2))
    print("独立工具构建完成；仅依赖系统动态库", flush=True)


if __name__ == "__main__":
    main()
