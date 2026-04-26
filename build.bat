@echo off
setlocal enabledelayedexpansion

:: ============================================================================
:: TaxIQ Windows Build Script
:: Builds a standalone TaxIQ.exe with all dependencies bundled.
::
:: Usage:   build.bat
:: Output:  dist\TaxIQ\TaxIQ.exe
:: ============================================================================

echo.
echo  ============================================
echo   TaxIQ - Windows Build
echo  ============================================
echo.

:: ── Check prerequisites ──────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install Python 3.10+ from python.org
    echo         Make sure to check "Add Python to PATH" during installation.
    pause
    exit /b 1
)

where node >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Node.js not found. Install Node.js 18+ from nodejs.org
    pause
    exit /b 1
)

:: Display versions
echo [INFO] Python version:
python --version
echo [INFO] Node version:
node --version
echo.

:: ── Install Python dependencies ──────────────────────────────────────────────
echo [1/4] Installing Python dependencies...
pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install Python dependencies
    pause
    exit /b 1
)
pip install pyinstaller>=6.11.0 --quiet
if errorlevel 1 (
    echo [ERROR] Failed to install PyInstaller
    pause
    exit /b 1
)
echo       Done.
echo.

:: ── Build React frontend ─────────────────────────────────────────────────────
echo [2/4] Building React frontend...
cd frontend
call npm install --silent 2>nul
if errorlevel 1 (
    echo [ERROR] npm install failed
    cd ..
    pause
    exit /b 1
)
call npm run build
if errorlevel 1 (
    echo [ERROR] Frontend build failed
    cd ..
    pause
    exit /b 1
)
cd ..
echo       Done. Output: frontend\dist\
echo.

:: ── Verify frontend build exists ─────────────────────────────────────────────
if not exist "frontend\dist\index.html" (
    echo [ERROR] frontend\dist\index.html not found - build may have failed
    pause
    exit /b 1
)

:: ── Run PyInstaller ──────────────────────────────────────────────────────────
echo [3/4] Packaging with PyInstaller (this may take a few minutes)...
pyinstaller build\TaxIQ.spec --clean --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller build failed
    echo         Check the output above for details.
    pause
    exit /b 1
)
echo       Done.
echo.

:: ── Report results ───────────────────────────────────────────────────────────
echo [4/4] Build complete!
echo.
echo  ============================================
echo   OUTPUT: dist\TaxIQ\TaxIQ.exe
echo  ============================================
echo.
echo  To run:
echo    dist\TaxIQ\TaxIQ.exe
echo.
echo  To create an installer (requires NSIS):
echo    makensis build\installer.nsi
echo.
pause
