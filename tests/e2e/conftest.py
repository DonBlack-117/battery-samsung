"""Levanta la app real con un teléfono falso para las pruebas en navegador."""

import socket
import threading
import time

import pytest
import uvicorn

from battery_sam.config import Settings
from battery_sam.service import BatteryService
from battery_sam.storage import ReadingStore
from battery_sam.web import create_app
from tests.fakes import S24_ULTRA, FakeShell


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def fake_shell():
    return FakeShell()


@pytest.fixture(scope="session")
def server(fake_shell, tmp_path_factory):
    store = ReadingStore(tmp_path_factory.mktemp("db") / "e2e.db", min_interval_s=0)
    store.init()
    app = create_app(Settings(refresh_ms=60_000), BatteryService(fake_shell, store))
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not srv.started:
        if time.time() > deadline:
            raise RuntimeError("El servidor de pruebas no arrancó")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    srv.should_exit = True
    thread.join(timeout=5)


@pytest.fixture(autouse=True)
def reset_phone(fake_shell):
    fake_shell.values = dict(S24_ULTRA)
    fake_shell.error = None
    yield


@pytest.fixture
def app_url(server):
    return server
