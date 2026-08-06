#!/usr/bin/env python3
"""Launch Ledgerit as a lightweight local web app.

No Electron: this starts a stdlib-only HTTP server on loopback, waits for
it to answer, then opens the user's own installed Chrome/Chromium/Edge in
`--app` mode — a dedicated window with no tabs or URL bar, so it reads as
an application rather than a browser tab. If no Chromium-family browser is
found, it falls back to the OS default browser.

Zero new dependencies. Every piece here is Python's standard library. The
target machine has 8 GB total and the model already claims most of it —
bundling a private copy of Chromium the way Electron does (~200-400 MB) is
not affordable here, and launching the browser the user already has costs
us nothing beyond the page itself.

Usage:
    python3 launch.py

The server binds to 127.0.0.1 only (not visible to the rest of the
network), on a port the OS assigns — nothing here is hardcoded to compete
with another process for a fixed port. Closing the app window shuts the
server down; so does Ctrl+C.
"""
from __future__ import annotations

import http.server
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import webbrowser
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import server as ledgerit_server  # noqa: E402 — the real backend: cleaner/analyst/explain wired to /api/*

HOST = "127.0.0.1"


def _free_port() -> int:
    """Ask the OS for an unused port rather than hardcoding one that might
    already be taken — the tiny window between closing this probe socket
    and binding the real server is the standard, accepted way to do this
    without a dependency; the target platform doesn't hand that exact port
    to another process in practice."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def start_server() -> tuple[http.server.ThreadingHTTPServer, int]:
    if not ledgerit_server.WEB_DIR.is_dir():
        raise SystemExit(f"error: {ledgerit_server.WEB_DIR} not found — nothing to serve")
    port = _free_port()
    httpd = ledgerit_server.create_server(HOST, port)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return httpd, port


def wait_until_ready(url: str, timeout: float = 5.0) -> bool:
    """Poll instead of assuming the socket is immediately accepting
    connections — cheap, and it's the literal "wait for it to be ready"
    the launch behaviour is supposed to have."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            urllib.request.urlopen(url, timeout=0.5)
            return True
        except Exception:
            time.sleep(0.05)
    return False


def find_chromium_binary() -> str | None:
    """Look for an installed Chromium-family browser — Chrome, Chromium,
    Edge, Brave all understand --app=. Ledgerit never bundles or downloads
    one; if none of these exist, the caller falls back to the OS default
    browser instead."""
    candidates: list[str] = []

    if sys.platform == "darwin":
        candidates += [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        ]
    elif sys.platform.startswith("win"):
        for env in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
            base = os.environ.get(env)
            if not base:
                continue
            candidates += [
                str(Path(base) / "Google/Chrome/Application/chrome.exe"),
                str(Path(base) / "Microsoft/Edge/Application/msedge.exe"),
                str(Path(base) / "Chromium/Application/chrome.exe"),
                str(Path(base) / "BraveSoftware/Brave-Browser/Application/brave.exe"),
            ]
    else:  # linux and other unix-likes
        for name in ("google-chrome", "google-chrome-stable", "chromium",
                      "chromium-browser", "microsoft-edge", "microsoft-edge-stable",
                      "brave-browser"):
            found = shutil.which(name)
            if found:
                candidates.append(found)

    for path in candidates:
        if Path(path).exists():
            return path
    return None


def main() -> None:
    httpd, port = start_server()
    url = f"http://{HOST}:{port}/"
    print(f"Ledgerit is running at {url}")

    if not wait_until_ready(url):
        print("warning: server did not respond in time — opening anyway")

    # Load the model now, in the background, rather than on the user's first
    # question — otherwise the first real answer pays the model-load cost
    # (tens of seconds) on top of generation time, and reads as broken
    # rather than just slow.
    ledgerit_server.warm_model_in_background()

    browser_path = find_chromium_binary()
    proc = None
    profile_dir = None
    if browser_path:
        # A plain `--app=` launch, with no --user-data-dir, does NOT reliably
        # give us a process to wait on: if that browser is already running
        # elsewhere on the machine (the common case), Chrome's single-instance
        # behaviour hands the window off to the EXISTING process over IPC and
        # the process we just spawned exits in well under a second — found by
        # actually running this, not by inspecting the flags. proc.wait()
        # would then return almost immediately regardless of whether the user
        # still has the window open, breaking "shut down when the window
        # closes" silently. A dedicated --user-data-dir forces a genuinely
        # separate process that isn't subject to that hand-off, so proc.wait()
        # tracks the real window.
        profile_dir = tempfile.mkdtemp(prefix="ledgerit-app-")
        print(f"opening app window ({Path(browser_path).name})…")
        proc = subprocess.Popen([
            browser_path,
            f"--app={url}",
            f"--user-data-dir={profile_dir}",
            "--window-size=760,860",
            "--no-first-run",
        ])
    else:
        print("no Chrome/Chromium/Edge/Brave found — opening your default browser instead")
        webbrowser.open(url)

    try:
        if proc is not None:
            proc.wait()  # blocks until this specific app window's process exits
            print("window closed — shutting down")
        else:
            print("Ledgerit is running in your default browser.")
            print("Closing the tab alone won't stop the server — press Ctrl+C here to stop it.")
            while True:
                time.sleep(1)
    except KeyboardInterrupt:
        print("\nstopping…")
    finally:
        httpd.shutdown()
        httpd.server_close()
        if profile_dir is not None:
            shutil.rmtree(profile_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
