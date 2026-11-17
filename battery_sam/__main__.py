"""Servidor web: `python -m battery_sam` (abre el navegador)."""

import argparse
import threading
import webbrowser

import uvicorn

from .config import Settings
from .web import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de salud de batería.")
    parser.add_argument(
        "--no-browser", action="store_true", help="No abrir el navegador."
    )
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.is_local:
        print(
            f"Aviso: escuchando en {settings.host}. La API no tiene contraseña: cualquiera en la "
            "red puede leer la batería y el historial. Agrega a BATTERY_SAM_ALLOWED_HOSTS la IP "
            "o el nombre con que la abrirás."
        )
    # 0.0.0.0 o :: no se pueden abrir en el navegador
    browse_host = (
        "127.0.0.1" if settings.host in ("0.0.0.0", "::", "") else settings.host
    )
    url = f"http://{browse_host}:{settings.port}"
    if not args.no_browser:
        # daemon: si uvicorn no arranca (puerto ocupado) el proceso no se queda esperando
        timer = threading.Timer(1.2, lambda: webbrowser.open(url))
        timer.daemon = True
        timer.start()
    print(f"Battery-Sam: {url}  (Ctrl+C para detener)")
    uvicorn.run(
        create_app(settings),
        host=settings.host,
        port=settings.port,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
