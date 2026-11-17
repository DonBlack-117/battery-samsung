from datetime import datetime, timedelta, timezone

import pytest

from battery_sam.health import calculate_health
from battery_sam.sessions import COMPLETE, INCOMPLETE, OPEN, SessionStore
from battery_sam.storage import now
from tests.test_health import snap

DESIGN = 5000
CHARGING, DISCHARGING, NOT_CHARGING, FULL = 2, 3, 4, 5


def reading(
    level,
    status=CHARGING,
    mah_per_pct=48.0,
    temp=31.0,
    protect=False,
    model="S24 Ultra",
):
    # charge_counter proporcional al nivel: 48 mAh por punto = 4800 mAh (96 %)
    counter = round(level * mah_per_pct * 1000)
    s = snap(
        level=level,
        status_code=status,
        charge_counter=counter,
        temperature_raw=round(temp * 10),
        protect_battery=protect,
    )
    return calculate_health(s, model, DESIGN)


@pytest.fixture
def sessions(tmp_path):
    s = SessionStore(tmp_path / "s.db")
    s.init()
    return s


def charge(sessions, levels, start=None, step=timedelta(minutes=10), **kw):
    t = start or now()
    last = None
    for level in levels:
        last = sessions.track(reading(level, **kw), at=t) or last
        t += step
    return last


def test_full_charge_15_to_100(sessions):
    s = charge(sessions, [15, 40, 70, 99])
    assert s.status == OPEN
    s = sessions.track(reading(100, status=FULL))
    assert s.status == COMPLETE
    assert (s.start_level, s.end_level, s.span) == (15, 100, 85)
    assert s.added_mah == 4080
    assert s.capacity_mah == 4800
    assert s.health_pct == 96.0
    assert s.end_reason == "Llegó a 100 %."
    assert sessions.open_session("S24 Ultra") is None


def test_no_session_when_not_charging(sessions):
    assert sessions.track(reading(50, status=DISCHARGING)) is None
    assert sessions.sessions("S24 Ultra") == []


def test_unplugged_early_closes_with_last_max(sessions):
    charge(sessions, [15, 40, 60])
    s = sessions.track(reading(56, status=DISCHARGING))
    assert s.status == INCOMPLETE
    assert s.end_level == 60
    assert s.health_pct is None
    assert "50" in s.health_note


def test_unplugged_before_100_does_not_count(sessions):
    charge(sessions, [15, 50, 80])
    s = sessions.track(reading(76, status=DISCHARGING))
    assert s.status == INCOMPLETE
    assert s.health_pct == 96.0  # se muestra, pero no entra a la comparación
    assert not s.qualifies
    assert sessions.summary("S24 Ultra")["total"] == 0


def test_no_session_above_20(sessions):
    assert sessions.track(reading(21)) is None
    assert sessions.track(reading(60)) is None
    assert sessions.track(reading(20)).status == OPEN


def test_reconnect_at_full_after_wall_charger(sessions):
    # Se lee al 15 % por USB, se carga en la pared y se vuelve a conectar al 100 %
    t = now()
    sessions.track(reading(15), at=t)
    s = sessions.track(reading(100, status=FULL), at=t + timedelta(hours=2))
    assert s.status == COMPLETE and s.health_pct == 96.0


def test_protect_battery_stop_closes(sessions):
    charge(sessions, [15, 50])
    s = sessions.track(reading(85, status=NOT_CHARGING, protect=True))
    assert s.status == INCOMPLETE
    assert "Proteger batería" in s.end_reason
    assert not s.qualifies


def test_long_gap_abandons_open_session(sessions):
    t = now()
    sessions.track(reading(15), at=t)
    s = sessions.track(reading(18), at=t + timedelta(hours=30))
    # La vieja quedó incompleta y se abrió otra
    assert s.status == OPEN and s.start_level == 18
    old = sessions.sessions("S24 Ultra")[1]
    assert old.status == INCOMPLETE


def test_overridden_reading_is_ignored(sessions):
    r = reading(20)
    r.overridden = True
    assert sessions.track(r) is None


def full_charge(sessions, start, mah_per_pct=48.0, levels=(15, 60)):
    charge(sessions, list(levels), start=start, mah_per_pct=mah_per_pct)
    return sessions.track(
        reading(100, status=FULL, mah_per_pct=mah_per_pct),
        at=start + timedelta(hours=2),
    )


JAN = datetime(2026, 1, 10, 9, 0, tzinfo=timezone(timedelta(hours=-6)))


def test_one_reference_per_month_widest_range(sessions):
    narrow = full_charge(sessions, JAN, levels=(20, 60))
    wide = full_charge(
        sessions, JAN + timedelta(days=5), mah_per_pct=47.0, levels=(12, 60)
    )
    summary = sessions.summary("S24 Ultra")
    assert summary["counted_ids"] == [wide.id]
    assert narrow.id not in summary["counted_ids"]
    assert summary["last_health"] == 94.0


def test_monthly_trend_from_sessions(sessions):
    t = JAN
    for i, mah in enumerate((48.0, 47.5, 47.0)):
        start = t + timedelta(days=30 * i)
        charge(sessions, [15, 60], start=start, mah_per_pct=mah)
        sessions.track(
            reading(100, status=FULL, mah_per_pct=mah), at=start + timedelta(hours=2)
        )
    summary = sessions.summary("S24 Ultra")
    assert summary["total"] == 3
    assert summary["last_health"] == 94.0
    assert summary["monthly_degradation"] == pytest.approx(1.0, abs=0.01)
    assert summary["months_to_80"] == pytest.approx(14.0, abs=0.1)


def test_service_tracks_only_when_saving(service, shell):
    shell.values["dumpsys"] = (
        shell.values["dumpsys"].replace("status: 4", "status: 2").replace(
            "level: 80", "level: 15"
        )
    )
    _, _, _, session = service.current("S24 Ultra", save=False)
    assert session is None
    _, _, _, session = service.current("S24 Ultra", save=True)
    assert session.status == OPEN and session.start_level == 15
