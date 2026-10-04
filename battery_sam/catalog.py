"""Datos fijos: capacidades de fábrica, códigos de modelo y etiquetas."""

DEFAULT_MODEL = "S24 Ultra"

# Capacidad de fábrica por modelo (mAh)
SAMSUNG_CAPACITIES: dict[str, int] = {
    # Serie S25
    "S25 Ultra": 5000,
    "S25+": 4900,
    "S25": 4000,
    # Serie S24
    "S24 Ultra": 5000,
    "S24+": 4900,
    "S24": 4000,
    # Serie S23
    "S23 Ultra": 5000,
    "S23+": 4700,
    "S23": 3900,
    # Serie S22
    "S22 Ultra": 5000,
    "S22+": 4500,
    "S22": 3700,
    # Serie S21
    "S21 Ultra": 5000,
    "S21+": 4800,
    "S21": 4000,
    # Serie S20
    "S20 Ultra": 5000,
    "S20+": 4500,
    "S20": 4000,
    # Note
    "Note 20 Ultra": 4500,
    "Note 20": 4300,
    # Serie A (alta gama)
    "A73": 5000,
    "A55": 5000,
    "A54": 5000,
    "A53": 5000,
    # Serie A (gama media)
    "A35": 5000,
    "A34": 5000,
    "A33": 5000,
    "A25": 5000,
    # Serie A (gama baja)
    "A15": 5000,
    "A14": 5000,
    "A13": 5000,
    "A05s": 5000,
    "A05": 5000,
}

# Primeros 7 caracteres de ro.product.model (ej. "SM-A057F") → modelo
DEVICE_CODE_MAP: dict[str, str] = {
    "SM-S938": "S25 Ultra",
    "SM-S936": "S25+",
    "SM-S931": "S25",
    "SM-S928": "S24 Ultra",
    "SM-S926": "S24+",
    "SM-S921": "S24",
    "SM-S918": "S23 Ultra",
    "SM-S916": "S23+",
    "SM-S911": "S23",
    "SM-S908": "S22 Ultra",
    "SM-S906": "S22+",
    "SM-S901": "S22",
    "SM-G998": "S21 Ultra",
    "SM-G996": "S21+",
    "SM-G991": "S21",
    "SM-G988": "S20 Ultra",
    "SM-G986": "S20+",
    "SM-G981": "S20",
    "SM-N986": "Note 20 Ultra",
    "SM-N981": "Note 20",
    "SM-A736": "A73",
    "SM-A556": "A55",
    "SM-A546": "A54",
    "SM-A536": "A53",
    "SM-A356": "A35",
    "SM-A346": "A34",
    "SM-A336": "A33",
    "SM-A256": "A25",
    "SM-A156": "A15",
    "SM-A155": "A15",
    "SM-A146": "A14",
    "SM-A135": "A13",
    "SM-A057": "A05s",
    "SM-A055": "A05",
}

# (umbral mínimo, etiqueta, color)
HEALTH_LABELS: list[tuple[float, str, str]] = [
    (90, "Excelente", "green"),
    (80, "Muy bueno", "green"),
    (70, "Bueno", "yellow"),
    (60, "Regular — considera revisarla", "yellow"),
    (0, "Deficiente — considera reemplazarla", "red"),
]

# Códigos de BatteryManager.BATTERY_HEALTH_*
HEALTH_NAMES: dict[int, str] = {
    1: "Desconocido",
    2: "Bueno",
    3: "Sobrecalentamiento",
    4: "Muerta",
    5: "Sobrevoltaje",
    6: "Fallo",
    7: "Fría",
}

# Códigos de BatteryManager.BATTERY_STATUS_*
STATUS_NAMES: dict[int, str] = {
    1: "Desconocido",
    2: "Cargando",
    3: "Descargando",
    4: "Sin cargar (llena)",
    5: "Completa",
}


class UnknownModelError(ValueError):
    """El modelo pedido no está en SAMSUNG_CAPACITIES."""


def design_capacity(model: str) -> int:
    try:
        return SAMSUNG_CAPACITIES[model]
    except KeyError:
        raise UnknownModelError(f"Modelo no reconocido: {model!r}") from None


def health_label(pct: float) -> tuple[str, str]:
    """Retorna (etiqueta, color) según el porcentaje de salud."""
    for threshold, label, color in HEALTH_LABELS:
        if pct >= threshold:
            return label, color
    return HEALTH_LABELS[-1][1], HEALTH_LABELS[-1][2]
