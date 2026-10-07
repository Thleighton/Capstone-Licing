import pytest
from fastapi.testclient import TestClient

from licing.core.auth import usuario_actual
from licing.main import app

USUARIO = {"id": "u1", "nombre": "Usuario Prueba", "email": "a@b.cl", "rol": "encargado_licitaciones", "activo": True}


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def client_autenticado():
    app.dependency_overrides[usuario_actual] = lambda: USUARIO
    yield TestClient(app)
    app.dependency_overrides.clear()
