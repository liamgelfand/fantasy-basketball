"""Desktop app: Fantasy HQ in its own window (pywebview on Edge WebView2) instead of a browser tab.

The desktop shortcut runs `pythonw -m fbb desktop`, so there is no console. Everything is logged to
.fbb/logs/desktop.log instead. One copy runs at a time: launching again brings the open window to
the front. The web client is rebuilt when its sources changed, and closing the window stops the server.
"""
from __future__ import annotations

import ctypes
import html
import logging
import os
import shutil
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import ROOT

APP_NAME = "Fantasy HQ"
ICON = Path(__file__).resolve().parent / "assets" / "fantasy-hq.ico"
WEB_DIR = ROOT / "web"
DATA_DIR = ROOT / ".fbb"
LOG_FILE = DATA_DIR / "logs" / "desktop.log"
# Cookies and localStorage (saved chat, color scheme) persist here between launches.
WEBVIEW_DIR = DATA_DIR / "webview"
# Fixed so the page origin (and with it localStorage) stays the same between launches.
# Not 8000, so `fbb serve` can run alongside the desktop app.
PREFERRED_PORT = 8765
MUTEX_NAME = "Local\\fbb-fantasy-hq-desktop"
# Files that feed `npm run build`, besides everything under src/ and public/.
WEB_BUILD_FILES = ("index.html", "package.json", "package-lock.json", "vite.config.ts", "postcss.config.cjs",
                   "tsconfig.json", "tsconfig.app.json", "tsconfig.node.json")
BUILD_TIMEOUT = 600

log = logging.getLogger("fbb.desktop")


class BuildError(RuntimeError):
    pass


# --- web client build -------------------------------------------------------------------------

def _build_inputs(web: Path) -> Iterator[Path]:
    for name in WEB_BUILD_FILES:
        if (web / name).is_file():
            yield web / name
    for folder in ("src", "public"):
        if (web / folder).is_dir():
            yield from (p for p in (web / folder).rglob("*") if p.is_file())


def needs_build(web: Path) -> bool:
    """True when web/dist is missing or older than any of its sources (Vite rewrites
    dist/index.html on every build, so its mtime is the build time)."""
    built = web / "dist" / "index.html"
    if not built.is_file():
        return True
    built_at = built.stat().st_mtime
    return any(p.stat().st_mtime > built_at for p in _build_inputs(web))


def needs_install(web: Path) -> bool:
    """True when node_modules is missing or older than package-lock.json. npm writes
    node_modules/.package-lock.json at the end of every install."""
    installed = web / "node_modules" / ".package-lock.json"
    lock = web / "package-lock.json"
    if not installed.is_file():
        return True
    return lock.is_file() and lock.stat().st_mtime > installed.stat().st_mtime


def _run_npm(npm: str, args: list[str], web: Path) -> None:
    log.info("Running npm %s", " ".join(args))
    # No console window flashes up from pythonw, and output goes to the log rather than nowhere.
    flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    try:
        result = subprocess.run([npm, *args], cwd=web, capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=BUILD_TIMEOUT, creationflags=flags)
    except subprocess.TimeoutExpired as exc:
        raise BuildError(f"npm {' '.join(args)} took longer than {BUILD_TIMEOUT // 60} minutes.") from exc
    output = (result.stdout + result.stderr).strip()
    if output:
        log.info("npm output:\n%s", output)
    if result.returncode != 0:
        tail = "\n".join(output.splitlines()[-15:])
        raise BuildError(f"npm {' '.join(args)} failed (exit {result.returncode}).\n\n{tail}")


def build_web_client(web: Path, on_status: Callable[[str], None] = lambda _msg: None) -> None:
    npm = shutil.which("npm")
    if not npm:
        raise BuildError("Node.js (npm) wasn't found on PATH. Install Node.js 20+ from nodejs.org, then reopen the app.")
    if needs_install(web):
        on_status("Installing web dependencies (first run only, about a minute)...")
        _run_npm(npm, ["ci", "--no-audit", "--no-fund"], web)
    on_status("Building the latest version of the app...")
    _run_npm(npm, ["run", "build"], web)


# --- server -----------------------------------------------------------------------------------

