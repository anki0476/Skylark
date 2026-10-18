import pytest

from skylark.fixture import create_fixture, fixture_config
from skylark.store import Store


@pytest.fixture
def manifest(tmp_path):
    return create_fixture(tmp_path / "fixture")


@pytest.fixture
def config():
    return fixture_config()


@pytest.fixture
def store(tmp_path):
    return Store(tmp_path / "state")

