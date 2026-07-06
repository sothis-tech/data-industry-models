"""
Fixtures compartidos para los tests del backend.
Se usa TestClient de FastAPI/Starlette (sin levantar un servidor real).
"""
import pytest
from fastapi.testclient import TestClient

# Importar la app desde el módulo principal
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from main import app


@pytest.fixture
def client():
    """Cliente de test síncrono para la app FastAPI."""
    with TestClient(app) as c:
        yield c