def bind_local_socket(port: int) -> socket.socket:
    """Listen on 127.0.0.1:port, or a free port if that one's taken. The socket is handed to uvicorn,
    so the port can't be grabbed by something else between checking it and serving on it."""
    def bind(p: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no other process may share the port
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            sock.bind(("127.0.0.1", p))
        except OSError:
            sock.close()
            raise
        return sock

    try:
        return bind(port)
    except OSError:
        log.warning("Port %d is in use; using a free port (saved chats in this window won't carry over)", port)
        return bind(0)


class DesktopServer:
    """Uvicorn on a background thread, started on demand and stopped when the window closes."""

    def __init__(self, app_factory: Callable[[], object] | None = None, port: int = PREFERRED_PORT):
        self._app_factory = app_factory
        self._port = port
        self._server = None
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()

    def start(self, timeout: float = 30) -> str:
        import uvicorn

        if self._app_factory is None:
            from .api.app import create_app
            self._app_factory = create_app
        app = self._app_factory()  # raises on a bad .env, before anything is listening
        sock = bind_local_socket(self._port)
        port = sock.getsockname()[1]
        # log_config=None: uvicorn logs through the root logger into the desktop log file.
        config = uvicorn.Config(app, log_config=None, timeout_graceful_shutdown=2)
        self._server = uvicorn.Server(config)
        if self._stopping.is_set():  # window closed while we were getting ready
            sock.close()
            raise RuntimeError("Shutting down")
        self._thread = threading.Thread(target=self._server.run, kwargs={"sockets": [sock]}, name="fbb-server",
                                        daemon=True)
        self._thread.start()
        deadline = time.monotonic() + timeout
        while not self._server.started:
            if not self._thread.is_alive():
                raise RuntimeError(f"The server stopped while starting. Details are in {LOG_FILE}.")
            if time.monotonic() > deadline:
                raise RuntimeError(f"The server didn't start within {timeout:.0f}s. Details are in {LOG_FILE}.")
            time.sleep(0.05)
        url = f"http://127.0.0.1:{port}/"
        log.info("Serving on %s", url)
        return url

    @property
    def stopping(self) -> bool:
        return self._stopping.is_set()

    def stop(self) -> None:
        self._stopping.set()
        if self._server is not None:
            self._server.should_exit = True

    def join(self, timeout: float = 10) -> None:
        if self._thread is not None:
            self._thread.join(timeout)


# --- Windows integration ----------------------------------------------------------------------

class SingleInstance:
    """Named mutex owned for the life of the app (until its server has fully stopped). `acquired` is
    False when another copy owns it. Elsewhere than Windows it always acquires (the shortcut and
    single-instance logic are Windows-only)."""

    def __init__(self, name: str = MUTEX_NAME):
        self.name = name
        self.acquired = True
        self._handle = None
        self._kernel32 = None

    def __enter__(self) -> SingleInstance:
        if sys.platform == "win32":
            from ctypes import wintypes

            k = self._kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
            k.CreateMutexW.restype = wintypes.HANDLE
            k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            k.WaitForSingleObject.restype = wintypes.DWORD
            k.ReleaseMutex.argtypes = k.CloseHandle.argtypes = [wintypes.HANDLE]
            self._handle = k.CreateMutexW(None, True, self.name)
            if not self._handle:
                raise ctypes.WinError(ctypes.get_last_error())
            self.acquired = ctypes.get_last_error() != 183  # ERROR_ALREADY_EXISTS: not granted ownership
        return self

    def wait(self, timeout: float) -> bool:
        """Wait for the other copy to exit and take over. True once acquired."""
        if not self.acquired and self._handle:
            result = self._kernel32.WaitForSingleObject(self._handle, int(timeout * 1000))
            self.acquired = result in (0, 0x80)  # WAIT_OBJECT_0, WAIT_ABANDONED (it crashed)
        return self.acquired

    def __exit__(self, *_exc) -> None:
        if self._handle:
            if self.acquired:
                self._kernel32.ReleaseMutex(self._handle)
            self._kernel32.CloseHandle(self._handle)
            self._handle = None


def focus_existing_window(title: str = APP_NAME) -> bool:
    """Restore and bring the running app's window to the front. Only matches WinForms windows
    (what pywebview creates), so an Explorer window on a folder named "Fantasy HQ" isn't picked."""
    if sys.platform != "win32":
        return False
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def visit(hwnd, _lparam):
        text = ctypes.create_unicode_buffer(256)
        cls = ctypes.create_unicode_buffer(256)
        user32.GetWindowTextW(hwnd, text, 256)
        user32.GetClassNameW(hwnd, cls, 256)
        if text.value == title and cls.value.startswith("WindowsForms"):
            found.append(hwnd)
            return False
        return True

    user32.EnumWindows(visit, 0)
    if not found:
        return False
    hwnd = found[0]
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    return True


_SHORTCUT_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject WScript.Shell
foreach ($folder in 'Desktop', 'Programs') {
    $path = Join-Path ([Environment]::GetFolderPath($folder)) ($env:FBB_LNK_NAME + '.lnk')
    if ($env:FBB_LNK_ACTION -eq 'remove') {
        if (Test-Path -LiteralPath $path) { Remove-Item -LiteralPath $path; Write-Output $path }
        continue
    }
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $env:FBB_LNK_TARGET
    $lnk.Arguments = '-m fbb desktop'
    $lnk.WorkingDirectory = $env:FBB_LNK_DIR
    $lnk.IconLocation = $env:FBB_LNK_ICON + ',0'
    $lnk.Description = 'ESPN fantasy basketball analyst'
    $lnk.Save()
    Write-Output $path
}
"""


def _shortcuts(action: str) -> list[str]:
    """Create or remove the Desktop and Start menu shortcuts. Paths travel as environment
    variables, not spliced into the script, so spaces or quotes in them can't break it."""
    if sys.platform != "win32":
        raise SystemExit("Shortcuts are only supported on Windows.")
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    if action == "install" and not pythonw.is_file():
        raise SystemExit(f"{pythonw} not found. Run this with the project's venv Python (.venv\\Scripts\\python).")
    env = os.environ | {"FBB_LNK_ACTION": action, "FBB_LNK_NAME": APP_NAME, "FBB_LNK_TARGET": str(pythonw),
                        "FBB_LNK_DIR": str(ROOT), "FBB_LNK_ICON": str(ICON)}
    result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _SHORTCUT_SCRIPT],
                            env=env, capture_output=True, text=True)
    if result.returncode != 0:
        raise SystemExit(f"Couldn't {action} shortcuts:\n{result.stderr.strip()}")
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def install_shortcuts() -> list[str]:
    return _shortcuts("install")


