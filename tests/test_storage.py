import sqlite3
from datetime import timedelta

from battery_sam.health import calculate_health
from battery_sam.storage import now
from tests.test_health import snap


def reading(pct_counter=3_984_800, level=80, model="S24 Ultra"):
    return calculate_health(snap(charge_counter=pct_counter, level=level), model, 5000)


def test_save_respects_interval(store):
    assert store.save_if_due(reading())
    assert not store.save_if_due(reading())
    assert store.stats("S24 Ultra")["total_readings"] == 1


def test_reading_without_health_is_not_saved(store):
    assert not store.save_if_due(reading(level=10))


def test_history_is_per_model(store):
    store.save(reading())
    store.save(reading(model="S25 Ultra"))
    assert len(store.readings("S24 Ultra")) == 1


def test_trend_needs_enough_days(store):
    store.save(reading())
    s = store.stats("S24 Ultra")
    assert s["monthly_degradation"] is None
    assert "al menos 2 días" in s["trend_note"]


def test_trend_uses_daily_averages(store):
    start = now() - timedelta(days=60)
    # 100 % → 98 % en 60 días, con ruido dentro de cada día
    for day, counter in [(0, 4_000_000), (30, 3_960_000), (60, 3_920_000)]:
        for noise in (-8000, 8000):
            store.save(reading(pct_counter=counter + noise), at=start + timedelta(days=day))
    s = store.stats("S24 Ultra")
    assert s["days_with_data"] == 3
    assert abs(s["monthly_degradation"] - 1.0) < 0.05
    assert s["months_to_80"] is not None


def test_old_naive_timestamps_get_timezone(tmp_path):
    from battery_sam.storage import ReadingStore

    db = tmp_path / "old.db"
    store = ReadingStore(db)
    store.init()
    with sqlite3.connect(db) as conn:
        conn.execute(
            "INSERT INTO readings (timestamp, modelo, health_pct) VALUES ('2026-03-17T01:42:06.353081', 'S24 Ultra', 99.0)"
        )
    store.init()
    with sqlite3.connect(db) as conn:
        ts = conn.execute("SELECT timestamp FROM readings").fetchone()[0]
    assert len(ts) == 32 and ts.startswith("2026-03-17T01:42:06")
