"""
Settings routes — LLM provider configuration.

GET  /api/settings          → current provider config
PUT  /api/settings          → update provider, model, api_key  (persists to .env)
POST /api/settings/test     → test connection
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel

from ..rag.llm_provider import LLMConfig, DEFAULT_MODELS

router = APIRouter()

# Path to .env at project root
_ENV_FILE = Path(__file__).parent.parent.parent / ".env"

# LLM keys we persist (maps env var name → LLMConfig field)
_LLM_ENV_KEYS: dict[str, str] = {
    "LLM_PROVIDER": "provider",
    "LLM_MODEL":    "model",
    "LLM_API_KEY":  "api_key",
    "LLM_BASE_URL": "base_url",
}

_PROVIDER_KEY_MAP: dict[str, str] = {
    "ollama_cloud": "OLLAMA_CLOUD_API_KEY",
    "openai":       "OPENAI_API_KEY",
    "anthropic":    "ANTHROPIC_API_KEY",
    "gemini":       "GEMINI_API_KEY",
    "groq":         "GROQ_API_KEY",
    "openrouter":   "OPENROUTER_API_KEY",
    "nvidia":       "NVIDIA_API_KEY",
}


class SettingsUpdate(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None
    base_url: str | None = None
    provider_api_keys: dict[str, str] | None = None
    # temperature and max_tokens are locked at optimal defaults — not configurable


@router.get("/settings")
async def get_settings(request: Request) -> dict[str, Any]:
    """Return current LLM config (mask API key)."""
    cfg: LLMConfig = request.app.state.llm_config
    
    # Pack masked provider keys
    masked_provider_keys = {
        p: _mask_key(cfg.provider_api_keys.get(p, ""))
        for p in _PROVIDER_KEY_MAP
    }

    return {
        "provider": cfg.provider,
        "model": cfg.model,
        "api_key": _mask_key(cfg.api_key),
        "base_url": cfg.base_url,
        "provider_api_keys": masked_provider_keys,
        "available_providers": list(DEFAULT_MODELS.keys()),
        "available_models": DEFAULT_MODELS,
    }


@router.put("/settings")
async def update_settings(
    request: Request,
    body: SettingsUpdate,
) -> dict[str, Any]:
    """Update LLM config in-memory and persist to .env."""
    cfg: LLMConfig = request.app.state.llm_config

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = cfg.model_copy(update=updates)
    request.app.state.llm_config = updated

    # Persist to .env so config survives restarts
    _persist_to_env(updated)

    return {
        "ok": True,
        "provider": updated.provider,
        "model": updated.model,
        "api_key": _mask_key(updated.api_key),
    }


@router.post("/settings/test")
async def test_connection(request: Request) -> dict[str, Any]:
    """Test LLM connection with current config."""
    cfg: LLMConfig = request.app.state.llm_config

    from ..rag.llm_provider import get_provider
    provider = get_provider(cfg)

    try:
        response = await provider.chat(
            "You are a test assistant.",
            [{"role": "user", "content": "Reply with exactly: OK"}],
        )
        success = bool(response.strip())
        return {
            "ok": success,
            "provider": cfg.provider,
            "model": cfg.model,
            "response_preview": response[:100],
        }
    except Exception as e:
        return {
            "ok": False,
            "provider": cfg.provider,
            "model": cfg.model,
            "error": str(e),
        }


# ── Helpers ───────────────────────────────────────────────────────────────────

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "***"
    return key[:4] + "..." + key[-4:]


def _persist_to_env(cfg: LLMConfig) -> None:
    """
    Write LLM_PROVIDER / LLM_MODEL / LLM_API_KEY / LLM_BASE_URL back to .env.
    - Updates existing lines in-place (preserving all other content).
    - Appends any missing lines.
    - Never touches QDRANT_* or other variables.
    """
    try:
        # Build the values we want to write
        new_values: dict[str, str] = {
            "LLM_PROVIDER": cfg.provider,
            "LLM_MODEL":    cfg.model,
            "LLM_API_KEY":  cfg.api_key,
            "LLM_BASE_URL": cfg.base_url,
        }
        
        # Add provider-specific keys
        for p, env_var in _PROVIDER_KEY_MAP.items():
            val = cfg.provider_api_keys.get(p)
            if val is not None:
                new_values[env_var] = val

        # Read existing .env (create if missing)
        if _ENV_FILE.exists():
            lines = _ENV_FILE.read_text(encoding="utf-8").splitlines(keepends=True)
        else:
            lines = []

        # Update lines that already exist
        touched: set[str] = set()
        for i, line in enumerate(lines):
            for key in new_values:
                if re.match(rf"^\s*{key}\s*=", line):
                    lines[i] = f"{key}={new_values[key]}\n"
                    touched.add(key)
                    break

        # Append keys that were not in the file
        for key, val in new_values.items():
            if key not in touched:
                lines.append(f"{key}={val}\n")

        _ENV_FILE.write_text("".join(lines), encoding="utf-8")

        # Also update the live process environment so the running app sees it
        for key, val in new_values.items():
            os.environ[key] = val

    except Exception as exc:
        # Non-fatal — config still works in memory
        import logging
        logging.getLogger(__name__).warning("Could not persist settings to .env: %s", exc)
