@echo off
setlocal enabledelayedexpansion
:: ─────────────────────────────────────────────────────────────────────────────
:: start.bat — One-click TaxIQ launcher for Windows
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
    echo.
    echo  Please edit .env with your LLM API key, then run start.bat again.
    echo  (Or leave as-is to use Ollama signed-in mode via the Settings UI)
    echo.
    notepad .env
    pause
    exit /b 0
)

echo  [OK] .env found.

:: ── Start services ────────────────────────────────────────────────────────────
echo.
echo  [INFO] Starting TaxIQ...

docker compose up -d
if errorlevel 1 (
    echo  [ERROR] Failed to start Docker services.
    echo         Check logs: docker compose logs
    pause
    exit /b 1
)

:: ── Wait for health check ─────────────────────────────────────────────────────
echo.
echo  [INFO] Waiting for TaxIQ to be ready...

set READY=0
for /l %%i in (1,1,60) do (
    curl -sf http://localhost:8000/api/health >nul 2>&1
    if not errorlevel 1 (
        set READY=1
        goto :ready
    )
    echo  Waiting... (%%i/60)
    timeout /t 3 /nobreak >nul
)

:ready
echo.
if "!READY!"=="1" (
    echo  [OK] TaxIQ is ready!
    echo.
    echo  Opening http://localhost:8000 ...
    echo.
    echo  First run? Data loads automatically in the background (~2 min).
    echo  Stop app:   docker compose down
    echo  Full reset: docker compose down -v
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
