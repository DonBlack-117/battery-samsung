"""Uso desde la terminal: `python -m battery_sam.cli`."""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime

from rich import box
from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.table import Table

from .adb import AdbClient, AdbError
from .catalog import SAMSUNG_CAPACITIES
from .config import Settings
from .health import HealthReading
from .sessions import MAX_START_LEVEL, OPEN, ChargeSession
from .service import BatteryService
from .storage import ReadingStore

console = Console()

COLORS = {"green": "green", "yellow": "yellow", "red": "red", "gray": "dim"}

# En --watch, fallos seguidos de ADB que se toleran antes de salir (un parpadeo del cable)
WATCH_MAX_FAILURES = 3
# Intervalo de --sesion: una carga de 15 a 100 % dura horas
SESSION_WATCH_S = 60


def positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("debe ser un entero mayor que 0")
    return n


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Salud de la batería de un Samsung por ADB."
    )
    parser.add_argument(
        "--modelo", "-m", metavar="MODELO", help="Modelo (por defecto se detecta)."
    )
    parser.add_argument(
        "--watch",
        "-w",
        type=positive_int,
        metavar="SEGS",
        help="Actualizar cada N segundos.",
    )
    parser.add_argument("--json", "-j", action="store_true", help="Salida en JSON.")
    parser.add_argument(
        "--lista-modelos", action="store_true", help="Modelos y capacidades."
    )
    parser.add_argument(
        "--renovado", "-r", action="store_true", help="Análisis de reacondicionado."
    )
    parser.add_argument(
        "--guardar",
        action="store_true",
        help="Guardar la lectura en el historial y registrar la sesión de carga.",
    )
    parser.add_argument(
        "--sesion",
        "-s",
        action="store_true",
        help=f"Registrar la carga en curso: lee cada {SESSION_WATCH_S} s y termina al cerrar la sesión.",
    )
    parser.add_argument(
        "--sesiones", action="store_true", help="Sesiones de carga registradas."
    )
    return parser.parse_args(argv)


def render_health(r: HealthReading) -> None:
    color = COLORS.get(r.health_color, "white")
    if r.health_pct is not None:
        filled = int(r.health_pct / 5)
        bar = "█" * filled + "░" * (20 - filled)
        body = (
            f"[bold]Salud:[/bold]             [{color}]{r.health_pct} %  [{bar}]  {r.health_label}[/{color}]\n"
            f"[bold]Capacidad actual:[/bold]  {r.capacity_mah} mAh\n"
            f"[bold]De fábrica:[/bold]        {r.design_mah} mAh\n"
            f"[bold]Método:[/bold]            [dim]{r.method} ({r.method_detail})[/dim]"
        )
    else:
        body = f"[yellow]No se pudo calcular la salud.[/yellow]\n[dim]{escape(r.discarded_reason or '')}[/dim]"
    console.print(
        Panel(
            body,
            title=f"Batería · Samsung Galaxy {r.model}",
            border_style="blue",
            box=box.ROUNDED,
        )
    )

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("Nivel de carga", f"{r.level} %")
    table.add_row("Estado", r.status_name)
    table.add_row("Diagnóstico de Android", r.health_name)
    table.add_row("Temperatura", f"{r.temp_c} °C")
    table.add_row("Voltaje", f"{r.voltage_mv} mV")
    table.add_row("Carga actual", f"{r.charge_mah} mAh")
    console.print(
        Panel(table, title="En este momento", border_style="dim", box=box.ROUNDED)
    )
    if r.protect_note:
        console.print(Panel(r.protect_note, border_style="yellow", box=box.ROUNDED))


STATUS_LABELS = {"open": "en curso", "complete": "completa", "incomplete": "incompleta"}


def render_session(s: ChargeSession) -> None:
    health = f"{s.health_pct} %" if s.health_pct is not None else "—"
    body = (
        f"[bold]Sesión de carga:[/bold]  {STATUS_LABELS[s.status]} · {s.start_level} % → {s.end_level} %\n"
        f"[bold]Carga que entró:[/bold]  {s.added_mah} mAh en {s.duration_min} min\n"
        f"[bold]Salud de la sesión:[/bold] {health}"
    )
    if s.health_note and s.status != OPEN:
        body += f"\n[dim]{escape(s.health_note)}[/dim]"
    if s.end_reason:
        body += f"\n[dim]{escape(s.end_reason)}[/dim]"
    console.print(Panel(body, border_style="cyan", box=box.ROUNDED))


def render_sessions(sessions: list[ChargeSession], summary: dict) -> None:
    if not sessions:
        console.print("Todavía no hay sesiones de carga. Usa --sesion mientras cargas.")
        return
    counted = set(summary["counted_ids"])
    table = Table(box=box.SIMPLE_HEAD)
    for col in (
        "Inicio",
        "Rango",
        "Entró",
        "Capac.",
        "Salud",
        "Máx.",
        "Durac.",
        "Estado",
    ):
        table.add_column(col, no_wrap=True)
    for s in sessions:
        table.add_row(
            datetime.fromisoformat(s.started_at).strftime("%d/%m/%y %H:%M"),
            f"{s.start_level} → {s.end_level} %",
            f"{s.added_mah} mAh",
            f"{s.capacity_mah} mAh" if s.capacity_mah else "—",
            f"{s.health_pct} %" if s.health_pct is not None else "—",
            f"{s.max_temp_c} °C",
            f"{s.duration_min} min",
            STATUS_LABELS[s.status] + (" · cuenta" if s.id in counted else ""),
        )
    console.print(table)
    console.print(
        f"[dim]«cuenta» = carga de referencia del mes (de {MAX_START_LEVEL} % o menos a 100 %); "
        "solo esas se comparan.[/dim]"
    )
    if summary["monthly_degradation"] is not None:
        console.print(
            f"Degradación entre cargas de referencia: {summary['monthly_degradation']} % al mes"
        )


