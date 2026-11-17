"""Arreglos de la revisión ECC y Claude-Red (2026-11-15)."""

import sqlite3
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from battery_sam import cli
from battery_sam.adb import BadReadingError
from battery_sam.config import Settings
from battery_sam.device import _to_int, parse_battery
from battery_sam.health import VERY_LOW_LABEL, calculate_health
from battery_sam.renovation import analyze_renovation_risk, mask_serial
from battery_sam.storage import now
from battery_sam.web import create_app
from tests.fakes import DUMPSYS_S24, S24_ULTRA, FakeShell
from tests.test_health import snap

STOPPED = DUMPSYS_S24.replace(
    "Current Battery Service state:\n",
    "Current Battery Service state:\n  (UPDATES STOPPED -- use 'reset' to restart)\n",
)


@pytest.fixture
def client(service):
    return TestClient(create_app(Settings(), service), base_url="http://127.0.0.1:5000")


# --- Lectura del teléfono ---


@pytest.mark.parametrize("value", ["--5", "²", "1.5", "", "abc"])
def test_to_int_rejects_non_ascii_integers(value):
    assert _to_int(value) is None


def test_empty_dumpsys_is_an_error_not_zeros():
    with pytest.raises(BadReadingError, match="dumpsys battery vacío"):
        parse_battery({**S24_ULTRA, "dumpsys": ""})


def test_updates_stopped_marks_reading_as_overridden(store):
    reading = calculate_health(
        parse_battery({**S24_ULTRA, "dumpsys": STOPPED}), "S24 Ultra", 5000
    )
    assert reading.overridden and reading.health_pct is None
    assert "dumpsys battery set" in reading.discarded_reason
    assert not store.save_if_due(reading)


# --- Salud muy baja ---


def test_very_low_health_is_shown_but_not_saved(store):
    # 45 % de 5000 mAh: antes se descartaba como «valor imposible»
    reading = calculate_health(
        snap(charge_counter=1_800_000, level=80), "S24 Ultra", 5000
    )
    assert reading.health_pct == 45.0
    assert reading.needs_check and reading.health_label == VERY_LOW_LABEL
    assert not store.save_if_due(reading)


def test_below_twenty_percent_is_still_discarded():
    reading = calculate_health(
        snap(charge_counter=600_000, level=80), "S24 Ultra", 5000
    )
    assert reading.health_pct is None


def test_clock_going_back_counts_as_due(store, monkeypatch):
    reading = calculate_health(snap(), "S24 Ultra", 5000)
    future = now() + timedelta(hours=2)
    monkeypatch.setattr("battery_sam.storage.now", lambda: future)
    assert store.save_if_due(reading)
    monkeypatch.setattr("battery_sam.storage.now", lambda: future - timedelta(hours=1))
    assert store.save_if_due(reading)


# --- ¿Es reacondicionado? ---


def test_nothing_readable_is_not_low_risk():
    r = analyze_renovation_risk({"warranty_bit": None, "knox_fuse": None}, None)
    assert r["risk_level"] == "Sin datos suficientes"
    assert any(u.startswith("Fusible Knox") for u in r["unverified"])
    assert any(u.startswith("Salud") for u in r["unverified"])


def test_very_worn_battery_raises_risk():
    r = analyze_renovation_risk({"warranty_bit": "0", "knox_fuse": None}, 45.0)
    assert r["risk_level"] == "Medio"


def test_overridden_values_are_a_risk_factor():
    r = analyze_renovation_risk({"warranty_bit": "0"}, None, overridden=True)
    assert any("dumpsys battery set" in f for f in r["risk_factors"])


def test_serial_is_masked():
    assert mask_serial("R5CX12345678") == "•••• 5678"
    assert mask_serial(None) is None


def test_api_never_returns_full_serial(client):
    body = client.get("/api/renovation").json()
    assert "serial" not in body
    assert body["serial_masked"] == "•••• 5678"
    assert "R5CX12345678" not in client.get("/api/renovation").text


def test_renovation_validates_model_before_adb(client, shell):
    assert client.get("/api/renovation", params={"model": "Nokia"}).status_code == 404
    assert shell.calls == 0


# --- Servidor local: DNS rebinding, CSRF, cabeceras ---


def test_foreign_host_is_rejected(service):
    evil = TestClient(
        create_app(Settings(), service), base_url="http://evil.example:5000"
    )
    assert evil.get("/api/renovation").status_code == 400


def test_extra_allowed_host(service):
    app = create_app(Settings(allowed_hosts=("192.168.1.50",)), service)
    assert TestClient(app, base_url="http://192.168.1.50:5000").get(
        "/api/models"
    ).status_code == 200


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_cross_site_api_requests_are_blocked(client, shell, site):
    r = client.get("/api/current", headers={"Sec-Fetch-Site": site})
    assert r.status_code == 403 and r.json()["error"]["code"] == "cross_site"
    assert shell.calls == 0


@pytest.mark.parametrize("site", ["same-origin", "none"])
def test_same_origin_api_requests_pass(client, site):
    assert client.get(
        "/api/models", headers={"Sec-Fetch-Site": site}
    ).status_code == 200


def test_security_headers(client):
    r = client.get("/")
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"


def test_docs_are_disabled(client):
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404


# --- Errores de la base de datos ---


def test_db_error_message_hides_details(client, store, monkeypatch):
    def broken(*a, **k):
        raise sqlite3.DatabaseError("file is not a database: /home/x/secret.db")

    monkeypatch.setattr(store, "stats", broken)
    r = client.get("/api/stats")
    assert r.status_code == 503
    assert "secret.db" not in r.text


def test_save_failure_keeps_the_reading(client, store, monkeypatch):
    def broken(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(store, "save_if_due", broken)
    body = client.get("/api/current").json()
    assert body["health_pct"] == 99.6
    assert body["saved"] is False and body["save_error"]


# --- Configuración y CLI ---


@pytest.mark.parametrize(
    "var,value",
    [
        ("BATTERY_SAM_PORT", "0"),
        ("BATTERY_SAM_ADB_TIMEOUT", "0"),
        ("BATTERY_SAM_SAVE_INTERVAL", "-1"),
        ("BATTERY_SAM_REFRESH_MS", "10"),
    ],
)
def test_invalid_settings_exit(monkeypatch, var, value):
    monkeypatch.setenv(var, value)
    with pytest.raises(SystemExit):
        Settings.from_env()


def test_cli_escapes_phone_text(monkeypatch, tmp_path, capsys):
    phone = FakeShell(
        {**S24_ULTRA, "build_fingerprint": "lineage/[/bold]x[link=http://e.vil]y"}
    )
    monkeypatch.setenv("BATTERY_SAM_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "AdbClient", lambda **_: phone)
    assert cli.main(["--renovado"]) == 0
    assert "[/bold]x" in capsys.readouterr().out


def test_cli_model_is_case_insensitive(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("BATTERY_SAM_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "AdbClient", lambda **_: FakeShell())
    assert cli.main(["--modelo", "s24 ultra"]) == 0


def test_own_code_is_revalidated(client):
    assert client.get("/static/js/api.js").headers["cache-control"] == "no-cache"
    assert client.get("/static/style.css").headers["cache-control"] == "no-cache"
    assert client.get("/").headers["cache-control"] == "no-cache"
    r = client.get(
        "/static/js/api.js",
        headers={"If-None-Match": client.get("/static/js/api.js").headers["etag"]},
    )
    assert r.status_code == 304
