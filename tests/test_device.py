from battery_sam.adb import parse_sections
from battery_sam.device import detect_device, match_model
from tests.fakes import S24_ULTRA, FakeShell


def test_parse_sections_keeps_empty_sections():
    out = "<<<bsam:a\n1\n<<<bsam:b\n<<<bsam:c\nx\ny\n"
    assert parse_sections(out) == {"a": "1", "b": "", "c": "x\ny"}


def test_detects_s24_ultra():
    info = detect_device(FakeShell())
    assert info.model == "S24 Ultra"
    assert info.brand == "Samsung"
    assert info.is_samsung


def test_model_by_code_when_marketname_missing():
    assert match_model(None, "SM-A057F") == "A05s"


def test_non_samsung_has_no_model():
    info = detect_device(FakeShell({**S24_ULTRA, "brand": "google", "model": "Pixel 8"}))
    assert info.model is None
    assert not info.is_samsung
    assert info.raw_model == "Pixel 8"
