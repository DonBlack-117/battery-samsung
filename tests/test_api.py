import pytest
from fastapi.testclient import TestClient

from battery_sam.adb import AdbTimeoutError, DeviceNotConnectedError
from battery_sam.config import Settings
from battery_sam.web import create_app


@pytest.fixture
def client(service):
    return TestClient(create_app(Settings(), service))


def test_index_renders(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'data-testid="gauge-pct"' in r.text
    assert "googleapis" not in r.text


def test_current_reading(client):
    body = client.get("/api/current", params={"model": "S24 Ultra"}).json()
    assert body["health_pct"] == 99.6
    assert body["saved"] is True
    # La segunda lectura inmediata no se guarda
    assert client.get("/api/current").json()["saved"] is False


def test_unknown_model_is_404(client):
    r = client.get("/api/current", params={"model": "Nokia 3310"})
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "unknown_model"


@pytest.mark.parametrize(
    "error,status,code",
    [
        (DeviceNotConnectedError("sin teléfono"), 503, "no_device"),
        (AdbTimeoutError("lento"), 504, "adb_timeout"),
    ],
)
def test_adb_errors_have_codes(client, shell, error, status, code):
    shell.error = error
    r = client.get("/api/current")
    assert r.status_code == status
    assert r.json() == {"error": {"code": code, "message": str(error)}}


def test_renovation(client):
    body = client.get("/api/renovation").json()
    assert body["risk_level"] == "Bajo"
    assert body["warranty_bit"] == "0"


def test_one_shell_call_per_reading(client, shell):
    client.get("/api/current")
    assert shell.calls == 1


def test_stats_and_history(client):
    client.get("/api/current")
    assert client.get("/api/stats").json()["total_readings"] == 1
    history = client.get("/api/history", params={"days": 7}).json()
    assert history[0]["health_pct"] == 99.6
    assert client.get("/api/history", params={"days": 0}).status_code == 422


def test_csv_export(client):
    client.get("/api/current")
    r = client.get("/api/export.csv")
    assert r.headers["content-type"].startswith("text/csv")
    assert r.text.splitlines()[0].startswith("timestamp,modelo,health_pct")
    assert len(r.text.splitlines()) == 2


def test_device(client):
    assert client.get("/api/device").json()["model"] == "S24 Ultra"


def test_save_false_does_not_store(client):
    assert client.get("/api/current", params={"save": "false"}).json()["saved"] is False
    assert client.get("/api/stats").json()["total_readings"] == 0


def test_renovation_uses_one_shell_call(client, shell):
    client.get("/api/renovation")
    assert shell.calls == 1
