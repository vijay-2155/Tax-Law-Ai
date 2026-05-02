"""
Central configuration — reads from .env (project root) via python-dotenv.

Import this everywhere instead of reading os.environ directly.

Embedding: Qwen/Qwen3-Embedding-0.6B via sentence-transformers (1024-dim)
Reranker : BAAI/bge-reranker-large via sentence-transformers CrossEncoder

Qdrant modes:
  Local Docker (default): QDRANT_URL=http://localhost:6333, QDRANT_API_KEY=(empty)
  Cloud:                  QDRANT_URL=https://....qdrant.io, QDRANT_API_KEY=<key>
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


# ── Qdrant (local Docker or Cloud) ───────────────────────────────────────────
# Local mode: set QDRANT_URL=http://localhost:6333 and leave QDRANT_API_KEY empty
# Cloud mode: set both QDRANT_URL and QDRANT_API_KEY

QDRANT_URL: str = os.environ.get("QDRANT_URL", "http://localhost:6333").strip()
QDRANT_API_KEY: str = os.environ.get("QDRANT_API_KEY", "").strip()

# True when running against local Docker Qdrant (no auth needed)
QDRANT_LOCAL: bool = not QDRANT_API_KEY

# ── Ollama (chat only — no longer used for embeddings) ───────────────────────

OLLAMA_BASE_URL: str = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434").strip()
OLLAMA_CHAT_MODEL: str = os.environ.get("OLLAMA_CHAT_MODEL", "qwen2.5:7b").strip()

# ── HuggingFace local inference ───────────────────────────────────────────────
# Embedding model: Qwen3-Embedding-0.6B (1024-dim, ~2.4 GB, auto-downloaded)
HF_EMBED_MODEL: str = os.environ.get("HF_EMBED_MODEL", "Qwen/Qwen3-Embedding-0.6B").strip()
# Reranker model: BGE cross-encoder (1.3 GB, auto-downloaded)
HF_RERANKER_MODEL: str = os.environ.get("HF_RERANKER_MODEL", "BAAI/bge-reranker-large").strip()
# Device: auto-detect CUDA/MPS/CPU, or force via env var
EMBED_DEVICE: str = os.environ.get("EMBED_DEVICE", "").strip()
# HuggingFace token (for gated models / faster downloads)
HF_TOKEN: str = os.environ.get("HF_TOKEN", "").strip()

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
        errors.append("QDRANT_URL is not set — defaulting to http://localhost:6333")
    # QDRANT_API_KEY is optional: empty means local Docker mode (no auth)
    if QDRANT_API_KEY and not QDRANT_URL:
        errors.append("QDRANT_API_KEY is set but QDRANT_URL is missing")
    return errors


def summary() -> str:
    """Human-readable config summary (masks secrets)."""
    def mask(s: str) -> str:
        return s[:8] + "..." if len(s) > 8 else ("(not set)" if not s else s)

    lines = [
        f"  QDRANT_URL     : {QDRANT_URL or '(not set)'}",
        f"  QDRANT_MODE    : {'local Docker (no auth)' if QDRANT_LOCAL else 'cloud'}",
        f"  QDRANT_API_KEY : {mask(QDRANT_API_KEY)}",
        f"  EMBED_MODEL    : {HF_EMBED_MODEL}",
        f"  RERANKER_MODEL : {HF_RERANKER_MODEL}",
        f"  EMBED_DEVICE   : {EMBED_DEVICE or 'auto'}",
        f"  HF_TOKEN       : {'set' if HF_TOKEN else '(not set)'}",
        f"  OLLAMA_BASE    : {OLLAMA_BASE_URL} (chat only)",
        f"  LLM_PROVIDER   : {LLM_PROVIDER}",
        f"  LLM_MODEL      : {LLM_MODEL}",
        f"  APP            : {APP_HOST}:{APP_PORT}",
    ]
    return "\n".join(lines)
