"""Contratos y fallos del filtro híbrido, sin descargas ni inferencia en la suite normal."""
from datetime import datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
import httpx
import pytest

from app.config import settings
from app.services import semantica_hotel as sem
from app.services.preseleccion import CHILE, evaluar_preseleccion


def scores(categoria, valor=0.99):
    return {k: valor if k == categoria else 0.01 for k in sem.HIPOTESIS}


def compra(**cambios):
    return {"codigo_externo": "123-4-LE26", "raw_id": 1, "nombre": "Arriendo de salón en Santiago",
            "descripcion": "Se requiere salón en Santiago para una jornada.", "items": [],
            "estado": "Publicada", "codigo_estado": 5, "fecha_cierre": "2099-12-01T12:00:00-03:00", **cambios}


def evaluar(**cambios):
    return evaluar_preseleccion(compra(**cambios), ahora=datetime(2026, 10, 25, 12, tzinfo=CHILE))


@pytest.fixture(autouse=True)
def limpiar_cache():
    sem._puntuar_remoto.cache_clear()
    yield
    sem._puntuar_remoto.cache_clear()


def activar(monkeypatch, categoria="salones"):
    monkeypatch.setattr(settings, "semantica_modo", "activa")
    monkeypatch.setattr(settings, "semantica_modelo_dir", "modelo-de-prueba")
    monkeypatch.setattr(sem, "_modelo", lambda _: SimpleNamespace(puntuar=lambda texto: (scores(categoria), False)))


def test_semantica_no_agrega_pilares_y_conserva_evidencia(monkeypatch):
    activar(monkeypatch)
    r = evaluar()
    assert r["clasificacion"] == "preseleccionada"
    assert set(r["criterios"]) == {"vigencia", "ubicacion", "pertinencia"}
    assert r["semantica"]["estado"] == "evaluada"
    p = r["criterios"]["pertinencia"]
    assert p["semantica"]["revision"] == sem.REVISION
    assert p["evidencias"][0]["evidencia"] == compra()["nombre"]
    assert p["evidencias"][1]["evidencia"] == compra()["descripcion"]


def test_obras_con_contexto_taller_se_descartan_por_servicio(monkeypatch):
    activar(monkeypatch, "obras")
    r = evaluar(nombre="Taller Fiscal Lazareto", descripcion="Mantención y reparación del taller fiscal")
    assert r["clasificacion"] == "descartada"
    assert r["pilar_decisivo"] == "pertinencia"


def test_sombra_registra_sin_cambiar_clasificacion(monkeypatch):
    activar(monkeypatch, "obras")
    monkeypatch.setattr(settings, "semantica_modo", "sombra")
    r = evaluar()
    assert r["clasificacion"] == "preseleccionada"
    assert r["semantica"]["resultado"] == "no_cumple"


@pytest.mark.parametrize("fallo", [OSError, RuntimeError, ImportError])
def test_fallo_de_modelo_no_convierte_una_duda_en_oportunidad(monkeypatch, fallo):
    activar(monkeypatch)
    def fallar(_):
        raise fallo("información privada que no debe aparecer en la respuesta")
    monkeypatch.setattr(sem, "_modelo", fallar)
    r = evaluar()
    assert r["clasificacion"] == "revision_manual"
    assert r["semantica"]["estado"] == "no_disponible"
    assert "privada" not in str(r)


def test_reglas_de_bienes_explicitos_no_se_anulan_por_un_error_del_modelo(monkeypatch):
    activar(monkeypatch, "alimentacion")
    monkeypatch.setattr(sem, "analizar", lambda _: pytest.fail("Los bienes explícitos no necesitan inferencia"))
    r = evaluar(nombre="Regulador", descripcion="Tensión de alimentación: 220V",
                items=[{"codigo_producto": "26101766", "descripcion": "Regulador para extractor"}])
    assert r["clasificacion"] == "descartada"
    assert r["semantica"]["estado"] == "omitida"


def test_similitud_hotelera_no_resuelve_compra_de_sabanas(monkeypatch):
    activar(monkeypatch, "alojamiento")
    r = evaluar(nombre="Compra de sábanas para habitaciones de hotel en Santiago")
    assert r["clasificacion"] == "revision_manual"


