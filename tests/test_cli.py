import json

import pytest

from battery_sam import cli
from tests.fakes import FakeShell


@pytest.fixture(autouse=True)
def fake_phone(monkeypatch, tmp_path):
    monkeypatch.setenv("BATTERY_SAM_DB", str(tmp_path / "cli.db"))
    monkeypatch.setattr(cli, "AdbClient", lambda **_: FakeShell())


def test_reading_detects_model(capsys):
    assert cli.main([]) == 0
    out = capsys.readouterr().out
    assert "S24 Ultra" in out and "99.6 %" in out


def test_json_output(capsys):
    assert cli.main(["--json"]) == 0
    assert json.loads(capsys.readouterr().out)["health_pct"] == 99.6


def test_renovation_report(capsys):
    assert cli.main(["--renovado"]) == 0
    assert "Bajo" in capsys.readouterr().out


def test_unknown_model(capsys):
    assert cli.main(["-m", "Nokia"]) == 1


def test_unrecognized_model_is_not_assumed(monkeypatch, capsys):
    from tests.fakes import S24_ULTRA

    shell = FakeShell({**S24_ULTRA, "marketname": "", "model": "SM-X999"})
    monkeypatch.setattr(cli, "AdbClient", lambda **_: shell)
    assert cli.main([]) == 1
    assert "--modelo" in capsys.readouterr().out


def test_watch_must_be_positive():
    with pytest.raises(SystemExit):
        cli.parse_args(["--watch", "-1"])


def _dumpsys(level, status):
    from tests.fakes import DUMPSYS_S24

    counter = level * 48_000
    return (
        DUMPSYS_S24.replace("status: 4", f"status: {status}").replace("level: 80", f"level: {level}").replace(
            "harge counter: 3984800", f"harge counter: {counter}"
        )
    )


def test_session_mode_records_until_full(monkeypatch, capsys):
    from tests.fakes import S24_ULTRA

    steps = iter([(15, 2), (60, 2), (100, 5)])

    class ChargingPhone(FakeShell):
        def run_sections(self, sections):
            if "dumpsys" in sections:
                self.values["dumpsys"] = _dumpsys(*next(steps))
            return super().run_sections(sections)

    monkeypatch.setattr(
        cli,
        "AdbClient",
        lambda **_: ChargingPhone({**S24_ULTRA, "protect_battery": "0"}),
    )
    monkeypatch.setattr(cli.time, "sleep", lambda _: None)
    monkeypatch.setattr(cli.console, "clear", lambda: None)
    assert cli.main(["--sesion"]) == 0
    assert "Sesión cerrada" in capsys.readouterr().out

    assert cli.main(["--sesiones", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    session = data["sessions"][0]
    assert (session["start_level"], session["end_level"], session["status"]) == (
        15,
        100,
        "complete",
    )
    assert session["health_pct"] == 96.0


def test_session_mode_needs_charger(capsys):
    assert cli.main(["--sesion"]) == 1
    assert "no está cargando" in capsys.readouterr().out


def test_session_mode_needs_low_start(monkeypatch, capsys):
    from tests.fakes import S24_ULTRA

    shell = FakeShell({**S24_ULTRA, "dumpsys": _dumpsys(60, 2)})
    monkeypatch.setattr(cli, "AdbClient", lambda **_: shell)
    monkeypatch.setattr(cli.console, "clear", lambda: None)
    assert cli.main(["--sesion"]) == 1
    assert "20 % o menos" in capsys.readouterr().out
