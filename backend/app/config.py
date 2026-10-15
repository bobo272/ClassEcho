import math
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    redis_url: str
    qwen_key: str
    qwen_base_url: str
    qwen_model: str
    budget_cny: float
    input_price: float | None
    output_price: float | None
    max_upload_bytes: int = 500 * 1024 * 1024
    max_duration: float = 90 * 60
    max_output_tokens: int = 4096
    max_note_chars: int = 60000


@lru_cache
def get_settings() -> Settings:
    load_dotenv(ROOT / ".env", override=False)

    def price(name):
        value = os.getenv(name, "").strip()
        return float(value) if value else None

    settings = Settings(
        data_dir=Path(os.getenv("CLASSECHO_DATA_DIR", str(ROOT / "data"))).expanduser().resolve(),
        redis_url=os.getenv("CLASSECHO_REDIS_URL", "redis://127.0.0.1:6387/0"),
        qwen_key=os.getenv("QWEN_API_KEY", ""),
        qwen_base_url=os.getenv(
            "QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        qwen_model=os.getenv("QWEN_MODEL", "qwen-plus"),
        budget_cny=float(os.getenv("CLASSECHO_BUDGET_CNY", "0")),
        input_price=price("QWEN_INPUT_CNY_PER_MILLION"),
        output_price=price("QWEN_OUTPUT_CNY_PER_MILLION"),
    )
    if (
        not math.isfinite(settings.budget_cny)
        or settings.budget_cny < 0
        or any(
            p is not None and (not math.isfinite(p) or p < 0)
            for p in (settings.input_price, settings.output_price)
        )
    ):
        raise ValueError("预算和单价不能为负数")
    return settings
