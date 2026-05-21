import os
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


DEEPSEEK_BASE_URL = "https://api.deepseek.com"
DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

load_dotenv()
load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not configured")
    return value


def get_generation_client(timeout: int = 60) -> OpenAI:
    return OpenAI(
        api_key=_required_env("DEEPSEEK_API_KEY"),
        base_url=os.getenv("DEEPSEEK_BASE_URL", DEEPSEEK_BASE_URL),
        timeout=timeout,
    )


def get_generation_model(default: str = "deepseek-v4-pro") -> str:
    return os.getenv("DEEPSEEK_MODEL", default)


def get_fast_generation_model(default: str = "deepseek-v4-flash") -> str:
    return os.getenv("DEEPSEEK_FAST_MODEL", default)


def get_embedding_api_key() -> str:
    return _required_env("DASHSCOPE_API_KEY")


def get_embedding_base_url() -> str:
    return os.getenv("DASHSCOPE_BASE_URL", DASHSCOPE_BASE_URL)


def get_embedding_model(default: str = "text-embedding-v3") -> str:
    return os.getenv("EMBEDDING_MODEL", default)


def get_embedding_dimensions(default: int = 1024) -> int:
    return int(os.getenv("EMBEDDING_DIMENSIONS", str(default)))
