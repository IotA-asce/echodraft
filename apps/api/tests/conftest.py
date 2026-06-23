from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from echodraft_api.config import AppSettings
from echodraft_api.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        artifact_root=tmp_path / "artifacts",
    )


@pytest.fixture
def app(settings: AppSettings):
    return create_app(settings)


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
