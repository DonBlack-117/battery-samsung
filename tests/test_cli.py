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
