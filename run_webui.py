#!/usr/bin/env python3
"""
One-click launcher for YTSage Web UI.

Usage:
    python run_webui.py                  # Start backend + check frontend
    python run_webui.py --build-frontend # Build Vue frontend before starting
    python run_webui.py --host 0.0.0.0 --port 8765

The FastAPI backend can serve both API and the built Vue frontend from
webui/client/dist/. For development, run Vite dev server separately:
    cd webui/client && npm run dev   # on port 5173
Then this script auto-proxies /api and /ws to the backend.
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
CLIENT_DIR = ROOT / "webui" / "client"
DIST_DIR = CLIENT_DIR / "dist"


def check_backend_deps() -> bool:
    """Check if FastAPI deps are installed."""
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
        return True
    except ImportError:
        return False


def install_backend_deps() -> None:
    """Install Web UI Python dependencies."""
    req_file = ROOT / "webui" / "requirements.txt"
    print(f"[WebUI] Installing backend deps from {req_file} ...")
    subprocess.check_call(
        [sys.executable, "-m", "pip", "install", "-r", str(req_file)]
    )


def build_frontend() -> bool:
    """Build Vue frontend. Returns True on success."""
    if not (CLIENT_DIR / "package.json").exists():
        print("[WebUI] No package.json found, skipping frontend build.")
        return False

    npm_lock = CLIENT_DIR / "package-lock.json"
    if not npm_lock.exists() and not (CLIENT_DIR / "node_modules").exists():
        print("[WebUI] Installing npm dependencies ...")
        r = subprocess.run(["npm", "install"], cwd=str(CLIENT_DIR))
        if r.returncode != 0:
            print("[WebUI] npm install failed.")
            return False

    print("[WebUI] Building frontend ...")
    r = subprocess.run(["npm", "run", "build"], cwd=str(CLIENT_DIR))
    if r.returncode != 0:
        print("[WebUI] Frontend build failed.")
        return False
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="YTSage Web UI launcher")
    parser.add_argument("--host", default=os.environ.get("YTSAGE_WEBUI_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("YTSAGE_WEBUI_PORT", "8765")))
    parser.add_argument("--build-frontend", action="store_true", help="Build Vue frontend before starting")
    parser.add_argument("--dev", action="store_true", help="Dev mode: start only backend (use npm run dev separately)")
    args = parser.parse_args()

    # 1. Ensure backend deps
    if not check_backend_deps():
        print("[WebUI] Backend dependencies missing.")
        try:
            install_backend_deps()
        except subprocess.CalledProcessError:
            print("[WebUI] Failed to install dependencies. Please run: pip install -r webui/requirements.txt")
            sys.exit(1)

    # 2. Optional: build frontend
    if args.build_frontend:
        if not build_frontend():
            print("[WebUI] Frontend build skipped or failed. API still works at /api/*")

    if not args.dev and not DIST_DIR.exists():
        print("\n[WebUI] Frontend not built. You have two options:")
        print("  1) Run: python run_webui.py --build-frontend")
        print("  2) Dev mode: cd webui/client && npm run dev  (then this script)")
        print("   → API is still accessible at http://localhost:{}/api/*".format(args.port))
        print()

    # 3. Start server
    os.environ["YTSAGE_WEBUI_HOST"] = args.host
    os.environ["YTSAGE_WEBUI_PORT"] = str(args.port)

    from webui.server import main as server_main
    print(f"[WebUI] Starting server on http://{args.host}:{args.port}")
    print(f"[WebUI] Default password: ytsage")
    print("[WebUI] Press Ctrl+C to stop.\n")
    server_main()


if __name__ == "__main__":
    main()
