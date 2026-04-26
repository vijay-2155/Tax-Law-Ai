"""
Central configuration — reads from .env (project root) via python-dotenv.

Import this everywhere instead of reading os.environ directly.
"""

from __future__ import annotations
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# ── Resolve root differently when running as PyInstaller bundle ───────────────
if getattr(sys, "frozen", False):
    _BUNDLE = Path(sys._MEIPASS)  # type: ignore[attr-defined]
    _ROOT = _BUNDLE
    load_dotenv(_BUNDLE / ".env", override=False)
else:
    _ROOT = Path(__file__).parent.parent
    load_dotenv(_ROOT / ".env", override=False)


# ── Qdrant Cloud ──────────────────────────────────────────────────────────────

QDRANT_URL: str = os.environ.get("QDRANT_URL", "").strip()
QDRANT_API_KEY: str = os.environ.get("QDRANT_API_KEY", "").strip()

# ── Ollama ────────────────────────────────────────────────────────────────────

OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_EMBED_MODEL: str = os.environ.get("OLLAMA_EMBED_MODEL", "qwen3-embedding").strip()
OLLAMA_CHAT_MODEL: str = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:7b").strip()

# ── LLM provider (default — users can override in the Settings UI) ────────────

LLM_PROVIDER: str = os.environ.get("LLM_PROVIDER", "ollama").strip()
LLM_MODEL: str = os.environ.get("LLM_MODEL", OLLAMA_CHAT_MODEL).strip()
LLM_API_KEY: str = os.environ.get("LLM_API_KEY", "").strip()
LLM_BASE_URL: str = os.environ.get("LLM_BASE_URL", "").strip()

# ── FastAPI ───────────────────────────────────────────────────────────────────

APP_HOST: str = os.environ.get("APP_HOST", "127.0.0.1").strip()
APP_PORT: int = int(os.environ.get("APP_PORT", "8000"))

# ── Paths ─────────────────────────────────────────────────────────────────────

ROOT_DIR: Path = _ROOT

# When packaged, writable data (summaries, cache) lives in %APPDATA%\TaxIQ
_user_data_env = os.environ.get("TAXIQ_USER_DATA")
if _user_data_env:
    DATA_DIR: Path = Path(_user_data_env)
elif getattr(sys, "frozen", False):
    _appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    DATA_DIR = Path(_appdata) / "TaxIQ"
else:
    DATA_DIR = _ROOT / "backend" / "data"

PDF_DIR: Path = _ROOT / "pdfs"


def validate() -> list[str]:
    """Return a list of missing/invalid config values."""
    errors: list[str] = []
    if not QDRANT_URL:
        errors.append("QDRANT_URL is not set (required for Qdrant Cloud)")
    if not QDRANT_API_KEY:
        errors.append("QDRANT_API_KEY is not set (required for Qdrant Cloud)")
    return errors


def summary() -> str:
    """Human-readable config summary (masks secrets)."""
    def mask(s: str) -> str:
        return s[:8] + "..." if len(s) > 8 else ("(not set)" if not s else s)

    lines = [
        f"  QDRANT_URL     : {QDRANT_URL or '(not set)'}",
        f"  QDRANT_API_KEY : {mask(QDRANT_API_KEY)}",
        f"  OLLAMA_BASE    : {OLLAMA_BASE_URL}",
        f"  EMBED_MODEL    : {OLLAMA_EMBED_MODEL}",
        f"  LLM_PROVIDER   : {LLM_PROVIDER}",
        f"  LLM_MODEL      : {LLM_MODEL}",
        f"  APP            : {APP_HOST}:{APP_PORT}",
    ]
    return "\n".join(lines)
