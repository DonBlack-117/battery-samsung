"""¿Es reacondicionado? Evalúa los indicadores leídos por ADB.

Ningún dato de ADB lo confirma con certeza: el resultado es orientativo.
"""

CYCLE_HIGH = 300
CYCLE_MEDIUM = 150
CYCLE_LOW = 50


def mask_serial(serial: str | None) -> str | None:
    """Solo los últimos 4 caracteres: la API no entrega el número completo."""
    if not serial:
        return None
    return f"•••• {serial[-4:]}"


def analyze_renovation_risk(
    indicators: dict, health_pct: float | None, overridden: bool = False
) -> dict:
    risk_factors: list[str] = []
    green_flags: list[str] = []
    unverified: list[str] = []

    cycles = indicators.get("cycle_count")
    if cycles is None:
        # Android 14+ no deja leerlo en muchos Samsung: no es señal en contra.
        unverified.append(
            "Ciclos de carga: el sistema no deja leer /sys/class/power_supply/battery/cycle_count"
        )
    elif cycles >= CYCLE_HIGH:
        risk_factors.append(
            f"Ciclos de carga muy altos: {cycles} (uso intensivo; {CYCLE_HIGH} o más es señal de alarma)"
        )
    elif cycles >= CYCLE_MEDIUM:
        risk_factors.append(
            f"Ciclos de carga moderados: {cycles} (uso notable antes de esta compra)"
        )
    elif cycles >= CYCLE_LOW:
        green_flags.append(f"Ciclos de carga aceptables: {cycles}")
    else:
        green_flags.append(f"Ciclos de carga muy bajos: {cycles} (prácticamente nuevo)")

    bits = (indicators.get("warranty_bit"), indicators.get("boot_warranty_bit"))
    warranty_voided = "1" in bits
    # El valor crudo que se devuelve es el que explica la bandera
    warranty = (
        "1" if warranty_voided else next((b for b in bits if b is not None), None)
    )
    if warranty_voided:
        risk_factors.append(
            "Warranty bit activado (ro.warranty_bit=1): el teléfono fue desbloqueado, flasheado "
            "con firmware no oficial o reparado con piezas que no son de Samsung. Es irreversible."
        )
    elif warranty == "0":
        green_flags.append("Warranty bit intacto (ro.warranty_bit=0)")
    else:
        unverified.append("Warranty bit: el teléfono no lo reporta")

    knox_fuse = indicators.get("knox_fuse")
    knox_triggered = knox_fuse == "1"
    if knox_triggered:
        risk_factors.append(
            "Fusible Knox de hardware quemado (/efs/FactoryApp/fuse=1): hubo acceso no "
            "autorizado al sistema. Es irreversible."
        )
    elif knox_fuse == "0":
        green_flags.append("Fusible Knox de hardware intacto")
    else:
        unverified.append("Fusible Knox: el sistema no deja leer /efs/FactoryApp/fuse")

    if overridden:
        risk_factors.append(
            "Los valores de la batería están fijados a mano con «dumpsys battery set»: la lectura "
            "no refleja la batería real. Reinicia el teléfono y vuelve a analizar."
        )
    elif health_pct is None:
        unverified.append(
            "Salud de la batería: no se pudo calcular con los datos del teléfono"
        )
    else:
        if health_pct < 80:
            risk_factors.append(
                f"Salud de batería baja ({health_pct} %) para un teléfono que se vende como nuevo o reacondicionado"
            )
        elif health_pct >= 95:
            green_flags.append(f"Salud de batería excelente: {health_pct} %")
        elif health_pct >= 85:
            green_flags.append(f"Salud de batería buena: {health_pct} %")

    fingerprint = indicators.get("build_fingerprint") or ""
    if fingerprint and "samsung" not in fingerprint.lower():
        risk_factors.append(
            f"Fingerprint de build inusual: '{fingerprint}'; puede ser firmware no oficial"
        )

    n = len(risk_factors)
    # «Bajo» con todo ilegible daría una falsa tranquilidad. Heurística propia:
    # hace falta la salud y al menos uno de warranty bit o fusible Knox.
    enough = health_pct is not None and (warranty is not None or knox_fuse is not None)
    if n == 0 and not enough:
        level, color = "Sin datos suficientes", "gray"
    elif n == 0:
        level, color = "Bajo", "green"
    elif n <= 2:
        level, color = "Medio", "yellow"
    else:
        level, color = "Alto", "red"

    return {
        "risk_level": level,
        "risk_color": color,
        "risk_factors": risk_factors,
        "green_flags": green_flags,
        "unverified": unverified,
        "cycle_count": cycles,
        "warranty_voided": warranty_voided,
        "knox_fuse_triggered": knox_triggered,
        # Valores crudos: distinguen «intacto» (0) de «sin acceso» (None)
        "warranty_bit": warranty,
        "knox_fuse": knox_fuse,
        "serial_masked": mask_serial(indicators.get("serial")),
        "build_fingerprint": fingerprint or None,
    }
