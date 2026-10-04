"""Cálculo de la salud de la batería a partir de una lectura cruda."""

from dataclasses import asdict, dataclass

from .catalog import HEALTH_NAMES, STATUS_NAMES, health_label
from .device import BatterySnapshot

# Fuera de este rango la lectura es un error de medición, no la salud real.
PLAUSIBLE_MIN = 50.0
PLAUSIBLE_MAX = 101.0

# Con poca carga, charge_counter / nivel tiene demasiado error.
MIN_LEVEL_FOR_ESTIMATE = 20
MIN_COUNTER_UAH = 100_000

METHOD_SYSFS = "sysfs"
METHOD_ESTIMATE = "estimate"


@dataclass
class HealthReading:
    model: str
    design_mah: int
    health_pct: float | None
    health_label: str
    health_color: str
    method: str | None  # "sysfs", "estimate" o None
    method_detail: str | None
    capacity_mah: int | None  # capacidad total actual (calculada)
    discarded_reason: str | None  # por qué no hay salud, si no la hay
    level: int
    charge_mah: int  # carga que tiene ahora
    charge_counter_uah: int
    voltage_mv: int
    temp_c: float
    health_code: int
    health_name: str
    status_code: int
    status_name: str
    protect_battery: bool | None
    protect_note: str | None

    def to_dict(self) -> dict:
        return asdict(self)


def to_mah(value: int) -> float:
    """El kernel suele dar µAh; valores pequeños ya vienen en mAh."""
    return value / 1000 if value >= 100_000 else float(value)


def _plausible(pct: float) -> bool:
    return PLAUSIBLE_MIN <= pct <= PLAUSIBLE_MAX


def _from_sysfs(snap: BatterySnapshot, design_mah: int) -> tuple[float, int, str] | None:
    if not snap.charge_full:
        return None
    full_mah = to_mah(snap.charge_full)
    # Primero contra el diseño que reporta el kernel; si las unidades no
    # cuadran (pasó en un S25 Ultra: 1000 %), contra la ficha del modelo.
    candidates = []
    if snap.charge_full_design:
        candidates.append(to_mah(snap.charge_full_design))
    candidates.append(float(design_mah))
    for design in candidates:
        pct = round(full_mah / design * 100, 1)
        if _plausible(pct):
            return pct, round(full_mah), f"charge_full={snap.charge_full}"
    return None


def _from_counter(snap: BatterySnapshot, design_mah: int) -> tuple[float, int, str] | None:
    if snap.charge_counter < MIN_COUNTER_UAH or snap.level < MIN_LEVEL_FOR_ESTIMATE:
        return None
    full_mah = snap.charge_counter / snap.level * 100 / 1000
    pct = round(full_mah / design_mah * 100, 1)
    if not _plausible(pct):
        return None
    return pct, round(full_mah), f"charge_counter={snap.charge_counter} µAh, nivel={snap.level} %"


def _protect_note(snap: BatterySnapshot) -> str | None:
    if snap.protect_battery is False:
        return None
    stopped = snap.status_code in (4, 5)
    near_cap = 79 <= snap.level <= 85
    if snap.protect_battery:
        if stopped and near_cap:
            return f"La carga se detuvo en {snap.level} % por «Proteger batería». Es normal."
        return "«Proteger batería» está activa: la carga se limita a 80–85 %."
    # Sin acceso al ajuste: se deduce por el comportamiento
    if stopped and near_cap:
        return f"La carga se detuvo en {snap.level} %: parece que «Proteger batería» está activa."
    return None


def calculate_health(snap: BatterySnapshot, model: str, design_mah: int) -> HealthReading:
    result = _from_sysfs(snap, design_mah)
    method = METHOD_SYSFS if result else None
    if result is None:
        result = _from_counter(snap, design_mah)
        method = METHOD_ESTIMATE if result else None

    discarded = None
    if result is None:
        if snap.level < MIN_LEVEL_FOR_ESTIMATE:
            discarded = f"Carga en {snap.level} %: con menos de {MIN_LEVEL_FOR_ESTIMATE} % la estimación no es fiable."
        else:
            discarded = "Los datos del teléfono dan un valor imposible; se descartó la lectura."
        health_pct, capacity_mah, detail = None, None, None
        label, color = "Sin datos", "gray"
    else:
        health_pct, capacity_mah, detail = result
        label, color = health_label(health_pct)

    return HealthReading(
        model=model,
        design_mah=design_mah,
        health_pct=health_pct,
        health_label=label,
        health_color=color,
        method=method,
        method_detail=detail,
        capacity_mah=capacity_mah,
        discarded_reason=discarded,
        level=snap.level,
        charge_mah=round(snap.charge_counter / 1000),
        charge_counter_uah=snap.charge_counter,
        voltage_mv=snap.voltage_mv,
        temp_c=round(snap.temperature_raw / 10, 1),
        health_code=snap.health_code,
        health_name=HEALTH_NAMES.get(snap.health_code, str(snap.health_code)),
        status_code=snap.status_code,
        status_name=STATUS_NAMES.get(snap.status_code, str(snap.status_code)),
        protect_battery=snap.protect_battery,
        protect_note=_protect_note(snap),
    )
