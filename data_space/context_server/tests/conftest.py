import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import main


@pytest.fixture
def client(tmp_path, monkeypatch):
    """Cliente de test con raíz de tenants aislada en un directorio temporal."""
    monkeypatch.setattr(main, "TENANTS_ROOT", tmp_path / "tenants")
    with TestClient(main.app) as c:
        yield c
