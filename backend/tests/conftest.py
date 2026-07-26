from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from coc_kp_assistant.app import create_app
from coc_kp_assistant.config import Settings
from coc_kp_assistant.infrastructure.models import Base


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(Settings(database_url="sqlite+pysqlite:///:memory:"))
    Base.metadata.create_all(app.state.engine)
    with TestClient(app) as test_client:
        yield test_client
    app.state.engine.dispose()

