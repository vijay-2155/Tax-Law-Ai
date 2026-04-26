# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec for TaxIQ — Income Tax Law Assistant.

Build from project root:
    pyinstaller build/TaxIQ.spec --clean
"""
from pathlib import Path

ROOT = Path(SPECPATH).parent  # project root

# ── Data files bundled into the exe ───────────────────────────────────────────
datas = [
    # React frontend build
    (str(ROOT / "frontend" / "dist"), "frontend/dist"),
    # .env with Qdrant keys (baked into bundle — users don't need to configure)
    (str(ROOT / ".env"), "."),
    # Read-only data: summaries cache + examples (exclude large .npy vector files)
    (str(ROOT / "backend" / "data" / "summaries"), "backend/data/summaries"),
    (str(ROOT / "backend" / "data" / "examples"), "backend/data/examples"),
    # Backend Python package (ensures all modules are found in frozen bundle)
    (str(ROOT / "backend"), "backend"),
]

# Only include chunk JSON files if they exist (needed for section browsing)
for json_file in ["chunks_2025.json", "chunks_1961.json"]:
    p = ROOT / "backend" / "data" / json_file
    if p.exists():
        datas.append((str(p), "backend/data"))

# ── Hidden imports PyInstaller can't detect automatically ─────────────────────
hiddenimports = [
    # uvicorn internals
    "uvicorn.main",
    "uvicorn.config",
    "uvicorn.loops",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.http.httptools_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.protocols.websockets.websockets_impl",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.middleware.proxy_headers",
    # starlette / fastapi
    "starlette",
    "starlette.routing",
    "starlette.staticfiles",
    "starlette.responses",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette._utils",
    "fastapi",
    "fastapi.staticfiles",
    "fastapi.responses",
    "fastapi.middleware",
    "fastapi.middleware.cors",
    # SSE streaming (used in chat routes)
    "sse_starlette",
    "sse_starlette.sse",
    # pydantic
    "pydantic",
    "pydantic.v1",
    "pydantic_settings",
    # qdrant
    "qdrant_client",
    "qdrant_client.http",
    "qdrant_client.http.models",
    "qdrant_client.http.models.models",
    "qdrant_client.async_qdrant_client",
    # langgraph / langchain
    "langgraph",
    "langgraph.graph",
    "langgraph.graph.message",
    "langgraph.graph.state",
    "langchain_core",
    "langchain_core.messages",
    "langchain_core.runnables",
    # LLM providers
    "anthropic",
    "openai",
    "google.genai",
    "groq",
    # web search
    "ddgs",
    "primp",
    # httpx / networking
    "httpx",
    "h11",
    "anyio",
    "anyio.from_thread",
    "anyio._backends._asyncio",
    # pywebview (Windows)
    "webview",
    "webview.platforms.winforms",
    "webview.platforms.edgechromium",
    # misc
    "dotenv",
    "python_dotenv",
    "click",
    "tqdm",
    "numpy",
    "multipart",
    "python_multipart",
    # Windows-specific stdlib modules that PyInstaller sometimes misses
    "email.mime.multipart",
    "email.mime.text",
]

a = Analysis(
    [str(ROOT / "app_entry.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PIL", "cv2", "torch"],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TaxIQ",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,        # no terminal window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "build" / "icon.ico") if (ROOT / "build" / "icon.ico").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TaxIQ",
)
