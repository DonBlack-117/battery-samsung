"""Servidor web: `python -m battery_sam` (abre el navegador)."""

import argparse
import threading
import webbrowser

import uvicorn

from .config import Settings
from .web import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard de salud de batería.")
    parser.add_argument("--no-browser", action="store_true", help="No abrir el navegador.")
    args = parser.parse_args()

    settings = Settings.from_env()
    if not settings.is_local:
        print(
            f"Aviso: escuchando en {settings.host}. La API no tiene contraseña y muestra el "
            "número de serie del teléfono a cualquiera en la red."
        )
    url = f"http://{settings.host}:{settings.port}"
    if not args.no_browser:
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    print(f"Battery-Sam: {url}  (Ctrl+C para detener)")
    uvicorn.run(create_app(settings), host=settings.host, port=settings.port, log_level="warning")


if __name__ == "__main__":
    main()
