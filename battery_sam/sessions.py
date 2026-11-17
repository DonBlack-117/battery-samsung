"""Registro por sesión de carga: una fila por cada carga de 20 % o menos a 100 %.

Solo se abre una sesión si la carga empieza en MAX_START_LEVEL o menos, y solo
cuenta para la comparación si llega a 100 %. De cada mes cuenta una sola: la de
rango más amplio. La tendencia se calcula entre esas cargas de referencia.

La capacidad de la sesión sale de la carga que entró entre el inicio y el fin:
(charge_counter final − inicial) / (nivel final − inicial) × 100. Con un rango
amplio (15 → 100 %) el error de un solo punto pesa mucho menos que en la
estimación de una lectura suelta.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from .health import PLAUSIBLE_MAX, PLAUSIBLE_MIN, HealthReading
from .storage import connect, now, slope_per_day

# Códigos de estado de BatteryManager
STATUS_CHARGING = 2
STATUS_NOT_CHARGING = 4
STATUS_FULL = 5

# La sesión solo se abre si la carga empieza en este nivel o menos (la carga
# mensual es de 15 a 100 %; 20 da margen de unos puntos). Heurística propia.
MAX_START_LEVEL = 20
# Puntos de carga mínimos para calcular la salud de una sesión. Heurística propia.
MIN_SPAN_FOR_HEALTH = 50
# Sin cargar y el nivel bajó esto desde el máximo: la carga terminó antes de llenar.
# Heurística propia (evita cerrar por el parpadeo de un punto).
DROP_TO_CLOSE = 3
# Sin lecturas por más de esto, la sesión abierta se da por perdida. Heurística propia.
MAX_GAP = timedelta(hours=24)

OPEN = "open"
COMPLETE = "complete"
INCOMPLETE = "incomplete"

COLUMNS = [
    "modelo",
    "started_at",
    "updated_at",
    "ended_at",
    "status",
    "end_reason",
    "design_mah",
    "start_level",
    "end_level",
    "start_counter_uah",
    "end_counter_uah",
    "max_temp_c",
    "readings",
]


@dataclass
class ChargeSession:
    id: int | None
    model: str
    started_at: str
    updated_at: str
    ended_at: str | None
    status: str  # open, complete, incomplete
    end_reason: str | None
    design_mah: int
    start_level: int
    end_level: int
    start_counter_uah: int
    end_counter_uah: int
    max_temp_c: float
    readings: int  # lecturas que tocaron la sesión

    @ property
    def span(self) -> int:
        return self.end_level - self.start_level

    @ property
    def added_mah(self) -> int:
        return round((self.end_counter_uah - self.start_counter_uah) / 1000)

    @ property
    def capacity_mah(self) -> int | None:
        if self.span < MIN_SPAN_FOR_HEALTH or self.added_mah <= 0:
            return None
        return round(self.added_mah / self.span * 100)

    @ property
    def health_pct(self) -> float | None:
        cap = self.capacity_mah
        if cap is None or not self.design_mah:
            return None
        pct = round(cap / self.design_mah * 100, 1)
        return pct if PLAUSIBLE_MIN <= pct <= PLAUSIBLE_MAX else None

    @ property
    def duration_min(self) -> int:
        end = datetime.fromisoformat(self.ended_at or self.updated_at)
        return round(
            (end - datetime.fromisoformat(self.started_at)).total_seconds() / 60
        )

    @ property
    def health_note(self) -> str | None:
        if self.health_pct is not None:
            return None
        if self.span < MIN_SPAN_FOR_HEALTH:
            return f"Rango de {self.span} puntos: hacen falta {MIN_SPAN_FOR_HEALTH} o más para calcular la salud."
        return "Los datos de la carga dan un valor imposible; no se calculó la salud."

    @ property
    def month(self) -> str:
        return self.started_at[:7]

    @ property
    def qualifies(self) -> bool:
        """Completa de 20 % o menos a 100 %, con salud válida."""
        return (
            self.status == COMPLETE
            and self.start_level <= MAX_START_LEVEL
            and self.end_level >= 100
            and self.health_pct is not None
        )

    def to_dict(self, counted: bool = False) -> dict:
        data = asdict(self)
        data.update(
            counted=counted,
            span=self.span,
            added_mah=self.added_mah,
            capacity_mah=self.capacity_mah,
            health_pct=self.health_pct,
            health_note=self.health_note,
            duration_min=self.duration_min,
        )
        return data


def _is_finished(r: HealthReading) -> str | None:
    """Motivo de fin si la lectura indica que la carga llegó a su tope."""
    if r.status_code == STATUS_FULL or r.level >= 100:
        return "Llegó a 100 %."
    return None


def _protect_stop(r: HealthReading) -> bool:
    """«Proteger batería» corta en 80-85 % con estado «Sin cargar»."""
    return (
        r.status_code == STATUS_NOT_CHARGING
        and bool(r.protect_battery)
        and r.level >= 79
    )


class SessionStore:
    def __init__(self, path: Path):
        self.path = Path(path)

    def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with connect(self.path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS charge_sessions (
                    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
                    modelo             TEXT    NOT NULL,
                    started_at         TEXT    NOT NULL,
                    updated_at         TEXT    NOT NULL,
                    ended_at           TEXT,
                    status             TEXT    NOT NULL,
                    end_reason         TEXT,
                    design_mah         INTEGER NOT NULL,
                    start_level        INTEGER NOT NULL,
                    end_level          INTEGER NOT NULL,
                    start_counter_uah  INTEGER NOT NULL,
                    end_counter_uah    INTEGER NOT NULL,
                    max_temp_c         REAL    NOT NULL,
                    readings           INTEGER NOT NULL DEFAULT 1
                )
                """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_sessions_model_start "
                "ON charge_sessions (modelo, started_at)"
            )

    @ staticmethod
    def _row(row) -> ChargeSession:
        data = dict(row)
        data["model"] = data.pop("modelo")
        return ChargeSession(**data)

    def open_session(self, model: str) -> ChargeSession | None:
        with connect(self.path) as conn:
            row = conn.execute(
                "SELECT * FROM charge_sessions WHERE modelo = ? AND status = ? " "ORDER BY id DESC LIMIT 1",
                (model, OPEN),
            ).fetchone()
        return self._row(row) if row else None

    def sessions(self, model: str, limit: int = 24) -> list[ChargeSession]:
        with connect(self.path) as conn:
            rows = conn.execute(
                "SELECT * FROM charge_sessions WHERE modelo = ? ORDER BY id DESC LIMIT ?",
                (model, limit),
            ).fetchall()
        return [self._row(r) for r in rows]

    def _insert(self, s: ChargeSession) -> ChargeSession:
        values = asdict(s)
        values["modelo"] = values.pop("model")
        with connect(self.path) as conn:
            cur = conn.execute(
                f"INSERT INTO charge_sessions ({', '.join(COLUMNS)}) " f"VALUES ({', '.join('?' * len(COLUMNS))})",
                [values[c] for c in COLUMNS],
            )
        s.id = cur.lastrowid
        return s

    def _update(self, s: ChargeSession) -> ChargeSession:
        values = asdict(s)
        values["modelo"] = values.pop("model")
        cols = [c for c in COLUMNS if c != "modelo"]
        with connect(self.path) as conn:
            conn.execute(
                f"UPDATE charge_sessions SET {', '.join(f'{c} = ?' for c in cols)} WHERE id = ?",
                [values[c] for c in cols] + [s.id],
            )
        return s

    def track(
        self, r: HealthReading, at: datetime | None = None
    ) -> ChargeSession | None:
        """Abre, actualiza o cierra la sesión del modelo con una lectura.

        Retorna la sesión tocada (abierta o recién cerrada), o None si no hay
        carga en curso. Hay que llamarla con un candado si hay varios hilos.
        """
        if r.overridden:
            return None  # valores fijados a mano: no son la carga real
        t = at or now()
        stamp = t.isoformat()
        current = self.open_session(r.model)

        if current and t - datetime.fromisoformat(current.updated_at) > MAX_GAP:
            current.status = INCOMPLETE
            current.ended_at = current.updated_at
            current.end_reason = "Sin lecturas por más de 24 h."
            self._update(current)
            current = None

        finished = _is_finished(r)
        if current is None:
            if (
                r.status_code != STATUS_CHARGING
                or finished
                or r.level > MAX_START_LEVEL
            ):
                return None
            return self._insert(
                ChargeSession(
                    id=None,
                    model=r.model,
                    started_at=stamp,
                    updated_at=stamp,
                    ended_at=None,
                    status=OPEN,
                    end_reason=None,
                    design_mah=r.design_mah,
                    start_level=r.level,
                    end_level=r.level,
                    start_counter_uah=r.charge_counter_uah,
                    end_counter_uah=r.charge_counter_uah,
                    max_temp_c=r.temp_c,
                    readings=1,
                )
            )

        current.readings += 1
        current.max_temp_c = max(current.max_temp_c, r.temp_c)
        charging = r.status_code == STATUS_CHARGING

        if (
            not charging
            and not finished
            and r.level <= current.end_level - DROP_TO_CLOSE
        ):
            # Se desconectó antes de llenar: el fin es el máximo visto, no esta lectura
            current.status = INCOMPLETE
            current.ended_at = current.updated_at
            current.end_reason = f"Se dejó de cargar en {current.end_level} %."
            return self._update(current)

        current.updated_at = stamp
        # El fin de la sesión es el nivel más alto (con su contador)
        if r.level >= current.end_level:
            current.end_level = r.level
            current.end_counter_uah = r.charge_counter_uah
        if finished:
            current.status = COMPLETE
            current.ended_at = stamp
            current.end_reason = finished
        elif _protect_stop(r):
            current.status = INCOMPLETE
            current.ended_at = stamp
            current.end_reason = (
                f"Se detuvo en {r.level} % por «Proteger batería»; "
                "desactívala para llegar a 100 %."
            )
        return self._update(current)

    def reference_sessions(self, model: str) -> list[ChargeSession]:
        """Una carga de referencia por mes (la de rango más amplio), de la más vieja a la más nueva."""
        best: dict[str, ChargeSession] = {}
        # De la más vieja a la más nueva: con el mismo rango gana la más reciente
        for s in reversed(self.sessions(model, limit=1000)):
            if not s.qualifies:
                continue
            kept = best.get(s.month)
            if kept is None or s.span >= kept.span:
                best[s.month] = s
        return [best[m] for m in sorted(best)]

    def summary(self, model: str) -> dict:
        """Salud de la última carga de referencia y tendencia entre ellas."""
        refs = self.reference_sessions(model)
        result = {
            "total": len(refs),
            "last_health": refs[-1].health_pct if refs else None,
            "monthly_degradation": None,
            "months_to_80": None,
            "counted_ids": [s.id for s in refs],
        }
        # La pendiente pide al menos 2 fechas separadas por 7 días o más (storage.py)
        points = [(s.started_at[: 10], s.health_pct) for s in refs]
        slope = slope_per_day(points)
        if slope is None:
            return result
        monthly = -slope * 30
        result["monthly_degradation"] = round(monthly, 3)
        current = points[-1][1]
        if monthly > 0 and current > 80:
            result["months_to_80"] = round((current - 80) / monthly, 1)
        return result
