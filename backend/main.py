"""
FastAPI application entry point.

Startup:
  uvicorn backend.main:app --reload           (dev)
  python -m backend.main                      (production / PyWebView)

The app:
  - Mounts the React frontend as static files from frontend/dist
  - Exposes all /api/* routes
  - Holds QdrantStore + Retriever + LLMConfig in app.state (shared singletons)
"""

from __future__ import annotations
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

# Ensure project root is on path when run as script
sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.config import (
    APP_HOST, APP_PORT,
    LLM_PROVIDER, LLM_MODEL, LLM_API_KEY, LLM_BASE_URL,
)
from backend.indexing.qdrant_store import QdrantStore
from backend.rag.retriever import Retriever
from backend.rag.llm_provider import LLMConfig
from backend.api.routes_search import router as search_router
from backend.api.routes_section import router as section_router
from backend.api.routes_chat import router as chat_router
from backend.api.routes_heads import router as heads_router
from backend.api.routes_settings import router as settings_router


# ---------------------------------------------------------------------------
# Lifespan (startup / shutdown)
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("Starting Income Tax Validator...")

    store = QdrantStore()
    app.state.store = store
    app.state.retriever = Retriever(store)

    # Build default LLM config from env
    provider_keys = {}
    for p, env_var in [
        ("ollama_cloud", "OLLAMA_CLOUD_API_KEY"),
        ("openai",       "OPENAI_API_KEY"),
        ("anthropic",    "ANTHROPIC_API_KEY"),
        ("gemini",       "GEMINI_API_KEY"),
        ("groq",         "GROQ_API_KEY"),
        ("openrouter",   "OPENROUTER_API_KEY"),
    ]:
        val = os.environ.get(env_var)
        if val:
            provider_keys[p] = val

    app.state.llm_config = LLMConfig(
        provider=LLM_PROVIDER,
        model=LLM_MODEL,
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        provider_api_keys=provider_keys,
    )

    try:
        counts = {
            "2025": store.collection_point_count("2025"),
            "1961": store.collection_point_count("1961"),
        }
        print(f"Qdrant ready — 2025: {counts['2025']:,} pts | 1961: {counts['1961']:,} pts")
    except Exception as e:
        print(f"Warning: Qdrant connection failed at startup ({e}). Retrying on first request.")
    print(f"LLM: {app.state.llm_config.provider} / {app.state.llm_config.model}")

    yield

    # Shutdown
    store.close()
    print("Shutdown complete.")


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Income Tax Validator",
    description="RAG-powered Income Tax Act search and analysis tool for CAs",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow dev frontend (Vite on :5173) and production (same origin)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        f"http://{APP_HOST}:{APP_PORT}",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

app.include_router(search_router, prefix="/api", tags=["search"])
app.include_router(section_router, prefix="/api", tags=["sections"])
app.include_router(chat_router, prefix="/api", tags=["chat"])
app.include_router(heads_router, prefix="/api", tags=["heads"])
app.include_router(settings_router, prefix="/api", tags=["settings"])


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


# ---------------------------------------------------------------------------
# Static frontend (production build)
# ---------------------------------------------------------------------------

# In a frozen PyInstaller bundle, __file__ is unreliable — use _MEIPASS
if getattr(sys, "frozen", False):
    _FRONTEND_DIST = Path(sys._MEIPASS) / "frontend" / "dist"  # type: ignore[attr-defined]
else:
    _FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"

if _FRONTEND_DIST.exists():
    # Serve React build
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """Serve index.html for all non-API routes (SPA routing)."""
        return FileResponse(_FRONTEND_DIST / "index.html")
else:
    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "message": "Income Tax Validator API",
            "docs": "/docs",
            "note": "Frontend not built yet — run: cd frontend && npm run build",
        }


# ---------------------------------------------------------------------------
# Script entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    # Check if we should launch PyWebView
    use_webview = "--webview" in sys.argv or os.environ.get("USE_WEBVIEW") == "1"

    if use_webview:
        import threading
        import webview

        def start_server():
            uvicorn.run(app, host=APP_HOST, port=APP_PORT, log_level="warning")

        server_thread = threading.Thread(target=start_server, daemon=True)
        server_thread.start()

        import time
        time.sleep(2)  # Wait for server to start

        webview.create_window(
            "Income Tax Validator",
            f"http://{APP_HOST}:{APP_PORT}",
            width=1280,
            height=800,
            resizable=True,
        )
        webview.start()
    else:
        uvicorn.run(
            "backend.main:app",
            host=APP_HOST,
            port=APP_PORT,
            reload=True,
            log_level="info",
        )
