"""Une el teléfono, el cálculo y el historial; lo usan la web y el CLI."""

import logging
import sqlite3
import threading

from .adb import Shell
from .catalog import design_capacity
from .device import DeviceInfo, detect_device, read_battery, read_battery_and_indicators
from .health import HealthReading, calculate_health
from .renovation import analyze_renovation_risk
from .sessions import ChargeSession, SessionStore
from .storage import ReadingStore

log = logging.getLogger(__name__)


class BatteryService:
    def __init__(
        self, shell: Shell, store: ReadingStore, sessions: SessionStore | None = None
    ):
        self.shell = shell
        self.store = store
        if sessions is None:
            # Misma base que el historial; crear la tabla es idempotente
            sessions = SessionStore(store.path)
            sessions.init()
        self.sessions = sessions
        # Comprobar el intervalo y guardar debe ser una sola operación
        self._save_lock = threading.Lock()

    def detect(self) -> DeviceInfo:
        return detect_device(self.shell)

    def current(self, model: str, save: bool = True) -> tuple[
        HealthReading, bool, str | None, ChargeSession | None
    ]:
        """Lee el teléfono. Retorna (lectura, si se guardó, error al guardar, sesión).

        Con `save` también registra la sesión de carga. Un fallo de SQLite no
        tira la lectura, que ya se leyó bien: se devuelve con `saved=False` y
        el motivo.
        """
        design = design_capacity(model)
        reading = calculate_health(read_battery(self.shell), model, design)
        if not save:
            return reading, False, None, None
        try:
            with self._save_lock:
                saved = self.store.save_if_due(reading)
                session = self.sessions.track(reading)
            return reading, saved, None, session
        except sqlite3.Error:
            log.exception("No se pudo guardar la lectura de %s", model)
            return (
                reading,
                False,
                "No se pudo guardar la lectura en el historial.",
                None,
            )

    def stats(self, model: str) -> dict:
        """Resumen del historial; la tendencia sale de las sesiones si ya alcanzan."""
        stats = self.store.stats(model)
        summary = self.sessions.summary(model)
        stats["sessions_with_health"] = summary["total"]
        stats["session_health"] = summary["last_health"]
        stats["trend_source"] = (
            "readings" if stats["monthly_degradation"] is not None else None
        )
        if summary["monthly_degradation"] is not None:
            stats["monthly_degradation"] = summary["monthly_degradation"]
            stats["months_to_80"] = summary["months_to_80"]
            stats["trend_note"] = None
            stats["trend_source"] = "sessions"
        return stats

    def renovation(self, model: str) -> dict:
        design = design_capacity(model)  # antes de hablar con el teléfono
        snapshot, indicators = read_battery_and_indicators(self.shell)
        reading = calculate_health(snapshot, model, design)
        return analyze_renovation_risk(
            indicators, reading.health_pct, reading.overridden
        )
