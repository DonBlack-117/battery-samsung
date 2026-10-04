"""API y dashboard con FastAPI."""

import csv
import io
import sqlite3
from typing import Annotated

from fastapi import Depends, FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .. import __version__
from ..adb import AdbClient, AdbError, AdbTimeoutError
from ..catalog import DEFAULT_MODEL, SAMSUNG_CAPACITIES, UnknownModelError, design_capacity
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
    StatsResponse,
)

ERRORS = {503: {"model": ErrorResponse}, 404: {"model": ErrorResponse}}


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(settings: Settings | None = None, service: BatteryService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if service is None:
        store = ReadingStore(settings.db_path, settings.save_interval_s)
        store.init()
        service = BatteryService(AdbClient(timeout=settings.adb_timeout_s), store)

    app = FastAPI(title="Battery-Sam", version=__version__)
    app.mount("/static", StaticFiles(directory=PROJECT_DIR / "static"), name="static")
    templates = Jinja2Templates(directory=PROJECT_DIR / "templates")

    def get_service() -> BatteryService:
        return service

    Svc = Annotated[BatteryService, Depends(get_service)]
    Model = Annotated[str, Query(description="Modelo, p. ej. «S24 Ultra»")]

    @app.exception_handler(AdbTimeoutError)
    async def _adb_timeout(_: Request, exc: AdbTimeoutError):
        return _error(504, exc.code, str(exc))

    @app.exception_handler(AdbError)
    async def _adb_error(_: Request, exc: AdbError):
        return _error(503, exc.code, str(exc))

    @app.exception_handler(sqlite3.OperationalError)
    async def _db_error(_: Request, exc: sqlite3.OperationalError):
        return _error(503, "db_unavailable", f"No se pudo usar el historial: {exc}")

    @app.exception_handler(UnknownModelError)
    async def _unknown_model(_: Request, exc: UnknownModelError):
        return _error(404, "unknown_model", str(exc))

    @app.get("/", response_class=HTMLResponse, include_in_schema=False)
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

    @app.get("/api/models", response_model=ModelsResponse)
    def models():
        return {
            "default": DEFAULT_MODEL,
            "models": [{"name": n, "design_mah": m} for n, m in SAMSUNG_CAPACITIES.items()],
        }

    @app.get("/api/device", response_model=DeviceResponse, responses=ERRORS)
    def device(svc: Svc):
        return svc.detect()

    @app.get("/api/current", response_model=CurrentResponse, responses=ERRORS)
    def current(
        svc: Svc,
        model: Model = DEFAULT_MODEL,
        save: Annotated[bool, Query(description="Guardar en el historial")] = True,
    ):
        reading, saved = svc.current(model, save=save)
        return {**reading.to_dict(), "saved": saved}

    @app.get("/api/renovation", response_model=RenovationResponse, responses=ERRORS)
    def renovation(svc: Svc, model: Model = DEFAULT_MODEL):
        return svc.renovation(model)

    @app.get("/api/history", response_model=list[HistoryPoint], responses=ERRORS)
    def history(
        svc: Svc,
        model: Model = DEFAULT_MODEL,
        days: Annotated[int, Query(ge=1, le=3650)] = 30,
    ):
        design_capacity(model)
        return svc.store.readings(model, days)

    @app.get("/api/stats", response_model=StatsResponse, responses=ERRORS)
    def stats(svc: Svc, model: Model = DEFAULT_MODEL):
        design_capacity(model)
        return svc.store.stats(model)

    @app.get("/api/export.csv", responses=ERRORS)
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