def test_modelo_no_concluyente_conserva_contratacion_explicita(monkeypatch):
    activar(monkeypatch)
    monkeypatch.setattr(sem, "_modelo", lambda _: SimpleNamespace(puntuar=lambda texto: ({k: 0.1 for k in sem.HIPOTESIS}, False)))
    r = evaluar()
    assert r["clasificacion"] == "preseleccionada"
    assert r["semantica"]["aplicacion"] == "contratacion_explicita"


def test_discrepancia_fuerte_entre_modelo_y_contrato_explicito_queda_en_revision(monkeypatch):
    activar(monkeypatch, "obras")
    assert evaluar()["clasificacion"] == "revision_manual"


def test_semantica_no_reabre_un_plazo_vencido(monkeypatch):
    activar(monkeypatch)
    monkeypatch.setattr(sem, "analizar", lambda _: pytest.fail("No inferir compras cerradas"))
    assert evaluar(fecha_cierre="2020-01-01T12:00:00-03:00")["clasificacion"] == "descartada"


def test_semantica_no_cambia_un_servicio_fuera_de_la_rm(monkeypatch):
    activar(monkeypatch)
    r = evaluar(nombre="Arriendo de salón en Antofagasta", descripcion="Arriendo de salón en Antofagasta para una jornada")
    assert r["clasificacion"] == "descartada"
    assert r["pilar_decisivo"] == "ubicacion"


def test_una_linea_hotelera_se_conserva_en_paquete_mixto():
    partes = [{"fuente": "items[0]", "texto": "Compra de equipo"}, {"fuente": "items[1]", "texto": "Salón para jornada"}]
    r = sem.resolver(partes, [scores("bienes"), scores("salones")])
    assert r["resultado"] == "cumple"
    assert r["categorias"] == ["salones"]


def test_desconocido_no_se_descarta_por_tener_otro_segmento_ajeno():
    r = sem.resolver([{"fuente": "items[0]", "texto": "Según bases"}, {"fuente": "items[1]", "texto": "Obras"}],
                     [{k: 0.1 for k in sem.HIPOTESIS}, scores("obras")])
    assert r["resultado"] == "sin_informacion"


@pytest.mark.parametrize("categoria", ["salones", "obras"])
def test_textos_recortados_nunca_deciden_automaticamente(categoria):
    r = sem.resolver([{"fuente": "cabecera", "texto": "Texto"}], [scores(categoria)], parcial=True)
    assert r["resultado"] == "sin_informacion"


@pytest.mark.parametrize("valor", [float("nan"), float("inf"), -0.1, 1.1, True])
def test_puntuaciones_invalidas_se_rechazan(valor):
    s = scores("salones"); s["salones"] = valor
    with pytest.raises(sem.SemanticaNoDisponible):
        sem.resolver([{"fuente": "cabecera", "texto": "Texto"}], [s])


def test_no_fusiona_categorias_genericas_ni_datos_del_comprador():
    partes, parcial = sem.segmentos({"nombre_organismo": "Hotel con catering", "direccion_entrega": "Salón hotel",
        "items": [{"nombre_producto": "Servicios de catering", "categoria": "Alojamiento"}]})
    assert partes == [] and parcial


def test_limita_segmentos_sin_confirmar_una_lectura_incompleta():
    partes, parcial = sem.segmentos({"descripcion": "a" * 60000})
    assert len(partes) == sem.MAX_SEGMENTOS and parcial
    assert all(len(p["texto"]) <= sem.TAMANO_TEXTO for p in partes)


def test_cambiar_modo_invalida_la_firma(monkeypatch):
    from app.api.preseleccion import firma_fuente
    firma = firma_fuente(compra())
    monkeypatch.setattr(settings, "semantica_modo", "activa")
    assert firma_fuente(compra()) != firma


def test_remoto_verifica_version_y_autentica_sin_exponer_token(monkeypatch):
    real_client = httpx.Client
    llamadas = []
    def responder(request):
        llamadas.append(request)
        assert request.headers["authorization"] == "Bearer token-de-prueba"
        return httpx.Response(200, json={"version": sem.VERSION, "revision": sem.REVISION,
            "puntuaciones": [scores("salones"), scores("salones")], "parcial": False})
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=httpx.MockTransport(responder), **kw))
    monkeypatch.setattr(settings, "semantica_modo", "activa")
    monkeypatch.setattr(settings, "semantica_url", "https://semantica.example.test/clasificar")
    monkeypatch.setattr(settings, "semantica_token", "token-de-prueba")
    assert evaluar()["clasificacion"] == "preseleccionada"
    assert evaluar()["clasificacion"] == "preseleccionada"
    assert len(llamadas) == 1


