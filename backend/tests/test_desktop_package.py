"""Packaging must never sweep local recordings, config or test data into the app."""

from scripts import build_desktop


def test_packaging_uses_runtime_allowlist(tmp_path, monkeypatch):
    source, target = tmp_path / "source", tmp_path / "app"
    for name in (
        "backend/app/main.py",
        "backend/migrations/versions/0001.py",
        "backend/__init__.py",
        "backend/alembic.ini",
        "scripts/run.py",
        "desktop/runtime.py",
        "samples/demo.json",
        "LICENSE",
        "frontend/dist/index.html",
        "frontend/dist/assets/app.js",
        "frontend/dist/assets/app.js.map",
        ".env",
        "data/notes-api.json",
        "data/private.m4a",
        "backend/tests/private.json",
        "backend/app/__pycache__/main.pyc",
    ):
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fixture")
    monkeypatch.setattr(build_desktop, "ROOT", source)
    build_desktop.copy_application(target)
    files = {path.relative_to(target).as_posix() for path in target.rglob("*") if path.is_file()}
    assert files == {
        "backend/app/main.py",
        "backend/migrations/versions/0001.py",
        "backend/__init__.py",
        "backend/alembic.ini",
        "scripts/run.py",
        "desktop/runtime.py",
        "samples/demo.json",
        "LICENSE",
        "frontend/dist/index.html",
        "frontend/dist/assets/app.js",
    }


def test_bundle_rejects_symlink_to_machine_data(tmp_path):
    import pytest

    (tmp_path / "external").symlink_to(tmp_path.parent)
    with pytest.raises(RuntimeError, match="外部符号链接"):
        build_desktop.audit_bundle(tmp_path)


def test_packaging_rejects_embedded_builder_metadata_across_read_boundaries(tmp_path):
    import pytest

    needle = b"/Users/private-builder"
    (tmp_path / "tool").write_bytes(b"\0" * (1024 * 1024 - 4) + needle + b"\0")
    with pytest.raises(RuntimeError, match="构建机路径或机器名"):
        build_desktop.audit_builder_metadata(tmp_path, [needle])


def test_public_relative_runtime_metadata_is_allowed(tmp_path):
    (tmp_path / "config.py").write_text('root = "/ClassEcho/Python"')
    build_desktop.audit_builder_metadata(tmp_path, [b"/Users/private-builder"])
