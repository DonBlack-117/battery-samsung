"""Une el teléfono, el cálculo y el historial; lo usan la web y el CLI."""

import threading

from .adb import Shell
from .catalog import design_capacity
from .device import DeviceInfo, detect_device, read_battery, read_battery_and_indicators
from .health import HealthReading, calculate_health
from .renovation import analyze_renovation_risk
from .storage import ReadingStore


class BatteryService:
    def __init__(self, shell: Shell, store: ReadingStore):
        self.shell = shell
        self.store = store
        # Comprobar el intervalo y guardar debe ser una sola operación
        self._save_lock = threading.Lock()

    def detect(self) -> DeviceInfo:
        return detect_device(self.shell)

    def current(self, model: str, save: bool = True) -> tuple[HealthReading, bool]:
        """Lee el teléfono. Retorna (lectura, si se guardó en el historial)."""
        design = design_capacity(model)
        reading = calculate_health(read_battery(self.shell), model, design)
        if not save:
            return reading, False
        with self._save_lock:
            return reading, self.store.save_if_due(reading)

    def renovation(self, model: str) -> dict:
        snapshot, indicators = read_battery_and_indicators(self.shell)
        reading = calculate_health(snapshot, model, design_capacity(model))
        return analyze_renovation_risk(indicators, reading.health_pct)
