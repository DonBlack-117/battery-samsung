"""Cliente ADB: una sola llamada a `adb shell` por lectura."""

import logging
import platform
import secrets
import subprocess
import threading
from pathlib import Path
from typing import Protocol

_BUNDLED_DIR = Path(__file__).resolve().parent.parent / "adb"
_MARK = "<<<bsam:"

log = logging.getLogger(__name__)


class AdbError(RuntimeError):
    """Error base de ADB; `code` viaja a la API."""

    code = "adb_error"


class AdbNotFoundError(AdbError):
    code = "adb_not_found"

    def __init__(self) -> None:
        super().__init__(
            "ADB no está instalado o no está en el PATH. Descárgalo en "
            "https://developer.android.com/studio/releases/platform-tools"
        )


class DeviceNotConnectedError(AdbError):
    code = "no_device"


class DeviceUnauthorizedError(AdbError):
    code = "unauthorized"


class AdbTimeoutError(AdbError):
    code = "adb_timeout"


class BadReadingError(AdbError):
    """La salida del teléfono no tiene la forma esperada (secciones repetidas, dumpsys vacío)."""

    code = "bad_reading"


class Shell(Protocol):
    """Lo que necesita el resto del paquete; los tests usan un falso."""

    def run_sections(self, sections: dict[str, str]) -> dict[str, str]:
        ...


def resolve_adb() -> str:
    """En Windows usa el adb incluido en `adb/`; en el resto, el del PATH."""
    if platform.system() != "Windows":
        return "adb"
    exe = _BUNDLED_DIR / "adb.exe"
    return str(exe) if exe.exists() else "adb"


class AdbClient:
    def __init__(self, adb_path: str | None = None, timeout: float = 10.0):
        self.adb_path = adb_path or resolve_adb()
        self.timeout = timeout
        # La web atiende peticiones en varios hilos: una sola conversación con adb a la vez
        self._lock = threading.Lock()

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [self.adb_path, *args],
                capture_output=True,
                # Nombres y fingerprints pueden traer bytes no ASCII; en Windows la
                # codificación local sería cp1252 y lanzaría UnicodeDecodeError.
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
            )
        except FileNotFoundError:
            raise AdbNotFoundError() from None
        except OSError as exc:
            raise AdbError(
                f"No se pudo ejecutar ADB ({self.adb_path}): {exc.strerror or exc}"
            ) from exc
        except subprocess.TimeoutExpired:
            raise AdbTimeoutError(
                f"ADB no respondió en {self.timeout:.0f} s. Desconecta y vuelve a conectar el cable."
            ) from None

    def ensure_device(self) -> None:
        proc = self._run(["get-state"])
        # Si adb tuvo que arrancar su servidor, antes imprime «* daemon started…»
        lines = proc.stdout.strip().splitlines()
        if proc.returncode == 0 and lines and lines[-1].strip() == "device":
            return
        err = f"{proc.stderr}\n{proc.stdout}".lower()
        if "unauthorized" in err:
            raise DeviceUnauthorizedError(
                "El teléfono no ha autorizado esta computadora. Toca «Permitir» en el aviso de depuración USB."
            )
        if "more than one" in err:
            raise DeviceNotConnectedError(
                "Hay más de un teléfono o emulador conectado. Deja solo el que quieres revisar."
            )
        if "offline" in err:
            raise DeviceNotConnectedError(
                "El teléfono aparece desconectado (offline). Desconecta y vuelve a conectar el cable."
            )
        raise DeviceNotConnectedError(
            "No se detectó ningún teléfono. Conéctalo por USB y activa la depuración USB "
            "en Opciones para desarrolladores."
        )

    def run_sections(self, sections: dict[str, str]) -> dict[str, str]:
        """Ejecuta varios comandos en una sola shell y separa la salida por nombre.

        Cada comando corre con stderr descartado: si falla (p. ej. Permission
        denied en /sys), su sección queda vacía. El marcador lleva un nonce por
        llamada para que la salida del teléfono (p. ej. un ajuste escrito con
        `settings put`) no pueda abrir una sección falsa.
        """
        mark = f"{_MARK}{secrets.token_hex(8)}:"
        # `true` al final: el código de salida no depende del último comando,
        # que puede fallar sin que falte nada (p. ej. `settings` restringido).
        script = "; ".join(
            [
                f"echo '{mark}{name}'; {cmd} 2>/dev/null"
                for name, cmd in sections.items()
            ]
            + ["true"]
        )
        with self._lock:
            self.ensure_device()
            proc = self._run(["shell", script])
        result = parse_sections(proc.stdout, mark)
        missing = set(sections) - set(result)
        # Si el cable se suelta entre get-state y shell no llega ninguna sección
        if proc.returncode != 0 or missing:
            log.warning(
                "adb shell rc=%s secciones_faltantes=%s stderr=%r",
                proc.returncode,
                sorted(missing),
                proc.stderr.strip()[:500],
            )
            raise DeviceNotConnectedError(
                "Se perdió la conexión con el teléfono durante la lectura. Revisa el cable."
            )
        extra = set(result) - set(sections)
        if extra:
            raise BadReadingError(
                f"El teléfono devolvió secciones inesperadas: {sorted(extra)}"
            )
        return result


def parse_sections(output: str, mark: str = _MARK) -> dict[str, str]:
    """Separa la salida por marcador. Una sección repetida es salida manipulada."""
    result: dict[str, str] = {}
    current: str | None = None
    lines: list[str] = []
    for line in output.splitlines():
        if line.startswith(mark):
            if current is not None:
                result[current] = "\n".join(lines).strip()
            current, lines = line[len(mark) :].strip(), []
            if current in result:
                raise BadReadingError(
                    f"La sección «{current}» llegó dos veces en la salida del teléfono."
                )
        elif current is not None:
            lines.append(line)
    if current is not None:
        result[current] = "\n".join(lines).strip()
    return result
