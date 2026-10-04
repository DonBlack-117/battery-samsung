import pytest

from battery_sam.service import BatteryService
from battery_sam.storage import ReadingStore
from tests.fakes import FakeShell


@pytest.fixture
def store(tmp_path):
    s = ReadingStore(tmp_path / "test.db", min_interval_s=600)
    s.init()
    return s


@pytest.fixture
def shell():
    return FakeShell()


@pytest.fixture
def service(shell, store):
    return BatteryService(shell, store)
