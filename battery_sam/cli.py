"""Uso desde la terminal: `python -m battery_sam.cli`."""

import argparse
import json
import sys
import time

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from .adb import AdbClient, AdbError
from .catalog import SAMSUNG_CAPACITIES
from .config import Settings
from .health import HealthReading
from .service import BatteryService
from .storage import ReadingStore

console = Console()

COLORS = {"green": "green", "yellow": "yellow", "red": "red", "gray": "dim"}


def positive_int(value: str) -> int:
    n = int(value)
    if n <= 0:
        raise argparse.ArgumentTypeError("debe ser un entero mayor que 0")
    return n


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Salud de la batería de un Samsung por ADB.")
    parser.add_argument("--modelo", "-m", metavar="MODELO", help="Modelo (por defecto se detecta).")
    parser.add_argument("--watch", "-w", type=positive_int, metavar="SEGS", help="Actualizar cada N segundos.")
    parser.add_argument("--json", "-j", action="store_true", help="Salida en JSON.")
    parser.add_argument("--lista-modelos", action="store_true", help="Modelos y capacidades.")
    parser.add_argument("--renovado", "-r", action="store_true", help="Análisis de reacondicionado.")
    parser.add_argument("--guardar", action="store_true", help="Guardar la lectura en el historial.")
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
        body = f"[yellow]No se pudo calcular la salud.[/yellow]\n[dim]{r.discarded_reason}[/dim]"
    console.print(Panel(body, title=f"Batería · Samsung Galaxy {r.model}", border_style="blue", box=box.ROUNDED))

    table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
    table.add_column(style="dim")
    table.add_column(style="bold")
    table.add_row("Nivel de carga", f"{r.level} %")
    table.add_row("Estado", r.status_name)
    table.add_row("Diagnóstico de Android", r.health_name)
    table.add_row("Temperatura", f"{r.temp_c} °C")
    table.add_row("Voltaje", f"{r.voltage_mv} mV")
    table.add_row("Carga actual", f"{r.charge_mah} mAh")
    console.print(Panel(table, title="En este momento", border_style="dim", box=box.ROUNDED))
    if r.protect_note:
        console.print(Panel(r.protect_note, border_style="yellow", box=box.ROUNDED))


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
            lines.extend(f"  • {item}" for item in report[key])
    lines.append("\n[dim]Ningún dato de ADB confirma con certeza si es reacondicionado.[/dim]")
    console.print(Panel("\n".join(lines), title="¿Es reacondicionado?", border_style=color, box=box.ROUNDED))


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.lista_modelos:
        for name, mah in SAMSUNG_CAPACITIES.items():
            print(f"  {name:<14} {mah} mAh")
        return 0

    settings = Settings.from_env()
    store = ReadingStore(settings.db_path, settings.save_interval_s)
    store.init()
    service = BatteryService(AdbClient(timeout=settings.adb_timeout_s), store)

    try:
        model = args.modelo or service.detect().model
        if model is None:
            # Con un modelo supuesto la capacidad de fábrica sería otra y el historial quedaría mal
            console.print("[yellow]No se reconoció el modelo del teléfono.[/yellow] Indícalo con --modelo.")
            return 1
        if model not in SAMSUNG_CAPACITIES:
            console.print(f"[red]Modelo {model!r} no reconocido.[/red] Usa --lista-modelos.")
            return 1

        if args.renovado:
            report = service.renovation(model)
            if args.json:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                render_renovation(report)
            return 0

        while True:
            reading, _ = service.current(model, save=args.guardar)
            if args.json:
                print(json.dumps(reading.to_dict(), ensure_ascii=False, indent=2))
            else:
                if args.watch:
                    console.clear()
                render_health(reading)
            if not args.watch:
                return 0
            console.print(f"[dim]Actualizando cada {args.watch} s; Ctrl+C para salir[/dim]")
            time.sleep(args.watch)
    except AdbError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1
    except KeyboardInterrupt:
        console.print("\nMonitoreo detenido.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
