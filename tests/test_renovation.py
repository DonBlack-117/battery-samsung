from battery_sam.renovation import analyze_renovation_risk

CLEAN = {"cycle_count": None, "warranty_bit": "0", "knox_fuse": None, "build_fingerprint": "samsung/x"}


def test_unreadable_cycles_are_unverified_not_risk():
    r = analyze_renovation_risk(CLEAN, 99.6)
    assert r["risk_level"] == "Bajo"
    assert r["unverified"] and r["unverified"][0].startswith("Ciclos")


def test_warranty_bit_raises_risk():
    r = analyze_renovation_risk({**CLEAN, "warranty_bit": "1"}, 99.0)
    assert r["warranty_voided"] and r["risk_level"] == "Medio"


def test_three_signals_is_high():
    r = analyze_renovation_risk(
        {"cycle_count": 400, "warranty_bit": "1", "knox_fuse": "1", "build_fingerprint": "lineage/x"}, 75.0
    )
    assert r["risk_level"] == "Alto"
    assert len(r["risk_factors"]) == 5


def test_missing_warranty_bit_is_unverified():
    r = analyze_renovation_risk({**CLEAN, "warranty_bit": None}, None)
    assert any("Warranty" in u for u in r["unverified"])
    assert r["warranty_bit"] is None


def test_raw_warranty_matches_flag():
    r = analyze_renovation_risk({**CLEAN, "warranty_bit": "0", "boot_warranty_bit": "1"}, None)
    assert r["warranty_voided"] and r["warranty_bit"] == "1"
