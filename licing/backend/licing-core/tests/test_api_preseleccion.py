from datetime import datetime, timedelta, timezone

from app.api import preseleccion
from app.auth import usuario_actual
from app.main import app


def entradas(db, ids):
    return {i: {"id": i, "codigo_externo": f"100-{i}-LE26", "raw_id": 12, "estado": "Publicada",
        "codigo_estado": 5, "fecha_cierre": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
        "nombre": "Arriendo de salón en Santiago", "items": [], "fuente_consultada_en": "2026-10-23T12:00:00Z"} for i in ids}


def test_rutas_requieren_sesion(client):
    assert client.get("/api/preseleccion/catalogo").status_code == 401
    assert client.post("/api/preseleccion/evaluar", json={"licitacion_ids": [1]}).status_code == 401


def test_catalogo_disponible_a_usuario_activo(client_usuario):
    r = client_usuario.get("/api/preseleccion/catalogo")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert len(r.json()["comunas_rm"]) == 52


def test_evalua_licitaciones_guardadas_sin_escribir_ni_llamar_modelos(client_usuario, monkeypatch):
    monkeypatch.setattr(preseleccion, "cargar_entradas", entradas)
    monkeypatch.setattr(preseleccion, "GeminiEmbeddings", lambda *a, **k: (_ for _ in ()).throw(AssertionError("No debe consultar modelos")))
    r = client_usuario.post("/api/preseleccion/evaluar", json={"licitacion_ids": [1, 2]})
    assert r.status_code == 200
    assert r.json()["conteos"]["preseleccionada"] == 2
    assert r.json()["persistido"] is False and r.json()["modo"] == "simulacion"


def test_lotes_invalidos_se_rechazan(client_usuario):
    for ids in ([], [1, 1], [True], ["1"], list(range(1, 52))):
        assert client_usuario.post("/api/preseleccion/evaluar", json={"licitacion_ids": ids}).status_code == 422


def test_faltantes_no_generan_resultados_inventados(client_usuario, monkeypatch):
    monkeypatch.setattr(preseleccion, "cargar_entradas", lambda *a: {})
    assert client_usuario.post("/api/preseleccion/evaluar", json={"licitacion_ids": [12]}).status_code == 404


def test_semantica_requiere_administrador_y_clave_servidor(client_usuario, monkeypatch):
    monkeypatch.setattr(preseleccion, "cargar_entradas", entradas)
    assert client_usuario.post("/api/preseleccion/evaluar", json={"licitacion_ids": [1], "incluir_semantica": True}).status_code == 403
    app.dependency_overrides[usuario_actual] = lambda: {"id": "admin", "rol": "administrador", "activo": True}
    monkeypatch.setattr(preseleccion.settings, "preseleccion_gemini_api_key", None)
    r = client_usuario.post("/api/preseleccion/evaluar", json={"licitacion_ids": [1], "incluir_semantica": True})
    assert r.status_code == 503 and "PRESELECCION_GEMINI_API_KEY" in r.json()["error"]


def test_lote_semantico_tiene_limite_propio(client_usuario):
    r = client_usuario.post("/api/preseleccion/evaluar", json={"licitacion_ids": [1, 2, 3, 4], "incluir_semantica": True})
    assert r.status_code == 422
