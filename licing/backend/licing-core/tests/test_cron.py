import pytest

from app.api import ingesta
from app.config import settings
from app.database import get_db
from app.main import app
from app.services.ingesta_lote import EjecucionEnCursoError

SECRETO = "secreto-de-prueba"
RUTA = "/api/cron/ingesta"


class DbFalsa:
    def rollback(self):
        pass


@pytest.fixture
def lotes(client, monkeypatch):
    """Sustituye el lote real y devuelve los límites con que se llamó."""
    monkeypatch.setattr(settings, "cron_secret", SECRETO)
    monkeypatch.setattr(settings, "documentos_automaticos", False)
    app.dependency_overrides[get_db] = lambda: DbFalsa()
    llamadas = []

    async def lote_falso(db, client, limite_detalles):
        llamadas.append(limite_detalles)
        return {"procesados": 1, "errores": []}

    monkeypatch.setattr(ingesta, "ejecutar_ingesta_lote", lote_falso)
    return llamadas


def autorizado(secreto=SECRETO):
    return {"Authorization": "Bearer " + secreto}


def test_sin_secreto_configurado_queda_desactivado(client, lotes, monkeypatch):
    monkeypatch.setattr(settings, "cron_secret", "")
    assert client.post(RUTA, headers=autorizado("")).status_code == 503
    assert lotes == []


@pytest.mark.parametrize("headers", [{}, autorizado("otro"), {"Authorization": SECRETO}])
def test_rechaza_secreto_ausente_o_incorrecto(client, lotes, headers):
    assert client.post(RUTA, headers=headers).status_code == 401
    assert lotes == []


@pytest.mark.parametrize("metodo", ["get", "post"])
def test_ejecuta_lote_con_secreto(client, lotes, metodo):
    r = getattr(client, metodo)(RUTA + "?limite=2", headers=autorizado())
    assert r.status_code == 200, r.text
    assert r.json() == {"procesados": 1, "errores": []}
    assert lotes == [2]


def test_limite_predeterminado_y_maximo(client, lotes):
    assert client.post(RUTA, headers=autorizado()).status_code == 200
    assert lotes == [1]
    assert client.post(RUTA + "?limite=6", headers=autorizado()).status_code == 422


def test_omite_turno_si_hay_ingesta_en_curso(client, lotes, monkeypatch):
    async def en_curso(**_):
        raise EjecucionEnCursoError("Ya existe una ejecución de ingesta en curso.")

    monkeypatch.setattr(ingesta, "ejecutar_ingesta_lote", en_curso)
    r = client.post(RUTA, headers=autorizado())
    assert r.status_code == 200
    assert r.json() == {"omitida": True, "motivo": "Ya existe una ejecución de ingesta en curso."}