def render_renovation(report: dict) -> None:
    color = report["risk_color"]
    lines = [f"[bold]Riesgo:[/bold] [{color}]{report['risk_level']}[/{color}]\n"]
    if report["cycle_count"] is not None:
        lines.append(f"[bold]Ciclos de carga:[/bold] {report['cycle_count']}")
    for title, key, style in (
        ("Señales de alerta", "risk_factors", "red"),
        ("A favor", "green_flags", "green"),
        ("Sin verificar", "unverified", "dim"),
    ):
        if report[key]:
            lines.append(f"\n[bold {style}]{title}:[/bold {style}]")
            # Los textos traen datos del teléfono (fingerprint): sin escape, un «[/bold]» rompe Rich
            lines.extend(f"  • {escape(item)}" for item in report[key])
    lines.append(
        "\n[dim]Ningún dato de ADB confirma con certeza si es reacondicionado.[/dim]"
    )
    console.print(
        Panel(
            "\n".join(lines),
            title="¿Es reacondicionado?",
            border_style=color,
            box=box.ROUNDED,
        )
    )


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.lista_modelos:
        for name, mah in SAMSUNG_CAPACITIES.items():
            console.print(f"  {name:<14} {mah} mAh", highlight=False)
        return 0

    settings = Settings.from_env()
    store = ReadingStore(settings.db_path, settings.save_interval_s)
    try:
        store.init()
    except sqlite3.Error as exc:
        console.print(
            f"[red]No se pudo abrir el historial ({escape(str(settings.db_path))}):[/red] {escape(str(exc))}"
        )
        return 1
    service = BatteryService(AdbClient(timeout=settings.adb_timeout_s), store)

    if args.modelo:
        # «s24 ultra» también vale
        args.modelo = next(
            (m for m in SAMSUNG_CAPACITIES if m.lower() == args.modelo.lower()),
            args.modelo,
        )

    try:
        model = args.modelo or service.detect().model
        if model is None:
            # Con un modelo supuesto la capacidad de fábrica sería otra y el historial quedaría mal
            console.print(
                "[yellow]No se reconoció el modelo del teléfono.[/yellow] Indícalo con --modelo."
            )
            return 1
        if model not in SAMSUNG_CAPACITIES:
            console.print(
                f"[red]Modelo {escape(repr(model))} no reconocido.[/red] Usa --lista-modelos."
            )
            return 1

        if args.sesiones:
            sessions = service.sessions.sessions(model)
            summary = service.sessions.summary(model)
            if args.json:
                counted = set(summary["counted_ids"])
                data = {
                    "sessions": [s.to_dict(counted=s.id in counted) for s in sessions],
                    "summary": summary,
                }
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                render_sessions(sessions, summary)
            return 0

        if args.sesion:
            args.watch, args.guardar = SESSION_WATCH_S, True

        if args.renovado:
            report = service.renovation(model)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                render_renovation(report)
            return 0

        failures = 0
        while True:
            try:
                reading, _, save_error, session = service.current(
                    model, save=args.guardar
                )
            except AdbError as exc:
                failures += 1
                if not args.watch or failures >= WATCH_MAX_FAILURES:
                    raise
                console.print(
                    f"[yellow]{escape(str(exc))}[/yellow] Reintento {failures}/{WATCH_MAX_FAILURES - 1}…"
                )
                time.sleep(args.watch)
                continue
            failures = 0
            if save_error:
                console.print(f"[yellow]{escape(save_error)}[/yellow]")
            if args.json:
                print(json.dumps(reading.to_dict(), ensure_ascii=False, indent=2))
            else:
                if args.watch:
                    console.clear()
                render_health(reading)
                if session:
                    render_session(session)
            if not args.watch:
                return 0
            if args.sesion and session is None:
                if reading.status_code != 2:
                    console.print(
                        "[yellow]El teléfono no está cargando.[/yellow] Conecta el cargador y vuelve a correr --sesion."
                    )
                else:
                    console.print(
                        f"[yellow]La carga empieza en {reading.level} %.[/yellow] "
                        f"Solo se registra si empieza en {MAX_START_LEVEL} % o menos."
                    )
                return 1
            if args.sesion and session and session.status != OPEN:
                console.print("Sesión cerrada. Revisa el registro con --sesiones.")
                return 0
            console.print(
                f"[dim]Actualizando cada {args.watch} s; Ctrl+C para salir[/dim]"
            )
            time.sleep(args.watch)
    except AdbError as exc:
        console.print(f"[red]{escape(str(exc))}[/red]")
        return 1
    except sqlite3.Error as exc:
        console.print(f"[red]Error del historial:[/red] {escape(str(exc))}")
        return 1
    except KeyboardInterrupt:
        console.print("\nMonitoreo detenido.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
