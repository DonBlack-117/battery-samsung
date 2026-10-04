import subprocess

import pytest

from battery_sam.adb import AdbClient, DeviceNotConnectedError, DeviceUnauthorizedError


def proc(stdout="", stderr="", rc=0):
    return subprocess.CompletedProcess([], rc, stdout, stderr)


@pytest.fixture
def client():
    return AdbClient(adb_path="adb")


def test_get_state_after_daemon_start(client, monkeypatch):
    out = "* daemon not running; starting now at tcp:5037\n* daemon started successfully\ndevice\n"
    monkeypatch.setattr(client, "_run", lambda args: proc(out))
    client.ensure_device()


@pytest.mark.parametrize(
    "stderr,error,text",
    [
        ("error: device unauthorized.", DeviceUnauthorizedError, "Permitir"),
        ("error: more than one device/emulator", DeviceNotConnectedError, "más de un"),
        ("error: device offline", DeviceNotConnectedError, "offline"),
        ("error: no devices/emulators found", DeviceNotConnectedError, "No se detectó"),
    ],
)
def test_get_state_errors(client, monkeypatch, stderr, error, text):
    monkeypatch.setattr(client, "_run", lambda args: proc(stderr=stderr, rc=1))
    with pytest.raises(error, match=text):
        client.ensure_device()


def test_lost_connection_mid_read(client, monkeypatch):
    def run(args):
        return proc("device\n") if args == ["get-state"] else proc(stderr="error: closed", rc=1)

    monkeypatch.setattr(client, "_run", run)
    with pytest.raises(DeviceNotConnectedError, match="Se perdió"):
        client.run_sections({"a": "echo 1"})


def test_sections_round_trip(client, monkeypatch):
    def run(args):
        return proc("device\n") if args == ["get-state"] else proc("<<<bsam:a\n1\n<<<bsam:b\n")

    monkeypatch.setattr(client, "_run", run)
    assert client.run_sections({"a": "x", "b": "y"}) == {"a": "1", "b": ""}
