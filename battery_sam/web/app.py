"""API y dashboard con FastAPI."""

import csv
import io
import logging
import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .. import __version__
from ..adb import AdbClient, AdbError, AdbTimeoutError
from ..catalog import (
    DEFAULT_MODEL,
    SAMSUNG_CAPACITIES,
    UnknownModelError,
    design_capacity,
)
from ..config import PROJECT_DIR, Settings
from ..service import BatteryService
from ..storage import COLUMNS, ReadingStore
from .schemas import (
    CurrentResponse,
    DeviceResponse,
    ErrorResponse,
    HistoryPoint,
    ModelsResponse,
    RenovationResponse,
    SessionsResponse,
    StatsResponse,
)

ERRORS = {503: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}

log = logging.getLogger(__name__)

LOCAL_HOSTS = ("127.0.0.1", "localhost", "::1", "[::1]")

# Todo se sirve desde el propio servidor; Chart.js está en static/vendor.
# style-src lleva 'unsafe-inline' porque reading.js y chart.js ponen estilos en línea.
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; font-src 'self'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}

# Sec-Fetch-Site que se aceptan en /api: el propio dashboard, o navegación
# directa / curl (sin cabecera). Bloquea <img src="http://127.0.0.1:5000/api/...">
# desde otra web (CSRF), que de otro modo leería el teléfono y escribiría en SQLite.
ALLOWED_FETCH_SITES = {"same-origin", "none", None}

# La página, los scripts y los estilos se revalidan en cada carga (con el ETag el
# servidor responde 304 sin volver a mandar el archivo). Las fuentes se quedan en caché.
NO_CACHE_SUFFIXES = (".js", ".css", "/")


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message}}
    )


def create_app(
    settings: Settings | None = None, service: BatteryService | None = None
) -> FastAPI:
    settings = settings or Settings.from_env()
    if service is None:
        store = ReadingStore(settings.db_path, settings.save_interval_s)
        store.init()
        service = BatteryService(AdbClient(timeout=settings.adb_timeout_s), store)

    # Sin /docs ni /openapi.json: cargaban Swagger desde un CDN y no hacen falta
    app = FastAPI(
        title="Battery-Sam",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )
    # Contra DNS rebinding: una web que se reasigne a 127.0.0.1 manda su propio Host
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=sorted({*LOCAL_HOSTS, settings.host, *settings.allowed_hosts}),
    )

    @ app.middleware("http")
    async def _security(request: Request, call_next):
        if request.url.path.startswith("/api/"):
            site = request.headers.get("sec-fetch-site")
            if site not in ALLOWED_FETCH_SITES:
                return _error(403, "cross_site", "Petición desde otro sitio rechazada.")
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if request.url.path.endswith(NO_CACHE_SUFFIXES):
            # Que el navegador revalide con el ETag: sin esto mezcla un main.js
            # nuevo con un api.js viejo en caché después de una actualización
            response.headers["Cache-Control"] = "no-cache"
        return response

    app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PROJECT_DIR / "templates")

    def get_service() -> BatteryService:
        return service

    Svc = Annotated[BatteryService, Depends(get_service)]
    Model = Annotated[str, Query(description="Modelo, p. ej. «S24 Ultra»")]

    @ app.exception_handler(AdbTimeoutError)
    async def _adb_timeout(request: Request, exc: AdbTimeoutError):
        log.warning("%s %s: %s", request.method, request.url.path, exc)
        return _error(504, exc.code, str(exc))

    @ app.exception_handler(AdbError)
    async def _adb_error(request: Request, exc: AdbError):
        log.warning(
            "%s %s: %s (%s)",
            request.method,
            request.url.path,
            exc,
            exc.code,
            exc_info=exc.__cause__,
        )
        return _error(503, exc.code, str(exc))

    @ app.exception_handler(sqlite3.Error)
    async def _db_error(request: Request, exc: sqlite3.Error):
        # El detalle (con la ruta de la base) va al log, no al navegador
        log.error(
            "%s %s: error de SQLite", request.method, request.url.path, exc_info=exc
        )
        return _error(
            503,
            "db_unavailable",
            "No se pudo usar el historial. Revisa la consola del servidor.",
        )

    @ app.exception_handler(UnknownModelError)
    async def _unknown_model(_: Request, exc: UnknownModelError):
        return _error(404, "unknown_model", str(exc))

    @ app.get("/", response_class=HTMLResponse, include_in_schema=False)
    def index(request: Request):
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "modelos": list(SAMSUNG_CAPACITIES),
                "default_model": DEFAULT_MODEL,
                "refresh_ms": settings.refresh_ms,
            },
        )

    @ app.get("/api/models", response_model=ModelsResponse)
    def models():
        return {
            "default": DEFAULT_MODEL,
            "models": [
                {"name": n, "design_mah": m} for n, m in SAMSUNG_CAPACITIES.items()
            ],
        }

    @ app.get("/api/device", response_model=DeviceResponse, responses=ERRORS)
    def device(svc: Svc):
        return svc.detect()

    @ app.get("/api/current", response_model=CurrentResponse, responses=ERRORS)
    def current(
        svc: Svc,
        model: Model = DEFAULT_MODEL,
        save: Annotated[bool, Query(description="Guardar en el historial")] = True,
    ):
        reading, saved, save_error, session = svc.current(model, save=save)
        return {
            **reading.to_dict(),
            "saved": saved,
            "save_error": save_error,
            "session": session.to_dict() if session else None,
        }

    @ app.get("/api/renovation", response_model=RenovationResponse, responses=ERRORS)
    def renovation(svc: Svc, model: Model = DEFAULT_MODEL):
        return svc.renovation(model)

    @ app.get("/api/history", response_model=list[HistoryPoint], responses=ERRORS)
    def history(
        svc: Svc,
        model: Model = DEFAULT_MODEL,
        days: Annotated[int, Query(ge=1, le=3650)] = 30,
    ):
        design_capacity(model)
        return svc.store.readings(model, days)

    @ app.get("/api/stats", response_model=StatsResponse, responses=ERRORS)
    def stats(svc: Svc, model: Model = DEFAULT_MODEL):
        design_capacity(model)
        return svc.stats(model)

    @ app.get("/api/sessions", response_model=SessionsResponse, responses=ERRORS)
    def sessions(
        svc: Svc,
        model: Model = DEFAULT_MODEL,
        limit: Annotated[int, Query(ge=1, le=500)] = 24,
    ):
        design_capacity(model)
        summary = svc.sessions.summary(model)
        counted = set(summary["counted_ids"])
        return {
            "sessions": [
                s.to_dict(counted=s.id in counted)
                for s in svc.sessions.sessions(model, limit)
            ],
            "summary": summary,
        }

    @ app.get("/api/export.csv", responses=ERRORS)
    def export_csv(
        svc: Svc,
        model: Model = DEFAULT_MODEL,
        days: Annotated[int, Query(ge=1, le=3650)] = 365,
    ):
        design_capacity(model)
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(svc.store.readings(model, days))
        filename = f"battery_history_{model.replace(' ', '_')}.csv"
        return Response(
            output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app
