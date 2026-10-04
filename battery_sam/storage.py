"""Historial de lecturas en SQLite."""

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path

from .health import HealthReading

COLUMNS = [
    "timestamp",
    "modelo",
    "health_pct",
    "level",
    "voltage_mv",
    "temp_c",
    "charge_counter",
    "current_mah",
    "full_mah_est",
    "method",
]

# Para hablar de degradación hacen falta lecturas en días distintos y separados.
MIN_DAYS_FOR_TREND = 2
MIN_SPAN_DAYS = 7


def now() -> datetime:
    return datetime.now().astimezone()


class ReadingStore:
    def __init__(self, path: Path, min_interval_s: int = 600):
        self.path = Path(path)
        self.min_interval_s = min_interval_s

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            # WAL: leer el historial no bloquea al que guarda
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp       TEXT    NOT NULL,
                    modelo          TEXT    NOT NULL,
                    health_pct      REAL,
                    level           INTEGER,
                    voltage_mv      INTEGER,
                    temp_c          REAL,
                    charge_counter  INTEGER,
                    current_mah     INTEGER,
                    full_mah_est    REAL,
                    method          TEXT
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_model_ts ON readings (modelo, timestamp)"
            )
            self._add_timezone(conn)

    @staticmethod
    def _add_timezone(conn: sqlite3.Connection) -> None:
        """Las lecturas viejas se guardaron sin zona horaria (hora local)."""
        rows = conn.execute(
            "SELECT id, timestamp FROM readings "
            "WHERE timestamp NOT GLOB '*[+-][0-9][0-9]:[0-9][0-9]' AND timestamp NOT LIKE '%Z'"
        ).fetchall()
        for row in rows:
            aware = datetime.fromisoformat(row["timestamp"]).astimezone()
            conn.execute(
                "UPDATE readings SET timestamp = ? WHERE id = ?", (aware.isoformat(), row["id"])
            )

    def last_timestamp(self, model: str) -> datetime | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT timestamp AS ts FROM readings WHERE modelo = ? "
                "ORDER BY julianday(timestamp) DESC LIMIT 1",
                (model,),
            ).fetchone()
        return datetime.fromisoformat(row["ts"]) if row and row["ts"] else None

    def save_if_due(self, reading: HealthReading) -> bool:
        """Guarda la lectura si tiene salud y pasó el intervalo mínimo."""
        if reading.health_pct is None:
            return False
        last = self.last_timestamp(reading.model)
        if last and (now() - last).total_seconds() < self.min_interval_s:
            return False
        self.save(reading)
        return True

    def save(self, reading: HealthReading, at: datetime | None = None) -> None:
        with self._connect() as conn:
            conn.execute(
                f"INSERT INTO readings ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                (
                    (at or now()).isoformat(),
                    reading.model,
                    reading.health_pct,
                    reading.level,
                    reading.voltage_mv,
                    reading.temp_c,
                    reading.charge_counter_uah,
                    reading.charge_mah,
                    reading.capacity_mah,
                    reading.method,
                ),
            )

    def readings(self, model: str, days: int = 30) -> list[dict]:
        since = (now() - timedelta(days=days)).isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM readings WHERE modelo = ? AND julianday(timestamp) > julianday(?) "
                "ORDER BY julianday(timestamp)",
                (model, since),
            ).fetchall()
        return [dict(r) for r in rows]

    def daily_health(self, model: str) -> list[tuple[str, float]]:
        """Promedio de salud por día: suaviza el ruido de cada lectura."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT substr(timestamp, 1, 10) AS day, AVG(health_pct) AS health "
                "FROM readings WHERE modelo = ? AND health_pct IS NOT NULL "
                "GROUP BY day ORDER BY day",
                (model,),
            ).fetchall()
        return [(r["day"], r["health"]) for r in rows]

    def stats(self, model: str) -> dict:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS total, MAX(temp_c) AS max_temp, "
                "(SELECT timestamp FROM readings WHERE modelo = :m "
                " ORDER BY julianday(timestamp) LIMIT 1) AS first_ts "
                "FROM readings WHERE modelo = :m",
                {"m": model},
            ).fetchone()

        result = {
            "model": model,
            "total_readings": row["total"],
            "first_date": None,
            "first_health": None,
            "last_health": None,
            "max_temp_c": round(row["max_temp"], 1) if row["max_temp"] is not None else None,
            "days_with_data": 0,
            "monthly_degradation": None,
            "months_to_80": None,
            "trend_note": None,
        }
        if not row["total"]:
            result["trend_note"] = "Todavía no hay lecturas de este modelo."
            return result

        daily = self.daily_health(model)
        result["first_date"] = datetime.fromisoformat(row["first_ts"]).strftime("%d/%m/%Y")
        result["days_with_data"] = len(daily)
        if daily:
            result["first_health"] = round(daily[0][1], 1)
            result["last_health"] = round(daily[-1][1], 1)

        slope = _slope_per_day(daily)
        if slope is None:
            result["trend_note"] = (
                f"Hacen falta lecturas en al menos {MIN_DAYS_FOR_TREND} días "
                f"separados por {MIN_SPAN_DAYS} o más."
            )
            return result

        monthly = -slope * 30  # positivo = la salud baja
        result["monthly_degradation"] = round(monthly, 3)
        current = result["last_health"]
        if monthly > 0 and current > 80:
            result["months_to_80"] = round((current - 80) / monthly, 1)
        return result


def _slope_per_day(daily: list[tuple[str, float]]) -> float | None:
    """Pendiente por mínimos cuadrados de la salud diaria (puntos % por día)."""
    if len(daily) < MIN_DAYS_FOR_TREND:
        return None
    first = datetime.fromisoformat(daily[0][0])
    xs = [(datetime.fromisoformat(d) - first).days for d, _ in daily]
    if xs[-1] < MIN_SPAN_DAYS:
        return None
    ys = [h for _, h in daily]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    denom = sum((x - mean_x) ** 2 for x in xs)
    return sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
