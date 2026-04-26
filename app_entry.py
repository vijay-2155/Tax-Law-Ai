"""
PyInstaller entry point for the packaged Windows app.

When frozen:
  - sys._MEIPASS = extracted bundle dir (read-only)
  - APPDATA/TaxIQ  = writable user data (summaries cache, settings)
"""
from __future__ import annotations
import os
import sys
import threading
import time
import traceback
import webbrowser

# ── Path fix for frozen bundle ─────────────────────────────────────────────────
if getattr(sys, "frozen", False):
    bundle_dir = sys._MEIPASS  # type: ignore[attr-defined]
    # Put bundle dir at front of path so all backend imports resolve correctly
    sys.path.insert(0, bundle_dir)
    os.chdir(bundle_dir)

    # Writable user-data dir lives in %APPDATA%\TaxIQ
    appdata = os.environ.get("APPDATA") or os.path.expanduser("~")
    user_data = os.path.join(appdata, "TaxIQ")
    os.makedirs(os.path.join(user_data, "summaries"), exist_ok=True)
    os.makedirs(os.path.join(user_data, "examples"), exist_ok=True)
    os.makedirs(os.path.join(user_data, "logs"), exist_ok=True)

    os.environ["TAXIQ_USER_DATA"] = user_data
    # Load bundled .env so config.py picks up Qdrant keys etc.
    _env_path = os.path.join(bundle_dir, ".env")
    if os.path.exists(_env_path):
        from dotenv import load_dotenv
        load_dotenv(_env_path, override=False)

_USER_DATA = os.environ.get("TAXIQ_USER_DATA", "")


def _crash_log(error: Exception) -> None:
    """Write crash details to a log file for debugging."""
    if not _USER_DATA:
        return
    try:
        log_path = os.path.join(_USER_DATA, "logs", "crash.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n{'='*60}\n")
            f.write(f"Crash at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Python: {sys.version}\n")
            f.write(f"Frozen: {getattr(sys, 'frozen', False)}\n")
            if hasattr(sys, '_MEIPASS'):
                f.write(f"Bundle: {sys._MEIPASS}\n")  # type: ignore[attr-defined]
            f.write(f"\n{traceback.format_exc()}\n")
    except Exception:
        pass  # Can't even write the crash log — nothing we can do


# ── Main startup ──────────────────────────────────────────────────────────────
def main() -> None:
    # Import after path is set up
    from backend.config import APP_HOST, APP_PORT  # noqa: E402
    from backend.main import app  # noqa: E402

    # ── Start FastAPI in background thread ────────────────────────────────
    def _run_server() -> None:
        import uvicorn
        uvicorn.run(app, host=APP_HOST, port=APP_PORT, log_level="warning")

    server = threading.Thread(target=_run_server, daemon=True)
    server.start()

    # Give uvicorn time to bind the port
    url = f"http://{APP_HOST}:{APP_PORT}"
    ready = False
    for _ in range(30):
        time.sleep(0.3)
        try:
            import httpx
            httpx.get(f"{url}/api/health", timeout=1)
            ready = True
            break
        except Exception:
            pass

    if not ready:
        print(f"Warning: Server did not respond in time at {url}", flush=True)

    # ── Open UI ───────────────────────────────────────────────────────────
    try:
        import webview  # type: ignore[import]
        webview.create_window(
            "TaxIQ — Income Tax Law Assistant",
            url,
            width=1400,
            height=900,
            resizable=True,
            min_size=(1024, 640),
        )
        webview.start()
    except Exception:
        # pywebview not available or failed — open default browser instead
        webbrowser.open(url)
        # Keep process alive until user closes the terminal / tray
        print(f"TaxIQ running at {url}  (close this window to stop)")
        try:
            while True:
                time.sleep(60)
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        _crash_log(e)
        # Show error to user on Windows
        if sys.platform == "win32":
            import ctypes
            msg = (
                f"TaxIQ failed to start.\n\n"
                f"Error: {e}\n\n"
                f"Check the crash log at:\n"
                f"{os.path.join(_USER_DATA, 'logs', 'crash.log') if _USER_DATA else '(unknown)'}"
            )
            ctypes.windll.user32.MessageBoxW(0, msg, "TaxIQ — Startup Error", 0x10)
        raise
