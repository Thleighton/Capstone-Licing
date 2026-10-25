"""Pruebas aisladas: nunca conectan al DATABASE_URL del .env del usuario."""
import os
from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")
if TEST_DATABASE_URL and "test" not in (make_url(TEST_DATABASE_URL).database or "").lower():
    raise pytest.UsageError("TEST_DATABASE_URL debe apuntar a una base cuyo nombre contenga 'test'")
os.environ["DATABASE_URL"] = TEST_DATABASE_URL or "postgresql+psycopg://test:test@127.0.0.1:55439/licing_test"
os.environ["MP_TICKET"] = "test-sin-acceso-real"
os.environ["USUARIOS_URL"] = "https://usuarios.example.test"
os.environ["USUARIOS_ANON_KEY"] = "anon-test"
# El lote paralelo abre su propia sesión, fuera de la transacción de cada prueba.
os.environ["COMPRAS_AGILES_AUTOMATICAS"] = "false"
# Nunca la función de producción, aunque un .env local traiga CRON_SECRET: .invalid no resuelve.
os.environ["FILTRADAS_URL"] = "https://filtradas.invalid/functions/v1/licing-filtradas"
os.environ["SEMANTICA_MODO"] = "desactivada"
os.environ["SEMANTICA_URL"] = ""
os.environ["SEMANTICA_TOKEN"] = ""
os.environ["SEMANTICA_MODELO_DIR"] = ""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.auth import _cache, usuario_actual
from app.database import engine, get_db
from app.main import app

USUARIO = {"id": "u1", "nombre": "Prueba", "email": "test@example.test", "rol": "encargado_licitaciones", "activo": True}


@pytest.fixture(autouse=True)
def aislar_autenticacion(request):
    nombre = Path(request.node.fspath).name
    if nombre in {"test_persistencia.py", "test_descarga_detalle.py"}:
        if not TEST_DATABASE_URL:
            pytest.skip("Requiere TEST_DATABASE_URL de una base de pruebas migrada")
        app.dependency_overrides[usuario_actual] = lambda: {**USUARIO, "rol": "administrador"}
    _cache.clear()
    yield
    app.dependency_overrides.clear()
    _cache.clear()


@pytest.fixture
def client():
    with TestClient(app) as cliente:
        yield cliente


@pytest.fixture
def client_usuario(client):
    app.dependency_overrides[usuario_actual] = lambda: USUARIO
    return client


@pytest.fixture
def integration_db():
    if not TEST_DATABASE_URL:
        pytest.skip("Requiere TEST_DATABASE_URL de una base de pruebas migrada")
    with engine.connect() as conexion:
        transaccion = conexion.begin()
        db = Session(bind=conexion, join_transaction_mode="create_savepoint")
        app.dependency_overrides[get_db] = lambda: db
        try:
            yield db
        finally:
            db.close()
            transaccion.rollback()
