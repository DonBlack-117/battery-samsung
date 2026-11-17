import re
import subprocess

import pytest

from battery_sam.adb import (
    AdbClient,
    AdbError,
    AdbNotFoundError,
    AdbTimeoutError,
    BadReadingError,
    DeviceNotConnectedError,
    DeviceUnauthorizedError,
    parse_sections,
)


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
        (
            "error: no devices/emulators found",
            DeviceNotConnectedError,
            "No se detectó",
        ),
    ],
)
def test_get_state_errors(client, monkeypatch, stderr, error, text):
    monkeypatch.setattr(client, "_run", lambda args: proc(stderr=stderr, rc=1))
    with pytest.raises(error, match=text):
        client.ensure_device()


def test_lost_connection_mid_read(client, monkeypatch):
    def run(args):
        return (
            proc("device\n")
            if args == ["get-state"]
            else proc(stderr="error: closed", rc=1)
        )

    monkeypatch.setattr(client, "_run", run)
    with pytest.raises(DeviceNotConnectedError, match="Se perdió"):
        client.run_sections({"a": "echo 1"})


def fake_shell(outputs):
    """Simula `adb shell`: imprime cada marcador del script y luego la salida dada."""

    def run(args):
        if args == ["get-state"]:
            return proc("device\n")
        marks = re.findall(r"echo '([^']+)'", args[1])
        out = "".join(f"{m}\n{outputs.get(m.rsplit(':', 1)[-1], '')}\n" for m in marks)
        return proc(out)

    return run


def test_sections_round_trip(client, monkeypatch):
    monkeypatch.setattr(client, "_run", fake_shell({"a": "1"}))
    assert client.run_sections({"a": "x", "b": "y"}) == {"a": "1", "b": ""}


def test_marker_changes_on_every_call(client, monkeypatch):
    scripts = []

    def run(args):
        scripts.append(args)
        return fake_shell({})(args)

    monkeypatch.setattr(client, "_run", run)
    client.run_sections({"a": "x"})
    client.run_sections({"a": "x"})
    assert scripts[1][1] != scripts[3][1]


def test_phone_output_cannot_forge_a_section(client, monkeypatch):
    # Un ajuste escrito con `settings put` que imprime el marcador fijo antiguo
    monkeypatch.setattr(client, "_run", fake_shell({"a": "1\n<<<bsam:b\n4950000"}))
    assert client.run_sections({"a": "x", "b": "y"}) == {
        "a": "1\n<<<bsam:b\n4950000",
        "b": "",
    }


def test_repeated_section_is_rejected():
    with pytest.raises(BadReadingError, match="dos veces"):
        parse_sections("<<<bsam:a\n1\n<<<bsam:a\n2\n")


def test_failing_last_command_is_not_a_lost_connection(client, monkeypatch):
    # El script termina en `true`: el código de salida ya no depende del último comando
    monkeypatch.setattr(client, "_run", fake_shell({"a": "1"}))
    assert client.run_sections({"a": "x"}) == {"a": "1"}


@pytest.mark.parametrize(
    "exc,error",
    [
        (FileNotFoundError(), AdbNotFoundError),
        (subprocess.TimeoutExpired("adb", 1), AdbTimeoutError),
        (PermissionError(13, "Permission denied"), AdbError),
    ],
)
def test_run_maps_os_errors(client, monkeypatch, exc, error):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(subprocess, "run", boom)
    with pytest.raises(error):
        client._run(["get-state"])


def test_run_decodes_utf8_without_crashing(client, monkeypatch):
    seen = {}

    def run(*a, **k):
        seen.update(k)
        return proc()

    monkeypatch.setattr(subprocess, "run", run)
    client._run(["get-state"])
    assert seen["encoding"] == "utf-8" and seen["errors"] == "replace"