def remove_shortcuts() -> list[str]:
    return _shortcuts("remove")


# --- window -----------------------------------------------------------------------------------

def windows_prefers_dark() -> bool:
    """The Windows app theme, so the window doesn't flash white before the page paints in dark mode."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


_PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>{app}</title><style>
:root {{ color-scheme: light dark; --bg: #fff; --fg: #1f1f1f; --muted: #6b6b6b; --accent: #f76707; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg: #1a1b1e; --fg: #e9ecef; --muted: #a6a7ab; }} }}
body {{ margin: 0; height: 100vh; display: grid; place-items: center; background: var(--bg); color: var(--fg);
       font: 15px/1.5 "Segoe UI", system-ui, sans-serif; }}
main {{ max-width: 640px; padding: 24px; text-align: center; }}
h1 {{ font-size: 22px; margin: 16px 0 4px; }}
p {{ color: var(--muted); margin: 4px 0; }}
pre {{ text-align: left; white-space: pre-wrap; background: rgba(127,127,127,.12); padding: 12px; border-radius: 8px;
      font-size: 12px; max-height: 40vh; overflow: auto; }}
.spinner {{ width: 32px; height: 32px; margin: auto; border-radius: 50%; border: 3px solid rgba(127,127,127,.25);
           border-top-color: var(--accent); animation: spin .8s linear infinite; }}
@keyframes spin {{ to {{ transform: rotate(360deg); }} }}
</style></head><body><main>{body}</main></body></html>"""


def status_page(message: str) -> str:
    return _PAGE.format(app=APP_NAME, body=f'<div class="spinner"></div><h1>{APP_NAME}</h1>'
                                            f'<p>{html.escape(message)}</p>')


def error_page(message: str) -> str:
    return _PAGE.format(app=APP_NAME, body=f"<h1>{APP_NAME} couldn't start</h1><pre>{html.escape(message)}</pre>"
                                            f"<p>Full details: {html.escape(str(LOG_FILE))}</p>"
                                            "<p>Fix the problem, then close this window and open the app again.</p>")


def _boot(window, server: DesktopServer) -> None:
    """Runs on pywebview's worker thread once the window is up: build if needed, start the
    server, then point the window at it."""
    def status(message: str) -> None:
        log.info(message)
        # load_html, not evaluate_js: evaluate_js waits up to 20s for pywebview's JS bridge on a fresh window.
        window.load_html(status_page(message))

    try:
        if needs_build(WEB_DIR):
            try:
                build_web_client(WEB_DIR, status)
            except BuildError:
                if not (WEB_DIR / "dist" / "index.html").is_file():
                    raise
                log.exception("Build failed; opening the previous build")
        status("Starting...")
        window.load_url(server.start())
    except (Exception, SystemExit) as exc:  # load_config raises SystemExit for a missing .env value
        if server.stopping:
            return  # the window was closed mid-startup; nothing to show
        log.exception("Startup failed")
        window.load_html(error_page(str(exc) or type(exc).__name__))


def _setup_logging() -> None:
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # pythonw has no console: stray print()s would otherwise go to None and crash.
    if sys.stdout is None or sys.stderr is None:
        stream = open(LOG_FILE.with_name("desktop-output.log"), "a", encoding="utf-8", buffering=1)  # noqa: SIM115
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    sys.excepthook = lambda *exc: log.critical("Unhandled error", exc_info=exc)
    threading.excepthook = lambda args: log.critical("Unhandled error in thread %s", args.thread,
                                                     exc_info=(args.exc_type, args.exc_value, args.exc_traceback))


def run() -> None:
    _setup_logging()
    with SingleInstance() as instance:
        if not instance.acquired:
            if focus_existing_window():
                log.info("Already running; focused the open window")
                return
            # No window: the previous copy was just closed and is still stopping its server.
            log.info("Waiting for the previous copy to finish closing")
            if not instance.wait(15):
                log.warning("The previous copy is still running without a window; giving up")
                return
        import webview

        log.info("Starting %s", APP_NAME)
        server = DesktopServer()
        window = webview.create_window(APP_NAME, html=status_page("Starting..."), width=1440, height=900,
                                       min_size=(960, 640), text_select=True,
                                       background_color="#1a1b1e" if windows_prefers_dark() else "#ffffff")
        window.events.closed += server.stop
        webview.start(_boot, (window, server), private_mode=False, storage_path=str(WEBVIEW_DIR), icon=str(ICON))
        server.stop()
        server.join()
        log.info("Closed")
