"""Build an allowlisted, relocatable Apple Silicon .app (no user data or credentials)."""

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "dist/macos"
VERSION = "0.1.0-preview.1"
MACH_MAGICS = {
    b"\xcf\xfa\xed\xfe",
    b"\xce\xfa\xed\xfe",
    b"\xfe\xed\xfa\xcf",
    b"\xca\xfe\xba\xbe",
    b"\xbe\xba\xfe\xca",
}


def run(command, **kwargs):
    try:
        subprocess.run([str(part) for part in command], check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        if error.stderr:
            print(
                error.stderr.decode() if isinstance(error.stderr, bytes) else error.stderr,
                file=sys.stderr,
            )
        raise


def copy_application(destination):
    """Only explicit runtime sources and built public assets may enter the bundle."""
    for folder in ("backend/app", "backend/migrations"):
        for source in (ROOT / folder).rglob("*.py"):
            target = destination / source.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
    for name in (
        "backend/__init__.py",
        "backend/alembic.ini",
        "scripts/run.py",
        "desktop/runtime.py",
        "samples/demo.json",
        "LICENSE",
    ):
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    shutil.copytree(
        ROOT / "frontend/dist",
        destination / "frontend/dist",
        ignore=shutil.ignore_patterns("*.map"),
    )


def native_files(root):
    for path in root.rglob("*"):
        if not path.is_file() or path.is_symlink():
            continue
        with path.open("rb") as source:
            if source.read(4) in MACH_MAGICS:
                yield path


def relocate_library_ids(root):
    # Some upstream wheels carry build-machine install IDs even when their consumers
    # already use relative links. Change only those IDs in the copied bundle.
    for path in root.rglob("*.dylib"):
        if path.is_symlink():
            continue
        identity = subprocess.check_output(
            ["otool", "-arch", "arm64", "-D", str(path)], text=True
        ).splitlines()[1:]
        if identity and not identity[0].startswith("@"):
            run(["install_name_tool", "-id", f"@rpath/{path.name}", path])
    # Wheel repair tools may leave unused compiler-directory rpaths alongside
    # their valid @loader_path entries. Remove those external fallbacks.
    for path in native_files(root):
        metadata = subprocess.check_output(["otool", "-arch", "arm64", "-l", str(path)], text=True)
        for block in re.split(r"Load command \d+", metadata):
            if "LC_RPATH" in block:
                match = re.search(r"path (.+) \(offset", block)
                if (
                    match
                    and match[1].startswith("/")
                    and not match[1].startswith(("/usr/lib/", "/System/Library/"))
                ):
                    run(["install_name_tool", "-delete_rpath", match[1], path])


def audit_bundle(root):
    """Reject external symlinks/native links and compute the real OS floor."""
    minimum = (14, 0)
    binaries = list(native_files(root))
    for path in root.rglob("*"):
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            raise RuntimeError(f"安装包包含外部符号链接：{path.relative_to(root)}")
        if path.name == ".env" or path.suffix in {".sqlite", ".sqlite3"}:
            raise RuntimeError(f"安装包包含禁止的配置/数据文件：{path.relative_to(root)}")
    for path in binaries:
        links = subprocess.check_output(
            ["otool", "-arch", "arm64", "-L", str(path)], text=True
        ).splitlines()[1:]
        for line in links:
            library = line.strip().split(" (", 1)[0]
            if not library.startswith(
                ("@rpath/", "@loader_path/", "@executable_path/", "/usr/lib/", "/System/Library/")
            ):
                raise RuntimeError(f"{path.relative_to(root)} 依赖外部库：{library}")
        metadata = subprocess.check_output(["otool", "-arch", "arm64", "-l", str(path)], text=True)
        for block in re.split(r"Load command \d+", metadata):
            if "LC_RPATH" in block:
                match = re.search(r"path (.+) \(offset", block)
                if match and match[1].startswith(("/Users/", "/opt/", "/usr/local/")):
                    raise RuntimeError(f"{path.relative_to(root)} 包含外部库搜索路径")
        versions = re.findall(r"(?:minos|version) (\d+\.\d+(?:\.\d+)?)", metadata)
        # Only deployment-target commands count, not dylib compatibility versions.
        for block in re.split(r"Load command \d+", metadata):
            if "LC_BUILD_VERSION" in block or "LC_VERSION_MIN_MACOSX" in block:
                match = re.search(r"(?:minos|version) (\d+\.\d+(?:\.\d+)?)", block)
                if match:
                    minimum = max(minimum, tuple(int(part) for part in match[1].split(".")))
        if not versions:
            raise RuntimeError(f"无法读取 macOS 最低版本：{path.relative_to(root)}")
    return binaries, ".".join(map(str, minimum))


def sign_bundle(application, binaries):
    # File-provider backed build directories may add FinderInfo to .app folders.
    # Remove only signing-incompatible metadata on this generated artifact.
    for name in ("com.apple.FinderInfo", "com.apple.ResourceFork"):
        run(["xattr", "-dr", name, application])
    for path in binaries:
        if path == application / "Contents/MacOS/ClassEcho":
            continue  # The outer bundle signing step signs the main executable.
        run(
            ["codesign", "--force", "--sign", "-", "--timestamp=none", path],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    run(
        [
            "codesign",
            "--force",
            "--sign",
            "-",
            "--timestamp=none",
            "--entitlements",
            ROOT / "desktop/entitlements.plist",
            application,
        ]
    )
    run(["codesign", "--verify", "--deep", "--strict", application])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="生成镜像前运行隔离位置的完整产物冒烟测试"
    )
    args = parser.parse_args()
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit("当前安装包构建仅支持 Apple Silicon macOS")
    # Build/sign outside cloud-synced Documents: file providers can continuously
    # re-add FinderInfo while codesign is walking a large application bundle.
    with tempfile.TemporaryDirectory(prefix="classecho-build-", dir="/private/tmp") as temporary:
        application = Path(temporary) / "ClassEcho.app"
        build_application(application)
        if args.check:
            run([sys.executable, ROOT / "scripts/check_desktop.py", application])
        create_dmg(application)


def build_application(application):
    os.environ.setdefault("CLANG_MODULE_CACHE_PATH", "/private/tmp/classecho-swift-cache")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    # Remove only this builder's obsolete loose output from earlier preview builds.
    old_application = OUTPUT / "ClassEcho.app"
    if old_application.exists():
        shutil.rmtree(old_application)
    print("构建生产前端与锁定的 Python 依赖…", flush=True)
    run(["npm", "--prefix", ROOT / "frontend", "run", "build"])
    environment = ROOT / "dist/desktop-deps/venv"
    run(
        ["uv", "sync", "--locked", "--no-dev"],
        cwd=ROOT,
        env={**os.environ, "UV_PROJECT_ENVIRONMENT": str(environment)},
    )
    run([sys.executable, ROOT / "scripts/build_desktop_tools.py"])
    base = Path(
        subprocess.check_output(
            [environment / "bin/python", "-c", "import sys; print(sys.base_prefix)"], text=True
        ).strip()
    )
    contents = application / "Contents"
    resources = contents / "Resources"
    executable = contents / "MacOS/ClassEcho"
    executable.parent.mkdir(parents=True)
    print("复制独立 Python 与生产依赖…", flush=True)
    shutil.copytree(
        base,
        resources / "python",
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    packages = resources / "python/lib/python3.11/site-packages"
    shutil.rmtree(packages)
    shutil.copytree(
        environment / "lib/python3.11/site-packages",
        packages,
        symlinks=True,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "_virtualenv.*"),
    )
    # Venv console scripts contain absolute shebangs; no console entry points are used.
    for path in (resources / "python/bin").iterdir():
        if path.name not in {"python", "python3", "python3.11"}:
            path.unlink()
    relocate_library_ids(resources / "python")
    # uv also patches sysconfig with its local install prefix. Keep its values relocatable
    # without distributing the builder's personal path.
    for config in (resources / "python/lib/python3.11").glob("_sysconfigdata_*.py"):
        config.write_text(
            config.read_text().replace(str(base), "/ClassEcho/Python")
            + '\nimport sys as _sys\nbuild_time_vars = {k: v.replace("/ClassEcho/Python", _sys.base_prefix) if isinstance(v, str) else v for k, v in build_time_vars.items()}\n'
        )
    copy_application(resources / "app")
    dependencies = ROOT / "dist/desktop-deps"
    shutil.copytree(dependencies / "tools", resources / "tools")
    licenses = resources / "licenses"
    licenses.mkdir()
    shutil.copytree(dependencies / "sources", licenses / "sources")
    for source in (
        ROOT / "LICENSE",
        ROOT / "scripts/build_desktop_tools.py",
        dependencies / "tools/build.json",
        dependencies / "src/ffmpeg-8.1.2/COPYING.LGPLv2.1",
        dependencies / "src/redis-8.10.2/LICENSE.txt",
    ):
        name = "Redis-LICENSE.txt" if "redis-8.10.2" in str(source) else source.name
        shutil.copy2(source, licenses / name)
    shutil.copy2(resources / "python/lib/python3.11/LICENSE.txt", licenses / "Python-LICENSE.txt")
    inventory = sorted(
        (
            {
                "name": dist.metadata["Name"],
                "version": dist.version,
                "license": dist.metadata.get("License-Expression")
                or dist.metadata.get("License", "See package metadata"),
            }
            for dist in importlib.metadata.distributions(path=[str(packages)])
        ),
        key=lambda item: item["name"].lower(),
    )
    (licenses / "python-packages.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2)
    )
    (licenses / "README.txt").write_text(
        "ClassEcho 原创代码：MIT。\nCPython 与 Python 依赖的许可见 Python-LICENSE.txt、python-packages.json 及 python/lib/python3.11/site-packages/*dist-info 下的 LICENSE/NOTICE 文件。\nFFmpeg 使用 LGPLv2.1+ 构建，未启用 GPL/nonfree。Redis 8 core 选择 AGPLv3 许可，源码未修改、单独进程运行。\nFFmpeg 与 Redis 对应原始源码在 sources/；校验值、构建参数见 build.json 和 build_desktop_tools.py。\n可以重新构建并替换 Contents/Resources/tools/bin 中的工具；本预览版没有阻止用户替换的技术限制。\n构建脚本及应用源码：https://github.com/bobo272/ClassEcho\n",
        encoding="utf-8",
    )
    print("编译原生窗口与图标…", flush=True)
    run(
        [
            "xcrun",
            "swiftc",
            "-parse-as-library",
            "-O",
            "-swift-version",
            "5",
            "-target",
            "arm64-apple-macosx14.0",
            "-framework",
            "AppKit",
            "-framework",
            "WebKit",
            "-framework",
            "AVFoundation",
            ROOT / "desktop/App.swift",
            "-o",
            executable,
        ]
    )
    icon = OUTPUT / "make-icon"
    run(["xcrun", "swiftc", ROOT / "desktop/icon.swift", "-o", icon])
    iconset = OUTPUT / "ClassEcho.iconset"
    run([icon, iconset])
    run(["iconutil", "-c", "icns", iconset, "-o", resources / "ClassEcho.icns"])
    binaries, minimum = audit_bundle(application)
    info = {
        "CFBundleIdentifier": "io.github.bobo272.ClassEcho",
        "CFBundleExecutable": "ClassEcho",
        "CFBundleName": "ClassEcho",
        "CFBundleDisplayName": "ClassEcho",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": "0.1.0",
        "CFBundleVersion": "1",
        "CFBundleIconFile": "ClassEcho",
        "LSMinimumSystemVersion": minimum,
        "NSHighResolutionCapable": True,
        "NSMicrophoneUsageDescription": "ClassEcho 使用麦克风录制课程，在本机转录并整理笔记。",
        "NSPrincipalClass": "NSApplication",
    }
    with (contents / "Info.plist").open("wb") as output:
        plistlib.dump(info, output)
    print(f"签署 {len(binaries)} 个原生文件；最低 macOS {minimum}…", flush=True)
    sign_bundle(application, binaries)
    manifest = {
        "version": VERSION,
        "architecture": "arm64",
        "minimum_macos": minimum,
        "native_files": len(binaries),
        "python_packages": len(inventory),
        "signing": "ad-hoc; not notarized",
        "source_commit": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "source_tree_dirty": bool(
            subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip()
        ),
    }
    (OUTPUT / "build-manifest.json").write_text(json.dumps(manifest, indent=2))
    print("原生应用已签名并通过验证", flush=True)


def create_dmg(application):
    dmg = OUTPUT / f"ClassEcho-{VERSION}-macos-arm64.dmg"
    with tempfile.TemporaryDirectory(prefix="classecho-dmg-", dir="/private/tmp") as temporary:
        staging = Path(temporary)
        run(["cp", "-cR", application, staging / "ClassEcho.app"])
        (staging / "Applications").symlink_to("/Applications", target_is_directory=True)
        shutil.copy2(ROOT / "desktop/安装说明.txt", staging / "安装说明.txt")
        run(
            [
                "hdiutil",
                "create",
                "-volname",
                "ClassEcho",
                "-srcfolder",
                staging,
                "-ov",
                "-format",
                "UDZO",
                dmg,
            ]
        )
    run(["hdiutil", "verify", dmg])
    with dmg.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    (dmg.with_suffix(".dmg.sha256")).write_text(f"{digest}  {dmg.name}\n")
    print(f"安装镜像已构建：{dmg}", flush=True)


if __name__ == "__main__":
    main()
