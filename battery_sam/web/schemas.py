"""Modelos de respuesta de la API (aparecen en /docs)."""

from pydantic import BaseModel


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


class ModelInfo(BaseModel):
    name: str
    design_mah: int


class ModelsResponse(BaseModel):
    default: str
    models: list[ModelInfo]


class DeviceResponse(BaseModel):
    model: str | None
    brand: str | None
    raw_model: str | None
    is_samsung: bool


class ChargeSessionOut(BaseModel):
    id: int
    model: str
    started_at: str
    updated_at: str
    ended_at: str | None
    status: str
    end_reason: str | None
    design_mah: int
    start_level: int
    end_level: int
    span: int
    added_mah: int
    capacity_mah: int | None
    health_pct: float | None
    health_note: str | None
    max_temp_c: float
    duration_min: int
    readings: int
    # Carga de referencia del mes (entra en la comparación)
    counted: bool


class SessionSummary(BaseModel):
    total: int
    last_health: float | None
    monthly_degradation: float | None
    months_to_80: float | None
    counted_ids: list[int]


class SessionsResponse(BaseModel):
    sessions: list[ChargeSessionOut]
    summary: SessionSummary


class CurrentResponse(BaseModel):
    model: str
    design_mah: int
    health_pct: float | None
    health_label: str
    health_color: str
    method: str | None
    method_detail: str | None
    capacity_mah: int | None
    discarded_reason: str | None
    level: int
    charge_mah: int
    charge_counter_uah: int
    voltage_mv: int
    temp_c: float
    health_code: int
    health_name: str
    status_code: int
    status_name: str
    protect_battery: bool | None
    protect_note: str | None
    needs_check: bool
    overridden: bool
    save_error: str | None
    saved: bool
    session: ChargeSessionOut | None


class RenovationResponse(BaseModel):
    risk_level: str
    risk_color: str
    risk_factors: list[str]
    green_flags: list[str]
    unverified: list[str]
    cycle_count: int | None
    warranty_voided: bool
    knox_fuse_triggered: bool
    warranty_bit: str | None
    knox_fuse: str | None
    serial_masked: str | None
    build_fingerprint: str | None


class HistoryPoint(BaseModel):
    timestamp: str
    health_pct: float | None
    level: int | None
    temp_c: float | None


class StatsResponse(BaseModel):
    model: str
    total_readings: int
    first_date: str | None
    first_health: float | None
    last_health: float | None
    max_temp_c: float | None
    days_with_data: int
    monthly_degradation: float | None
    months_to_80: float | None
    trend_note: str | None
    trend_source: str | None
    sessions_with_health: int
    session_health: float | None
