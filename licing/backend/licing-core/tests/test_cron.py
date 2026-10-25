import asyncio
import time

import pytest

from app.api import cron, ingesta
from app.config import settings
from app.database import get_db
from app.main import app
from app.services.ingesta_lote import EjecucionEnCursoError

SECRETO = "secreto-de-prueba"
RUTA = "/api/cron/ingesta"


class DbFalsa:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def rollback(self):
        pass


@pytest.fixture
def lotes(client, monkeypatch):
    """Sustituye el lote real y devuelve los límites con que se llamó."""
    monkeypatch.setattr(settings, "cron_secret", SECRETO)
    monkeypatch.setattr(settings, "documentos_automaticos", False)
    monkeypatch.setattr(settings, "compras_agiles_automaticas", False)
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


def lento(cancelado):
    """Tarea que no termina a tiempo y registra si fue cancelada."""
    async def ejecutar(*_, **__):
        try:
            await asyncio.sleep(5)
        except asyncio.CancelledError:
            cancelado.append(True)
            raise
    return ejecutar


def test_responde_dentro_del_plazo_y_cancela_el_lote(client, lotes, monkeypatch):
    monkeypatch.setattr(settings, "cron_plazo_respuesta_segundos", 0.2)
    cancelado = []
    monkeypatch.setattr(ingesta, "ejecutar_ingesta_lote", lento(cancelado))
    inicio = time.monotonic()
    r = client.post(RUTA, headers=autorizado())
    assert time.monotonic() - inicio < 2
    assert r.status_code == 200
    assert r.json() == {"pendiente": True, "motivo": "tiempo_turno_agotado"}
    assert cancelado == [True]


def test_cancela_compras_agiles_que_exceden_el_plazo(client, lotes, monkeypatch):
    monkeypatch.setattr(settings, "cron_plazo_respuesta_segundos", 0.2)
    monkeypatch.setattr(settings, "compras_agiles_automaticas", True)
    monkeypatch.setattr(cron, "SessionLocal", DbFalsa)
    cancelado = []
    monkeypatch.setattr(cron, "correr_lote_compras_agiles", lento(cancelado))
    r = client.post(RUTA, headers=autorizado())
    assert r.status_code == 200
    assert r.json() == {
        "procesados": 1, "errores": [],
        "compras_agiles": {"pendiente": True, "motivo": "tiempo_turno_agotado"},
    }
    assert cancelado == [True]
