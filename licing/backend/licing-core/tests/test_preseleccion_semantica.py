import asyncio
import json

import httpx
import pytest

from app.services.preseleccion_semantica import (
    GeminiEmbeddings, SemanticaNoDisponible, _CACHE, evaluar_semantica, fragmentar_para_semantica,
)


@pytest.fixture(autouse=True)
def vaciar_cache():
    _CACHE.clear()
    yield
    _CACHE.clear()


def test_adaptador_valida_normaliza_y_reutiliza_embeddings_sin_generacion():
    solicitudes = []

    def responder(request):
        solicitudes.append(request)
        cuerpo = json.loads(request.content)
        assert request.headers["x-goog-api-key"] == "clave-de-prueba"
        assert ":batchEmbedContents" in str(request.url)
        assert "clave-de-prueba" not in str(request.url)
        assert cuerpo["requests"][0]["embedContentConfig"]["taskType"] == "RETRIEVAL_QUERY"
        return httpx.Response(200, json={"embeddings": [{"values": [3., 4.] + [0.] * 126} for _ in cuerpo["requests"]]})

    proveedor = GeminiEmbeddings("clave-de-prueba", dimensiones=128, transport=httpx.MockTransport(responder))
    a = asyncio.run(proveedor.embeddings(["Alojamiento", "Alojamiento"], "RETRIEVAL_QUERY"))
    b = asyncio.run(proveedor.embeddings(["Alojamiento"], "RETRIEVAL_QUERY"))
    assert a == [[.6, .8] + [0.] * 126] * 2
    assert b == a[:1] and len(solicitudes) == 1
    assert len(json.loads(solicitudes[0].content)["requests"]) == 1


@pytest.mark.parametrize("valores", [None, [1.], [0.] * 128, [float("nan")] * 128, [True] * 128])
def test_vectores_invalidos_no_se_presentan_como_similitud(valores):
    def responder(request):
        return httpx.Response(200, json={"embeddings": [{"values": valores}]})
    proveedor = GeminiEmbeddings("prueba", dimensiones=128, transport=httpx.MockTransport(responder))
    with pytest.raises(SemanticaNoDisponible):
        asyncio.run(proveedor.embeddings(["Texto"], "RETRIEVAL_DOCUMENT"))


def test_error_del_proveedor_no_expone_la_clave():
    proveedor = GeminiEmbeddings("secreto-no-exponer", dimensiones=128,
        transport=httpx.MockTransport(lambda r: httpx.Response(429, json={"error": "secreto-no-exponer"})))
    with pytest.raises(SemanticaNoDisponible) as error:
        asyncio.run(proveedor.embeddings(["Texto"], "RETRIEVAL_DOCUMENT"))
    assert "secreto-no-exponer" not in str(error.value)


def test_ranking_es_coseno_con_fuente_y_sin_umbral_de_aceptacion():
    class Proveedor:
        dimensiones, modelo = 2, "modelo-simulado"
        async def embeddings(self, textos, tipo):
            if tipo == "RETRIEVAL_QUERY":
                return [[1., 0.], [0., 1.], [-1., 0.], [0., -1.], [-1., -1.]]
            return [[1., 0.] for _ in textos]
    r = asyncio.run(evaluar_semantica({"descripcion": "Hospedaje para una delegación."}, Proveedor()))
    assert r["ranking"][0]["perfil"] == "alojamiento"
    assert r["ranking"][0]["similitud"] == 1.
    assert r["ranking"][0]["fuente"] == "descripcion"
    assert r["requiere_calibracion"] is True and r["cambia_clasificacion"] is False


def test_textos_largos_muestran_cobertura_parcial_y_excluyen_comprador():
    fragmentos, parcial = fragmentar_para_semantica({"descripcion": "texto " * 3000,
        "nombre_organismo": "Hotel en Santiago", "direccion_comprador": "Santiago"})
    assert parcial and len(fragmentos) == 8
    assert all(f["fuente"] == "descripcion" and len(f["texto"]) <= 1500 for f in fragmentos)


def test_sin_texto_no_consulta_proveedor():
    r = asyncio.run(evaluar_semantica({}, object()))
    assert r["estado"] == "sin_texto"
