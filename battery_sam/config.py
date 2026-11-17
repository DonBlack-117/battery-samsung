"""Configuración; cada valor se puede cambiar con una variable de entorno."""

import os
from dataclasses import dataclass, field
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    db_path: Path = PROJECT_DIR / "data" / "battery_data.db"
    host: str = "127.0.0.1"
    port: int = 5000
    adb_timeout_s: float = 10.0
    # Mínimo entre lecturas guardadas del mismo modelo
    save_interval_s: int = 600
    # Cada cuánto consulta la web
    refresh_ms: int = 30_000
    # Nombres extra con los que se puede abrir la web (además de localhost y `host`),
    # p. ej. la IP de la laptop si se expone en la red. Separados por comas.
    allowed_hosts: tuple[str, ...] = field(default_factory=tuple)

    @ property
    def is_local(self) -> bool:
        return self.host in ("127.0.0.1", "localhost", "::1")

    @ classmethod
    def from_env(cls) -> "Settings":
        try:
            return cls._from_env()
        except ValueError as exc:
            raise SystemExit(
                f"Variable de entorno BATTERY_SAM_* inválida: {exc}"
            ) from None

    @ classmethod
    def _from_env(cls) -> "Settings":
        env = os.environ.get
        settings = cls(
            db_path=Path(env("BATTERY_SAM_DB", str(cls.db_path))),
            host=env("BATTERY_SAM_HOST", cls.host),
            port=int(env("BATTERY_SAM_PORT", cls.port)),
            adb_timeout_s=float(env("BATTERY_SAM_ADB_TIMEOUT", cls.adb_timeout_s)),
            save_interval_s=int(env("BATTERY_SAM_SAVE_INTERVAL", cls.save_interval_s)),
            refresh_ms=int(env("BATTERY_SAM_REFRESH_MS", cls.refresh_ms)),
            allowed_hosts=tuple(
                h.strip()
                for h in env("BATTERY_SAM_ALLOWED_HOSTS", "").split(",")
                if h.strip()
            ),
        )
        settings.validate()
        return settings

    def validate(self) -> None:
        if not 1 <= self.port <= 65535:
            raise ValueError(f"BATTERY_SAM_PORT={self.port} fuera de 1-65535")
        if self.adb_timeout_s <= 0:
            raise ValueError("BATTERY_SAM_ADB_TIMEOUT debe ser mayor que 0")
        if self.save_interval_s < 0:
            raise ValueError("BATTERY_SAM_SAVE_INTERVAL no puede ser negativo")
        if self.refresh_ms < 1000:
            raise ValueError("BATTERY_SAM_REFRESH_MS debe ser de al menos 1000")
