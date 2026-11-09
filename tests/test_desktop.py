"""Desktop launcher: build staleness, port fallback, server lifecycle, shortcuts (no window needed)."""
import os
import socket
import subprocess
import sys

import httpx
import pytest
from fastapi import FastAPI

from fbb import desktop


def touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x")
    os.utime(path, (mtime, mtime))


@pytest.fixture
def web(tmp_path):
    touch(tmp_path / "package.json", 100)
    touch(tmp_path / "package-lock.json", 100)
    touch(tmp_path / "src" / "main.tsx", 100)
    touch(tmp_path / "dist" / "index.html", 200)
    touch(tmp_path / "node_modules" / ".package-lock.json", 200)
    return tmp_path


def test_fresh_build_needs_nothing(web):
    assert not desktop.needs_build(web)
    assert not desktop.needs_install(web)


def test_missing_dist_needs_build(web):
    (web / "dist" / "index.html").unlink()
    assert desktop.needs_build(web)


@pytest.mark.parametrize("changed", ["src/features/x/Page.tsx", "public/favicon.svg", "vite.config.ts"])
def test_changed_source_needs_build(web, changed):
    touch(web / changed, 300)
    assert desktop.needs_build(web)


def test_unrelated_file_does_not_trigger_build(web):
    touch(web / "README.md", 300)
    touch(web / "node_modules" / "pkg" / "index.js", 300)
    assert not desktop.needs_build(web)


def test_install_needed_when_missing_or_lockfile_newer(web):
    touch(web / "package-lock.json", 300)
    assert desktop.needs_install(web)
    (web / "node_modules" / ".package-lock.json").unlink()
    assert desktop.needs_install(web)


def test_build_without_npm_explains(web, monkeypatch):
    monkeypatch.setattr(desktop.shutil, "which", lambda _name: None)
    with pytest.raises(desktop.BuildError, match="Node.js"):
        desktop.build_web_client(web)


def test_build_runs_install_then_build_and_reports_failure(web, monkeypatch):
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd[1:])
        return subprocess.CompletedProcess(cmd, 1 if cmd[1] == "run" else 0, stdout="", stderr="TS2322: bad type")

    touch(web / "package-lock.json", 300)
    monkeypatch.setattr(desktop.shutil, "which", lambda _name: "npm")
    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    with pytest.raises(desktop.BuildError, match="TS2322"):
        desktop.build_web_client(web)
    assert calls == [["ci", "--no-audit", "--no-fund"], ["run", "build"]]


def test_busy_port_falls_back_to_a_free_one():
    held = desktop.bind_local_socket(0)
    busy = held.getsockname()[1]
    try:
        sock = desktop.bind_local_socket(busy)
        try:
            assert sock.getsockname()[1] not in (busy, 0)
        finally:
            sock.close()
    finally:
        held.close()


def test_server_serves_until_stopped():
    app = FastAPI()
    app.get("/ping")(lambda: {"ok": True})
    with socket.socket() as probe:  # pick a port that is free right now
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = desktop.DesktopServer(lambda: app, port=port)
    url = server.start()
    try:
        assert url == f"http://127.0.0.1:{port}/"
        assert httpx.get(url + "ping").json() == {"ok": True}
    finally:
        server.stop()
        server.join()
    assert server.stopping
    with pytest.raises(httpx.ConnectError):
        httpx.get(url + "ping")


def test_server_not_started_after_window_closed():
    server = desktop.DesktopServer(FastAPI)
    server.stop()
    with pytest.raises(RuntimeError, match="Shutting down"):
        server.start()


def test_pages_escape_messages():
    assert "&lt;script&gt;" in desktop.status_page("<script>")
    page = desktop.error_page("ESPN_LEAGUE_ID is not set <b>")
    assert "ESPN_LEAGUE_ID is not set &lt;b&gt;" in page


@pytest.mark.skipif(sys.platform != "win32", reason="shortcuts are Windows-only")
def test_install_shortcuts_passes_paths_via_env(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, env, **kwargs):
        seen.update(cmd=cmd, env=env)
        return subprocess.CompletedProcess(cmd, 0, stdout="C:\\Users\\me\\Desktop\\Fantasy HQ.lnk\r\n", stderr="")

    (tmp_path / "pythonw.exe").write_text("")
    monkeypatch.setattr(desktop.sys, "executable", str(tmp_path / "python.exe"))
    monkeypatch.setattr(desktop.subprocess, "run", fake_run)
    assert desktop.install_shortcuts() == ["C:\\Users\\me\\Desktop\\Fantasy HQ.lnk"]
    assert seen["cmd"][0] == "powershell.exe"
    assert seen["env"]["FBB_LNK_TARGET"] == str(tmp_path / "pythonw.exe")
    assert seen["env"]["FBB_LNK_ICON"] == str(desktop.ICON)
    assert seen["env"]["FBB_LNK_ACTION"] == "install"
    assert desktop.ICON.is_file()


@pytest.mark.skipif(sys.platform != "win32", reason="single-instance mutex is Windows-only")
def test_single_instance_waits_for_first_copy_to_exit():
    import threading

    name = f"Local\fbb-test-{os.getpid()}"
    checked, released, results = threading.Event(), threading.Event(), []

    def second_copy():  # mutex ownership is per thread, so the second copy needs its own
        with desktop.SingleInstance(name) as second:
            results.append(second.acquired)
            results.append(second.wait(0.05))
            checked.set()
            released.wait(5)
            results.append(second.wait(5))

    with desktop.SingleInstance(name) as first:
        assert first.acquired
        thread = threading.Thread(target=second_copy)
        thread.start()
        assert checked.wait(5)
    released.set()
    thread.join(5)
    assert results == [False, False, True]
