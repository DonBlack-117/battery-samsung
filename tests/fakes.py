"""Teléfono falso: responde como `AdbClient.run_sections` sin ADB."""

from pathlib import Path

from battery_sam.adb import AdbError

FIXTURES = Path(__file__).parent / "fixtures"
DUMPSYS_S24 = (FIXTURES / "dumpsys_battery_s24.txt").read_text()

# S24 Ultra real (2026-09-28): sysfs bloqueado por SELinux, salud por estimación
S24_ULTRA = {
    "charge_full": "",
    "charge_full_design": "",
    "batt_capacity_max": "",
    "fg_capacity": "",
    "dumpsys": DUMPSYS_S24,
    "protect_battery": "1",
    "brand": "samsung",
    "manufacturer": "samsung",
    "model": "SM-S928B",
    "marketname": "Galaxy S24 Ultra",
    "cycle_count": "",
    "warranty_bit": "0",
    "boot_warranty_bit": "0",
    "knox_fuse": "",
    "serial": "R5CX12345678",
    "boot_serial": "",
    "build_fingerprint": "samsung/e3qxxx/e3q:14/UP1A.231005.007/S928BXXU1AWM9:user/release-keys",
}


class FakeShell:
    def __init__(self, values: dict | None = None, error: AdbError | None = None):
        self.values = dict(S24_ULTRA if values is None else values)
        self.error = error
        self.calls = 0

    def run_sections(self, sections: dict[str, str]) -> dict[str, str]:
        self.calls += 1
        if self.error:
            raise self.error
        return {name: self.values.get(name, "") for name in sections}
