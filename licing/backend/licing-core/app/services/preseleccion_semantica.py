"""Ranking semántico opcional. Solo embeddings; no genera resúmenes ni decide postular."""
import asyncio
from collections import OrderedDict
import hashlib
import math
import re
import time

import httpx

from .preseleccion import cargar_catalogo, textos_servicio


class SemanticaNoDisponible(RuntimeError):
    pass


_CACHE = OrderedDict()


def _vector(valores, dimensiones):
    if not isinstance(valores, list) or len(valores) != dimensiones:
        raise SemanticaNoDisponible("El proveedor devolvió dimensiones inesperadas.")
    if any(isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(x) for x in valores):
        raise SemanticaNoDisponible("El proveedor devolvió un vector inválido.")
    norma = math.sqrt(sum(x * x for x in valores))
    if norma == 0 or not math.isfinite(norma):
        raise SemanticaNoDisponible("El proveedor devolvió un vector sin información.")
    return [x / norma for x in valores]


class GeminiEmbeddings:
    """Adaptador acotado al endpoint de embeddings documentado; clave solo en el servidor."""
    def __init__(self, clave: str, *, modelo="gemini-embedding-001", dimensiones=768, transport=None):
        if not clave:
            raise SemanticaNoDisponible("Falta configurar PRESELECCION_GEMINI_API_KEY en el servidor.")
        if modelo != "gemini-embedding-001" or not 128 <= dimensiones <= 3072:
            raise ValueError("Configuración de embeddings no admitida.")
        self._clave = clave
        self.modelo, self.dimensiones, self.transport = modelo, dimensiones, transport

    async def embeddings(self, textos: list[str], tipo: str) -> list[list[float]]:
        if tipo not in {"RETRIEVAL_QUERY", "RETRIEVAL_DOCUMENT"}:
            raise ValueError("Tipo de embedding no admitido.")
        if len(textos) > 32 or any(not t.strip() or len(t) > 2000 for t in textos):
            raise ValueError("El lote semántico excede los límites de esta evaluación.")
        ahora, resultado, pendientes = time.monotonic(), {}, {}
        for i, texto in enumerate(textos):
            clave = (self.modelo, self.dimensiones, tipo, hashlib.sha256(texto.encode()).hexdigest())
            almacenado = _CACHE.get(clave)
            if almacenado and ahora - almacenado[0] < 1800:
                resultado[i] = almacenado[1]
                _CACHE.move_to_end(clave)
            else:
                pendientes.setdefault(clave, {"texto": texto, "indices": []})["indices"].append(i)
        if pendientes:
            entradas = list(pendientes.items())
            solicitudes = [{"model": f"models/{self.modelo}", "content": {"parts": [{"text": x[1]["texto"]}]},
                "embedContentConfig": {"taskType": tipo, "outputDimensionality": self.dimensiones}}
                for x in entradas]
            try:
                async with httpx.AsyncClient(timeout=httpx.Timeout(12.0, connect=4.0), transport=self.transport) as cliente:
                    respuesta = await cliente.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{self.modelo}:batchEmbedContents",
                        headers={"x-goog-api-key": self._clave}, json={"requests": solicitudes})
                    respuesta.raise_for_status()
                    cuerpo = respuesta.json()
            except (httpx.HTTPError, ValueError) as exc:
                raise SemanticaNoDisponible("No se pudo completar la consulta al proveedor de embeddings.") from None
            recibidos = cuerpo.get("embeddings") if isinstance(cuerpo, dict) else None
            if not isinstance(recibidos, list) or len(recibidos) != len(entradas):
                raise SemanticaNoDisponible("El proveedor devolvió un lote incompleto.")
            for (clave, entrada), recibido in zip(entradas, recibidos):
                v = _vector(recibido.get("values") if isinstance(recibido, dict) else None, self.dimensiones)
                _CACHE[clave] = (ahora, v)
                _CACHE.move_to_end(clave)
                for i in entrada["indices"]:
                    resultado[i] = v
            while len(_CACHE) > 128:
                _CACHE.popitem(last=False)
        return [resultado[i] for i in range(len(textos))]


def fragmentar_para_semantica(datos: dict) -> tuple[list[dict], bool]:
    fragmentos, parcial = [], False
    for campo in textos_servicio(datos):
        texto = re.sub(r"\s+", " ", campo["texto"]).strip()
        for inicio in range(0, len(texto), 1320):
            if len(fragmentos) == 8:
                parcial = True
                break
            fragmentos.append({"fuente": campo["fuente"], "texto": texto[inicio:inicio + 1500]})
        if parcial:
            break
    return fragmentos, parcial


async def evaluar_semantica(datos: dict, proveedor) -> dict:
    c = cargar_catalogo()
    perfiles = [{"id": g["id"], "tipo": "servicio", "texto": g["descripcion"]} for g in c["grupos"]
        if g["id"] in {"alojamiento", "salones", "alimentacion_asociada"}]
    perfiles += [{"id": g["id"], "tipo": "alternativa", "texto": g["descripcion"]}
        for g in c["perfiles_no_hoteleros"]]
    fragmentos, parcial = fragmentar_para_semantica(datos)
    if not fragmentos:
        return {"estado": "sin_texto", "requiere_calibracion": True, "ranking": []}
    # Presupuesto temporal propio: una llamada lenta nunca debe absorber toda la función de ingesta.
    try:
        async with asyncio.timeout(30):
            consultas = await proveedor.embeddings([p["texto"] for p in perfiles], "RETRIEVAL_QUERY")
            documentos = await proveedor.embeddings([f["texto"] for f in fragmentos], "RETRIEVAL_DOCUMENT")
    except TimeoutError:
        raise SemanticaNoDisponible("La evaluación semántica superó su tiempo disponible.") from None
    if len(consultas) != len(perfiles) or len(documentos) != len(fragmentos):
        raise SemanticaNoDisponible("La evaluación recibió un lote incompleto.")
    ranking = []
    for perfil, consulta in zip(perfiles, consultas):
        # Normaliza también adaptadores alternativos; no mezcla vectores de dimensiones diferentes.
        q = _vector(consulta, proveedor.dimensiones)
        puntajes = [max(-1.0, min(1.0, sum(a * b for a, b in zip(q, _vector(d, proveedor.dimensiones))))) for d in documentos]
        indice = max(range(len(puntajes)), key=puntajes.__getitem__)
        ranking.append({"perfil": perfil["id"], "tipo": perfil["tipo"],
            "similitud": round(puntajes[indice], 6), "fuente": fragmentos[indice]["fuente"],
            "fragmento_comparado": fragmentos[indice]["texto"]})
    return {"estado": "evaluada", "proveedor": "gemini", "modelo": proveedor.modelo,
        "dimensiones": proveedor.dimensiones, "metrica": "similitud_coseno", "cobertura": "parcial" if parcial else "textos_disponibles",
        "requiere_calibracion": True, "cambia_clasificacion": False,
        "nota": "Ordena afinidades para revisión. No es probabilidad ni aplica umbrales sin validar con el hotel.",
        "ranking": sorted(ranking, key=lambda x: x["similitud"], reverse=True)}
