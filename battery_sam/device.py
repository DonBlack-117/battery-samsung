"""Lectura del teléfono: batería, modelo e indicadores de reacondicionado."""

import re
from dataclasses import dataclass

from .adb import Shell
from .catalog import DEVICE_CODE_MAP, SAMSUNG_CAPACITIES

_PS = "/sys/class/power_supply/battery"

BATTERY_SECTIONS = {
    "charge_full": f"cat {_PS}/charge_full",
    "charge_full_design": f"cat {_PS}/charge_full_design",
    "batt_capacity_max": f"cat {_PS}/batt_capacity_max",
    "fg_capacity": f"cat {_PS}/fg_capacity",
    "dumpsys": "dumpsys battery",
    # Ajuste «Proteger batería» de One UI (1 = activo)
    "protect_battery": "settings get global protect_battery",
}

DEVICE_SECTIONS = {
    "brand": "getprop ro.product.brand",
    "manufacturer": "getprop ro.product.manufacturer",
    "model": "getprop ro.product.model",
    "marketname": "getprop ro.product.marketname",
}

RENOVATION_SECTIONS = {
    "cycle_count": f"cat {_PS}/cycle_count",
    "warranty_bit": "getprop ro.warranty_bit",
    "boot_warranty_bit": "getprop ro.boot.warranty_bit",
    "knox_fuse": "cat /efs/FactoryApp/fuse",
    "serial": "getprop ro.serialno",
    "boot_serial": "getprop ro.boot.serialno",
    "build_fingerprint": "getprop ro.build.fingerprint",
}


@dataclass(frozen=True)
class BatterySnapshot:
    """Datos crudos del teléfono, sin interpretar."""

    charge_full: int | None  # µAh, según el kernel
    charge_full_design: int | None
    level: int
    charge_counter: int  # µAh
    voltage_mv: int
    temperature_raw: int  # décimas de °C
    health_code: int
    status_code: int
    protect_battery: bool | None  # None si el ajuste no se pudo leer


@dataclass(frozen=True)
class DeviceInfo:
    model: str | None  # clave de SAMSUNG_CAPACITIES o None
    brand: str | None
    raw_model: str | None
    is_samsung: bool


def _to_int(value: str | None, default: int | None = None) -> int | None:
    if value is None:
        return default
    value = value.strip()
    if value.lstrip("-").isdigit():
        return int(value)
    return default


def parse_dumpsys_battery(text: str) -> dict[str, str]:
    """Campos `clave: valor` de `dumpsys battery`, con la clave en minúsculas."""
    data: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if ":" in line and not line.startswith("02-") and "ACTION_BATTERY" not in line:
            key, _, val = line.partition(":")
            data[key.strip().lower()] = val.strip()
    return data


def read_battery(shell: Shell) -> BatterySnapshot:
    return parse_battery(shell.run_sections(BATTERY_SECTIONS))


def parse_battery(raw: dict[str, str]) -> BatterySnapshot:
    batt = parse_dumpsys_battery(raw.get("dumpsys", ""))

    charge_full = (
        _to_int(raw.get("charge_full"))
        or _to_int(raw.get("batt_capacity_max"))
        or _to_int(raw.get("fg_capacity"))
    )
    protect = raw.get("protect_battery", "").strip()

    return BatterySnapshot(
        charge_full=charge_full,
        charge_full_design=_to_int(raw.get("charge_full_design")),
        level=_to_int(batt.get("level"), 0),
        charge_counter=_to_int(batt.get("charge counter"), 0),
        voltage_mv=_to_int(batt.get("voltage"), 0),
        temperature_raw=_to_int(batt.get("temperature"), 0),
        health_code=_to_int(batt.get("health"), 1),
        status_code=_to_int(batt.get("status"), 1),
        protect_battery={"1": True, "0": False}.get(protect),
    )


def match_model(marketname: str | None, model_code: str | None) -> str | None:
    if marketname:
        name = re.sub(r"^(Samsung\s+)?Galaxy\s+", "", marketname.strip(), flags=re.IGNORECASE)
        if name in SAMSUNG_CAPACITIES:
            return name
    if model_code:
        return DEVICE_CODE_MAP.get(model_code.strip()[:7].upper())
    return None


def detect_device(shell: Shell) -> DeviceInfo:
    raw = shell.run_sections(DEVICE_SECTIONS)
    brand = raw.get("brand") or raw.get("manufacturer") or None
    raw_model = raw.get("model") or None
    is_samsung = bool(brand and "samsung" in brand.lower())
    return DeviceInfo(
        model=match_model(raw.get("marketname"), raw_model) if is_samsung else None,
        brand=brand.title() if brand else None,
        raw_model=raw_model,
        is_samsung=is_samsung,
    )


def read_battery_and_indicators(shell: Shell) -> tuple[BatterySnapshot, dict]:
    """Batería e indicadores de reacondicionado en una sola llamada a adb."""
    raw = shell.run_sections({**BATTERY_SECTIONS, **RENOVATION_SECTIONS})
    return parse_battery(raw), parse_indicators(raw)


def parse_indicators(raw: dict[str, str]) -> dict:
    return {
        "cycle_count": _to_int(raw.get("cycle_count")),
        "warranty_bit": raw.get("warranty_bit") or None,
        "boot_warranty_bit": raw.get("boot_warranty_bit") or None,
        "knox_fuse": raw.get("knox_fuse") or None,
        "serial": raw.get("serial") or raw.get("boot_serial") or None,
        "build_fingerprint": raw.get("build_fingerprint") or None,
    }