@pytest.mark.parametrize("respuesta", [
    {"version": "otra", "revision": sem.REVISION, "puntuaciones": [], "parcial": False},
    {"version": sem.VERSION, "revision": sem.REVISION, "puntuaciones": [], "parcial": False},
    {"version": sem.VERSION, "revision": sem.REVISION, "puntuaciones": [], "parcial": "no"},
])
def test_respuesta_remota_incompatible_no_se_acepta(monkeypatch, respuesta):
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=respuesta)), **kw))
    monkeypatch.setattr(settings, "semantica_modo", "activa")
    monkeypatch.setattr(settings, "semantica_url", "https://semantica.example.test/clasificar")
    monkeypatch.setattr(settings, "semantica_token", "token-de-prueba")
    r = evaluar()
    assert r["clasificacion"] == "revision_manual"
    assert r["semantica"]["estado"] == "no_disponible"


def test_worker_privado_y_limites_de_entrada(monkeypatch):
    from app import semantica_api as worker
    monkeypatch.setattr(worker.settings, "semantica_token", "token-de-prueba")
    with TestClient(worker.app) as client:
        assert client.post("/clasificar", json={"textos": ["Hotel"]}).status_code == 401
        assert client.post("/clasificar", headers={"Authorization": "Bearer token-de-prueba"},
                           json={"textos": ["x" * (sem.TAMANO_TEXTO + 1)]}).status_code == 422


def test_worker_necesita_token_configurado(monkeypatch):
    from app import semantica_api as worker
    monkeypatch.setattr(worker.settings, "semantica_token", "")
    with TestClient(worker.app) as client:
        assert client.post("/clasificar", json={"textos": ["Hotel"]}).status_code == 503


def test_worker_devuelve_version_y_puntuaciones_autenticadas(monkeypatch):
    from app import semantica_api as worker
    monkeypatch.setattr(worker.settings, "semantica_token", "token-de-prueba")
    monkeypatch.setattr(worker.settings, "semantica_modelo_dir", "modelo-de-prueba")
    monkeypatch.setattr(worker, "_modelo", lambda _: SimpleNamespace(puntuar=lambda texto: (scores("salones"), False)))
    with TestClient(worker.app) as client:
        response = client.post("/clasificar", headers={"Authorization": "Bearer token-de-prueba"}, json={"textos": ["Salón"]})
    assert response.status_code == 200
    assert response.json() == {"version": sem.VERSION, "revision": sem.REVISION, "puntuaciones": [scores("salones")], "parcial": False}


def test_compra_agil_reintenta_semantica_no_disponible():
    from app.services.compra_agil_preseleccion import _registrar
    escrituras = []
    db = SimpleNamespace(execute=lambda query: escrituras.append(query.compile().params))
    entrada = {"datos": {"id": 1, "raw_id": 2, "codigo_externo": "1-1-COT26"}, "hash_fuente": "pendiente",
               "resultado": {"clasificacion": "revision_manual", "evaluado_en": "ahora", "semantica": {"estado": "no_disponible"}}}
    _registrar(db, [entrada], {"evaluadas": [{"codigo": "1-1-COT26", "evaluacion_id": 1}]}, "version-actual")
    assert escrituras[0]["preseleccion"]["version"] == "pendiente:version-actual"


def test_ingesta_guarda_progreso_antes_de_clasificar_todo_el_lote(monkeypatch):
    import asyncio
    from unittest.mock import AsyncMock
    from app.services import compra_agil_preseleccion as ca
    orden = []
    def evaluar_dato(datos):
        orden.append("evaluar")
        if len(orden) > 1:
            raise asyncio.CancelledError()
        return {"semantica": {"estado": "evaluada"}}
    monkeypatch.setattr(ca, "evaluar", evaluar_dato)
    monkeypatch.setattr(ca, "firma", lambda _: "hash")
    monkeypatch.setattr(ca, "monotonic", iter([0, 2, 2]).__next__)
    monkeypatch.setattr(ca, "_registrar", lambda *args: orden.append("registrar") or [1])
    monkeypatch.setattr(ca.filtradas, "operar", AsyncMock(return_value={"evaluadas": []}))
    db = SimpleNamespace(commit=lambda: orden.append("commit"))
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(ca._evaluar_con_semantica(db, {"1": {}, "2": {}}, None, "version"))
    assert orden[:3] == ["evaluar", "registrar", "commit"]
