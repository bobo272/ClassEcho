"""User-owned Chat Completions settings; secrets never appear in API responses."""

import fcntl
import json
import os
import tempfile
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator

from .config import get_settings
from .db import new_id
from .schemas import StrictModel


class APIInput(StrictModel):
    base_url: str = Field(max_length=2000)
    model: str = Field(max_length=200)
    api_key: SecretStr | None = Field(default=None, max_length=8192)

    @field_validator("base_url")
    @classmethod
    def validate_url(cls, value):
        value = value.strip().rstrip("/")
        if not value:
            return value
        parsed = urlsplit(value)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
            or parsed.query
            or parsed.fragment
            or any(char.isspace() for char in value)
        ):
            raise ValueError("接口 URL 必须是无凭据、无查询参数的 HTTP(S) 地址")
        _ = parsed.port
        # Accept either a base URL or the complete Chat Completions endpoint.
        return value.removesuffix("/chat/completions")

    @field_validator("model")
    @classmethod
    def clean_model(cls, value):
        return value.strip()

    @field_validator("api_key")
    @classmethod
    def clean_key(cls, value):
        if value is not None:
            key = value.get_secret_value().strip()
            if any(char.isspace() for char in key):
                raise ValueError("密钥不能包含空白字符")
            return SecretStr(key)
        return value


class APIConfig(APIInput):
    revision: str = ""

    @property
    def configured(self):
        return bool(
            self.base_url and self.model and self.api_key and self.api_key.get_secret_value()
        )

    def public(self):
        return {
            "base_url": self.base_url,
            "model": self.model,
            "key_configured": bool(self.api_key and self.api_key.get_secret_value()),
            "configured": self.configured,
            "revision": self.revision,
        }


def load_api_config():
    path = get_settings().data_dir / "notes-api.json"
    if not path.exists():
        return APIConfig(base_url="", model="")
    try:
        return APIConfig.model_validate_json(path.read_text())
    except (OSError, ValueError):
        raise ValueError("AI 接口配置无法读取，请在设置中重新保存") from None


def save_api_config(body: APIInput):
    directory = get_settings().data_dir
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / ".notes-api.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = load_api_config()
        key = body.api_key
        if not key or not key.get_secret_value():
            # A different server must never receive the previous server's key implicitly.
            key = previous.api_key if body.base_url == previous.base_url else None
        config = APIConfig(base_url=body.base_url, model=body.model, api_key=key, revision=new_id())
        payload = {
            **config.public(),
            "api_key": key.get_secret_value() if key else None,
        }
        payload.pop("configured")
        payload.pop("key_configured")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as output:
                temporary = output.name
                os.fchmod(output.fileno(), 0o600)
                json.dump(payload, output, ensure_ascii=False)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, directory / "notes-api.json")
        finally:
            if temporary and os.path.exists(temporary):
                os.unlink(temporary)
    return config
