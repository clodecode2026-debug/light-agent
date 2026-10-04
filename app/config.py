"""Конфигурация из переменных окружения."""
import os
from pathlib import Path

from dotenv import load_dotenv

try:
    import truststore
    truststore.inject_into_ssl()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent.parent
WORKSPACE = BASE_DIR / "workspace"

load_dotenv(BASE_DIR / ".env")


def _env(key: str, default: str = "") -> str:
    return os.getenv(key, default).strip()


# ---------- LLM ----------
AG_BASE_URL = _env("AG_BASE_URL", "https://agent-master-server.onrender.com/v1")
AG_API_KEY = _env("AG_API_KEY")
AG_MODEL = _env("AG_MODEL", "antigravity-3.8-flash")
AG_MODEL_FALLBACK = _env("AG_MODEL_FALLBACK", "antigravity-3.8-pro")

OPENROUTER_API_KEY = _env("OPENROUTER_API_KEY")
OPENROUTER_MODEL = _env("OPENROUTER_MODEL", "deepseek/deepseek-chat")
GROQ_API_KEY = _env("GROQ_API_KEY")
GROQ_MODEL = _env("GROQ_MODEL", "llama-3.3-70b-versatile")
GEMINI_API_KEY = _env("GEMINI_API_KEY")

# ---------- Прочее ----------
SERVICE_URL = _env("SERVICE_URL")
IDLE_SLEEP_MINUTES = int(_env("IDLE_SLEEP_MINUTES", "14") or 14)
ADMIN_TOKEN = _env("ADMIN_TOKEN", "dev-token")

SUPABASE_URL = _env("SUPABASE_URL")
SUPABASE_KEY = _env("SUPABASE_KEY")

S3_ENDPOINT = _env("S3_ENDPOINT", "https://gateway.storjshare.io")
S3_ACCESS_KEY = _env("S3_ACCESS_KEY")
S3_SECRET_KEY = _env("S3_SECRET_KEY")
S3_BUCKET = _env("S3_BUCKET", "agent-files")
S3_REGION = _env("S3_REGION", "us-east-1")

WORKSPACE.mkdir(parents=True, exist_ok=True)


def memory_enabled() -> bool:
    return bool(SUPABASE_URL and SUPABASE_KEY)


def storage_enabled() -> bool:
    return bool(S3_ACCESS_KEY and S3_SECRET_KEY)


def providers() -> list[dict]:
    """Каскад провайдеров: первый доступный — основной, остальные — фолбэк."""
    chain: list[dict] = [
        {
            "name": "antigravity",
            "base_url": AG_BASE_URL,
            "api_key": AG_API_KEY,
            "models": [AG_MODEL, AG_MODEL_FALLBACK],
        }
    ]
    if OPENROUTER_API_KEY:
        chain.append(
            {
                "name": "openrouter",
                "base_url": "https://openrouter.ai/api/v1",
                "api_key": OPENROUTER_API_KEY,
                "models": [OPENROUTER_MODEL],
            }
        )
    if GROQ_API_KEY:
        chain.append(
            {
                "name": "groq",
                "base_url": "https://api.groq.com/openai/v1",
                "api_key": GROQ_API_KEY,
                "models": [GROQ_MODEL],
            }
        )
    if GEMINI_API_KEY:
        chain.append(
            {
                "name": "gemini",
                "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
                "api_key": GEMINI_API_KEY,
                "models": ["gemini-2.0-flash"],
            }
        )
    return [p for p in chain if p["api_key"]]