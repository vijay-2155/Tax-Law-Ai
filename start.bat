@echo off
setlocal enabledelayedexpansion
:: ─────────────────────────────────────────────────────────────────────────────
:: start.bat — One-click TaxIQ launcher for Windows
:: No Ollama installation needed — everything runs inside Docker!
:: ─────────────────────────────────────────────────────────────────────────────

echo.
echo  ================================================
echo    TaxIQ -- Income Tax AI Assistant
echo  ================================================
echo.

:: ── Check Docker ──────────────────────────────────────────────────────────────
where docker >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker not found.
    echo         Install Docker Desktop from: https://www.docker.com/products/docker-desktop
    pause
    exit /b 1
)

docker info >nul 2>&1
if errorlevel 1 (
    echo  [ERROR] Docker is not running.
    echo         Please start Docker Desktop and try again.
    pause
    exit /b 1
)

echo  [OK] Docker is running.

:: ── Check .env ────────────────────────────────────────────────────────────────
if not exist ".env" (
    echo  [INFO] .env not found -- creating from template...
    copy .env.example .env >nul
    echo  [OK]  .env created with default local Ollama settings.
    echo         No manual configuration needed!
    echo.
)

echo  [OK] .env found.

:: ── Read model from .env (default: qwen2.5:7b) ───────────────────────────────
set OLLAMA_MODEL=qwen2.5:7b
for /f "tokens=2 delims==" %%a in ('findstr /b "OLLAMA_CHAT_MODEL=" .env 2^>nul') do (
    set OLLAMA_MODEL=%%a
)
if "!OLLAMA_MODEL!"=="" set OLLAMA_MODEL=qwen2.5:7b

:: ── Start services ────────────────────────────────────────────────────────────
echo.
echo  [INFO] Starting TaxIQ (Qdrant + Ollama + App)...
echo         No Ollama host configuration needed!
echo.

docker compose up -d
if errorlevel 1 (
    echo  [ERROR] Failed to start Docker services.
    echo         Check logs: docker compose logs
    pause
    exit /b 1
)

:: ── Wait for Ollama ───────────────────────────────────────────────────────────
echo.
echo  [INFO] Waiting for Ollama to start...

set OLLAMA_READY=0
for /l %%i in (1,1,30) do (
    curl -sf http://localhost:11434/api/tags >nul 2>&1
    if not errorlevel 1 (
        set OLLAMA_READY=1
        goto :ollama_ready
    )
    echo  Waiting for Ollama... (%%i/30)
    timeout /t 3 /nobreak >nul
)

:ollama_ready
if "!OLLAMA_READY!"=="1" (
    echo  [OK] Ollama is ready.

    :: Check if model is already pulled
    curl -sf http://localhost:11434/api/tags 2>nul | findstr /c:"!OLLAMA_MODEL!" >nul 2>&1
    if errorlevel 1 (
        echo.
        echo  [INFO] Pulling model '!OLLAMA_MODEL!' into Ollama...
        echo         One-time download (~4-5 GB). Models are cached between restarts.
        echo.
        docker compose exec ollama ollama pull !OLLAMA_MODEL!
        echo  [OK] Model '!OLLAMA_MODEL!' ready.
    ) else (
        echo  [OK] Model '!OLLAMA_MODEL!' already cached.
    )
) else (
    echo  [WARN] Ollama is taking longer than expected.
    echo         The model will be pulled automatically on first use.
)

:: ── Wait for app health check ─────────────────────────────────────────────────
echo.
echo  [INFO] Waiting for TaxIQ app to be ready...

set READY=0
for /l %%i in (1,1,60) do (
    curl -sf http://localhost:8000/api/health >nul 2>&1
    if not errorlevel 1 (
        set READY=1
        goto :app_ready
    )
    echo  Waiting... (%%i/60)
    timeout /t 3 /nobreak >nul
)

:app_ready
echo.
if "!READY!"=="1" (
    echo  [OK] TaxIQ is ready!
    echo.
    echo  LLM Model:  !OLLAMA_MODEL! (running locally in Docker)
    echo  Opening:    http://localhost:8000
    echo.
    echo  First run?  Data loads automatically in the background (~2 min).
    echo  Stop app:   docker compose down
    echo  Full reset: docker compose down -v   WARNING: clears models + data
    echo.
    start http://localhost:8000
) else (
    echo  [WARN] TaxIQ is taking longer than expected.
    echo        Check logs: docker compose logs app
    echo        App URL: http://localhost:8000 (may still be loading)
    echo.
    start http://localhost:8000
)

pause
