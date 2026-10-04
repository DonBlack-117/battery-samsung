import dataclasses

import pytest

from battery_sam.device import BatterySnapshot, read_battery
from battery_sam.health import METHOD_ESTIMATE, METHOD_SYSFS, calculate_health, to_mah
from tests.fakes import FakeShell

BASE = BatterySnapshot(
    charge_full=None,
    charge_full_design=None,
    level=80,
    charge_counter=3_984_800,
    voltage_mv=4123,
    temperature_raw=312,
    health_code=2,
    status_code=4,
    protect_battery=True,
)


def snap(**changes) -> BatterySnapshot:
    return dataclasses.replace(BASE, **changes)


def test_estimate_matches_real_s24_reading():
    r = calculate_health(snap(), "S24 Ultra", 5000)
    assert r.method == METHOD_ESTIMATE
    assert r.health_pct == 99.6
    assert r.capacity_mah == 4981
    assert r.health_label == "Excelente"


def test_reads_dumpsys_from_shell():
    s = read_battery(FakeShell())
    assert (s.level, s.charge_counter, s.voltage_mv, s.temperature_raw) == (80, 3_984_800, 4123, 312)
    assert s.protect_battery is True


def test_sysfs_used_when_plausible():
    r = calculate_health(snap(charge_full=4_900_000, charge_full_design=5_000_000), "S24 Ultra", 5000)
    assert r.method == METHOD_SYSFS
    assert r.health_pct == 98.0


def test_sysfs_unit_mismatch_falls_back_to_model_capacity():
    # Caso real del S25 Ultra: daba 1000 %
    r = calculate_health(snap(charge_full=4_950_000, charge_full_design=495_000), "S25 Ultra", 5000)
    assert r.method == METHOD_SYSFS
    assert r.health_pct == 99.0


def test_impossible_sysfs_falls_back_to_estimate():
    r = calculate_health(snap(charge_full=9_999_999, charge_full_design=1000), "S24 Ultra", 5000)
    assert r.method == METHOD_ESTIMATE


@pytest.mark.parametrize("level", [5, 10, 19])
def test_low_level_is_not_estimated(level):
    r = calculate_health(snap(level=level, charge_counter=600_000), "S24 Ultra", 5000)
    assert r.health_pct is None
    assert "20 %" in r.discarded_reason


def test_implausible_estimate_is_discarded():
    # 1.7 Ah al 33 % da 103 %: ruido de la estimación
    r = calculate_health(snap(level=33, charge_counter=1_700_000), "S24 Ultra", 5000)
    assert r.health_pct is None
    assert r.discarded_reason


@pytest.mark.parametrize("raw,expected", [(5_000_000, 5000.0), (4981, 4981.0), (100_000, 100.0)])
def test_to_mah(raw, expected):
    assert to_mah(raw) == expected


def test_protect_note_from_setting():
    assert "Proteger batería" in calculate_health(snap(), "S24 Ultra", 5000).protect_note
    assert calculate_health(snap(protect_battery=False), "S24 Ultra", 5000).protect_note is None


def test_protect_note_guessed_without_setting():
    note = calculate_health(snap(protect_battery=None), "S24 Ultra", 5000).protect_note
    assert note and "parece" in note
