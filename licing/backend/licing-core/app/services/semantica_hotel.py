"""Clasificación NLI real, separada de las reglas y limitada al servicio solicitado."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path
from threading import Lock

VERSION = "nli-hotel-1"
MODELO = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"
REVISION = "8adb042d524ecd5c26d3e3ba0e3fbcf7e2d0864c"
HASH_MODELO = "7d39629484bdad052176a0cff26ffe408d8c2b69c7abd242716fee320badd661"
ARTEFACTOS = {
    "model.onnx": HASH_MODELO,
    "config.json": "4e4430c95100d613df80fa01276f231931e1b535557cf62fbb3cc50323e50cca",
    "tokenizer.json": "3aca3ce69a0a35aeb144a52c4f1d41c4246b8785f8f398315cc8fb6b24057810",
}
HIPOTESIS = {
    "alojamiento": "Se solicita hospedaje para personas en habitaciones de hotel.",
    "salones": "Se solicita el arriendo de un salón para celebrar un evento.",
    "alimentacion": "Se solicita comida preparada para alimentar a personas.",
    "obras": "Se solicita reparar o mantener un edificio.",
    "bienes": "Se solicita comprar productos físicos.",
    "informatica": "Se solicitan servicios de informática.",
    "transporte": "Se solicita transportar personas o bienes.",
    "aseo": "Se solicita limpiar instalaciones.",
    "auditoria": "Se solicita realizar una auditoría.",
    "capacitacion": "Se solicita un relator para impartir un curso.",
}
HOTEL = {"alojamiento", "salones", "alimentacion"}
MAX_SEGMENTOS = 32
TAMANO_TEXTO = 900
UMBRAL = 0.90
MARGEN = 0.20


class SemanticaNoDisponible(RuntimeError):
    pass


def firma_configuracion():
    from ..config import settings
    if settings.semantica_modo == "desactivada":
        return "desactivada"
    return f"{VERSION}|{REVISION}|{settings.semantica_modo}"


class ModeloNLI:
    def __init__(self, directorio):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        ruta = Path(directorio)
        for nombre, esperado in ARTEFACTOS.items():
            with (ruta / nombre).open("rb") as archivo:
                if hashlib.file_digest(archivo, "sha256").hexdigest() != esperado:
                    raise ValueError("El modelo o tokenizador no coincide con el artefacto validado")
        config = json.loads((ruta / "config.json").read_text(encoding="utf-8"))
        if config.get("id2label") != {"0": "entailment", "1": "neutral", "2": "contradiction"}:
            raise ValueError("Las etiquetas NLI no coinciden con el modelo fijado")
        self.np = np
        self.tokenizador = Tokenizer.from_file(str(ruta / "tokenizer.json"))
        self.tokenizador.enable_truncation(max_length=384, strategy="only_first")
        self.tokenizador.enable_padding(pad_id=config["pad_token_id"], pad_token="[PAD]")
        opciones = ort.SessionOptions()
        opciones.intra_op_num_threads = 2
        opciones.inter_op_num_threads = 1
        self.sesion = ort.InferenceSession(str(ruta / "model.onnx"), sess_options=opciones,
                                           providers=["CPUExecutionProvider"])
        self.lock = Lock()

    @lru_cache(maxsize=2048)
    def puntuar(self, texto):
        # Tokenizador y sesión compartidos sin inferencias concurrentes que saturen CPU.
        with self.lock:
            codigos = self.tokenizador.encode_batch([(texto, h) for h in HIPOTESIS.values()])
            campos = {"input_ids": "ids", "attention_mask": "attention_mask", "token_type_ids": "type_ids"}
            entrada = {x.name: self.np.array([getattr(c, campos[x.name]) for c in codigos], dtype=self.np.int64)
                       for x in self.sesion.get_inputs()}
            logits = self.sesion.run(None, entrada)[0]
        if not self.np.isfinite(logits).all() or logits.shape != (len(HIPOTESIS), 3):
            raise SemanticaNoDisponible("Salida inválida del modelo NLI")
        exp = self.np.exp(logits - logits.max(axis=1, keepdims=True))
        probabilidades = exp / exp.sum(axis=1, keepdims=True)
        # Incluye neutral: estos puntajes NO son probabilidades calibradas de negocio.
        return {k: float(v) for k, v in zip(HIPOTESIS, probabilidades[:, 0])}, any(c.overflowing for c in codigos)


@lru_cache(maxsize=1)
def _modelo(directorio):
    return ModeloNLI(directorio)


def segmentos(datos):
    """Cabecera e ítems concretos; el organismo y sus domicilios no son el objeto comprado."""
    partes, parcial = [], False
    # No concatenar el título repetido con la descripción: se evalúan como evidencias
    # distintas de la misma cabecera. Las líneas conservan su identidad.
    unidades = [(k, datos.get(k, "") or "", False) for k in ("nombre", "descripcion")]
    for n, item in enumerate(datos.get("items") or []):
        texto = item.get("descripcion") or ""
        # Un nombre de categoría UNSPSC sin descripción no prueba una contratación.
        unidades.append((f"items[{n}].descripcion", texto, not bool(texto.strip())))
    for fuente, texto, incompleta in unidades:
        if incompleta:
            parcial = True
        for inicio in range(0, len(texto), TAMANO_TEXTO - 100):
            trozo = texto[inicio:inicio + TAMANO_TEXTO].strip()
            if not trozo:
                continue
            if len(partes) >= MAX_SEGMENTOS:
                return partes, True
            partes.append({"fuente": fuente, "texto": trozo})
            if inicio + TAMANO_TEXTO >= len(texto):
                break
    return partes, parcial


def resolver(partes, puntuaciones, parcial=False):
    """Sin evidencia hotelera suficiente, una duda nunca equivale a oportunidad."""
    if len(partes) != len(puntuaciones):
        raise SemanticaNoDisponible("Faltan puntuaciones de segmentos")
    evidencias, negativas, desconocidas = [], [], []
    for parte, scores in zip(partes, puntuaciones):
        if set(scores) != set(HIPOTESIS) or any(type(v) not in (float, int) or not math.isfinite(v) or not 0 <= v <= 1 for v in scores.values()):
            raise SemanticaNoDisponible("Puntuaciones semánticas inválidas")
        positivo = max(HOTEL, key=scores.get)
        negativo = max(set(HIPOTESIS) - HOTEL, key=scores.get)
        detalle = {"fuente": parte["fuente"], "evidencia": parte["texto"],
                   "categoria": max(scores, key=scores.get),
                   "puntuaciones": {k: round(v, 4) for k, v in scores.items()}}
        # Un paquete puede incluir un salón y capacitación o transporte simultáneamente.
        # Las reglas posteriores conservan las dudas explícitas de bienes y negaciones.
        if scores[positivo] >= UMBRAL:
            detalle["categorias"] = [k for k in sorted(HOTEL) if scores[k] >= UMBRAL]
            evidencias.append(detalle)
        elif scores[negativo] >= UMBRAL and scores[negativo] - scores[positivo] >= MARGEN:
            negativas.append(detalle)
        else:
            desconocidas.append(detalle)
    def unidad(e):
        return e["fuente"].split(".")[0] if e["fuente"].startswith("items[") else "cabecera"
    unidades = {unidad(p) for p in partes}
    # El título general no es una línea adicional cuando hay ítems concretos.
    requeridas = {u for u in unidades if u.startswith("items[")} or unidades
    negativas_confirmadas = {unidad(e) for e in negativas} - {unidad(e) for e in evidencias}
    if not parcial and evidencias:
        resultado, motivo = "cumple", "Se identifica contratación de servicios del hotel: " + ", ".join(sorted({c for e in evidencias for c in e["categorias"]})) + "."
    elif not parcial and requeridas and requeridas <= negativas_confirmadas:
        resultado, motivo = "no_cumple", "El objeto solicitado corresponde a " + ", ".join(sorted({e["categoria"] for e in negativas})) + "; no se identifica contratación de servicios del hotel."
    else:
        resultado, motivo = "sin_informacion", "El análisis semántico no confirma el servicio con suficiente claridad; requiere revisión."
    return {"resultado": resultado, "motivo": motivo, "parcial": parcial,
            "categorias": sorted({c for e in evidencias for c in e["categorias"]}),
            "evidencias": (evidencias + negativas + desconocidas)[:12]}


@lru_cache(maxsize=256)
def _puntuar_remoto(url, token, timeout, textos):
    import httpx
    if not token:
        raise SemanticaNoDisponible("Falta la credencial del servicio semántico")
    with httpx.Client(timeout=timeout, follow_redirects=False) as cliente:
        respuesta = cliente.post(url, headers={"Authorization": "Bearer " + token}, json={"textos": list(textos)})
        respuesta.raise_for_status()
        datos = respuesta.json()
    if datos.get("version") != VERSION or datos.get("revision") != REVISION:
        raise SemanticaNoDisponible("El servicio semántico tiene otra versión")
    return datos["puntuaciones"], datos["parcial"]


def analizar(datos):
    from ..config import settings
    modo = settings.semantica_modo
    base = {"estado": "pendiente" if modo == "desactivada" else "evaluada", "modo": modo,
            "version": VERSION, "modelo": MODELO, "revision": REVISION}
    if modo == "desactivada":
        return {**base, "motivo": "El componente semántico está desactivado."}
    partes, parcial = segmentos(datos)
    if not partes:
        return {**base, **resolver([], [], parcial)}
    try:
        if settings.semantica_url:
            scores, recortada = deepcopy(_puntuar_remoto(settings.semantica_url, settings.semantica_token,
                settings.semantica_timeout_segundos, tuple(p["texto"] for p in partes)))
            if type(recortada) is not bool:
                raise ValueError("Indicador de truncación inválido")
        elif settings.semantica_modelo_dir:
            calculos = [_modelo(settings.semantica_modelo_dir).puntuar(p["texto"]) for p in partes]
            scores, recortada = [c[0] for c in calculos], any(c[1] for c in calculos)
        else:
            raise SemanticaNoDisponible("Falta configurar el modelo local o el servicio semántico")
        return {**base, **resolver(partes, scores, parcial or recortada)}
    except Exception as exc:
        # El fallo se registra sin credenciales, URL privada ni contenido de excepciones HTTP.
        return {**base, "estado": "no_disponible", "resultado": "sin_informacion",
                "motivo": "No se pudo completar el análisis semántico; requiere revisión.",
                "error_tipo": type(exc).__name__, "evidencias": []}
