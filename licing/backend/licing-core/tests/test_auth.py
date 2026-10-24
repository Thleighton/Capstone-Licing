import asyncio

import httpx
import pytest

from app import auth
from app.config import settings


@pytest.mark.parametrize("ruta", ["/api/licitaciones", "/api/licitaciones/1", "/api/dashboard", "/api/ingestas", "/api/clientes"])
def test_consultas_exigen_sesion(client, ruta):
    r = client.get(ruta)
    assert r.status_code == 401
    assert r.json() == {"error": "Debes iniciar sesión"}


@pytest.mark.parametrize("prefijo", ["/api/ingesta", "/ingesta"])
def test_ingesta_exige_sesion_y_rol(client, client_usuario, prefijo):
    # client_usuario es el mismo cliente, con un perfil que no es administrador.
    assert client_usuario.post(prefijo + "/licitaciones/lote/ejecutar").status_code == 403


def test_ingesta_sin_token(client):
    assert client.post("/api/ingesta/licitaciones/lote/ejecutar").status_code == 401


def test_config_solo_expone_configuracion_publica(client):
    r = client.get("/api/config")
    assert r.status_code == 200
    assert r.json() == {"USUARIOS_URL": settings.usuarios_url, "USUARIOS_KEY": settings.usuarios_anon_key}
    assert r.headers["cache-control"] == "no-store"
    assert "DATABASE" not in r.text and "MP_TICKET" not in r.text


def simular_supabase(monkeypatch, handler):
    cliente_original = httpx.AsyncClient
    monkeypatch.setattr(auth.httpx, "AsyncClient", lambda **kw: cliente_original(transport=httpx.MockTransport(handler), **kw))


def test_valida_token_perfil_y_reutiliza_validacion(monkeypatch):
    llamadas = []
    def responder(request):
        llamadas.append(request)
        assert request.headers["Authorization"] == "Bearer token-prueba"
        if request.url.path == "/auth/v1/user":
            return httpx.Response(200, json={"id": "u1"})
        assert request.url.params["id"] == "eq.u1"
        return httpx.Response(200, json=[{"id": "u1", "activo": True, "rol": "administrador"}])
    simular_supabase(monkeypatch, responder)
    perfil = asyncio.run(auth.perfil_desde_token("token-prueba"))
    assert perfil["rol"] == "administrador"
    assert asyncio.run(auth.perfil_desde_token("token-prueba")) == perfil
    assert len(llamadas) == 2


@pytest.mark.parametrize("activo", [False, None])
def test_rechaza_perfil_inactivo(client, monkeypatch, activo):
    def responder(request):
        return httpx.Response(200, json={"id": "u1"} if request.url.path == "/auth/v1/user" else [{"id": "u1", "activo": activo}])
    simular_supabase(monkeypatch, responder)
    assert client.get("/api/licitaciones", headers={"Authorization": "Bearer token"}).status_code == 403


def test_rechaza_token_expirado(client, monkeypatch):
    simular_supabase(monkeypatch, lambda request: httpx.Response(401, json={"msg": "expired"}))
    assert client.get("/api/licitaciones", headers={"Authorization": "Bearer token"}).status_code == 401


def test_fallo_supabase_no_expone_detalles(client, monkeypatch):
    simular_supabase(monkeypatch, lambda request: httpx.Response(500, text="detalle interno"))
    r = client.get("/api/licitaciones", headers={"Authorization": "Bearer token"})
    assert r.status_code == 503
    assert "detalle interno" not in r.text
