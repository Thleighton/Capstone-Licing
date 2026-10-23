"""Evaluación de prueba sobre licitaciones existentes: no persiste ni cambia la ingesta."""
import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import usuario_actual
from ..config import settings
from ..database import get_db
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem
from ..models.raw import RawMercadoPublico
from ..services.preseleccion import cargar_catalogo, evaluar_preseleccion
from ..services.preseleccion_semantica import GeminiEmbeddings, SemanticaNoDisponible, evaluar_semantica

router = APIRouter(prefix="/api/preseleccion", tags=["Preselección"], dependencies=[Depends(usuario_actual)])


class EvaluacionEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid")
    licitacion_ids: list[Annotated[int, Field(strict=True, gt=0)]] = Field(min_length=1, max_length=50)
    incluir_semantica: bool = False

    @field_validator("licitacion_ids")
    @classmethod
    def sin_duplicados(cls, valor):
        if len(valor) != len(set(valor)):
            raise ValueError("No repitas identificadores en el lote")
        return valor

    @model_validator(mode="after")
    def lote_semantico_acotado(self):
        if self.incluir_semantica and len(self.licitacion_ids) > 3:
            raise ValueError("La prueba semántica admite hasta tres licitaciones por solicitud")
        return self


def cargar_entradas(db: Session, ids: list[int]) -> dict:
    filas = db.execute(select(Licitacion, RawMercadoPublico.consultado_en).join(
        RawMercadoPublico, RawMercadoPublico.id == Licitacion.raw_id).where(Licitacion.id.in_(ids))).all()
    items = db.scalars(select(LicitacionItem).where(LicitacionItem.licitacion_id.in_(ids))
        .order_by(LicitacionItem.licitacion_id, LicitacionItem.correlativo)).all()
    entradas = {}
    for licitacion, consultado in filas:
        datos = {k: getattr(licitacion, k) for k in ("id", "codigo_externo", "raw_id", "nombre", "descripcion",
            "estado", "codigo_estado", "fecha_cierre", "direccion_entrega", "direccion_visita")}
        datos.update(items=[], fuente_consultada_en=consultado.isoformat())
        entradas[licitacion.id] = datos
    for item in items:
        if item.licitacion_id in entradas:
            entradas[item.licitacion_id]["items"].append({k: getattr(item, k) for k in
                ("correlativo", "nombre_producto", "descripcion", "codigo_categoria", "categoria")})
    return entradas


@router.get("/catalogo")
def catalogo(response: Response):
    response.headers["Cache-Control"] = "no-store"
    return cargar_catalogo()


@router.post("/evaluar")
async def evaluar(entrada: EvaluacionEntrada, response: Response, usuario: dict = Depends(usuario_actual),
                  db: Session = Depends(get_db)):
    if entrada.incluir_semantica and usuario.get("rol") != "administrador":
        raise HTTPException(403, "La prueba con el proveedor de embeddings requiere un administrador")
    entradas = cargar_entradas(db, entrada.licitacion_ids)
    faltantes = [i for i in entrada.licitacion_ids if i not in entradas]
    if faltantes:
        raise HTTPException(404, "No se encontraron todas las licitaciones solicitadas")
    resultados = []
    proveedor = None
    try:
        async with asyncio.timeout(40):
            for identificador in entrada.licitacion_ids:
                datos = entradas[identificador]
                resultado = evaluar_preseleccion(datos)
                resultado.update(licitacion_id=identificador, fuente_consultada_en=datos["fuente_consultada_en"])
                if entrada.incluir_semantica and resultado["clasificacion"] != "descartada":
                    if proveedor is None:
                        clave = settings.preseleccion_gemini_api_key
                        proveedor = GeminiEmbeddings(clave.get_secret_value() if clave else "",
                            dimensiones=settings.preseleccion_embedding_dimensiones)
                    resultado["semantica"] = await evaluar_semantica(datos, proveedor)
                elif entrada.incluir_semantica:
                    resultado["semantica"] = {"estado": "omitida_por_vigencia_o_ubicacion"}
                resultados.append(resultado)
    except SemanticaNoDisponible as exc:
        raise HTTPException(503, str(exc)) from None
    except TimeoutError:
        raise HTTPException(503, "El lote superó su tiempo disponible; reduce la cantidad solicitada") from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    response.headers["Cache-Control"] = "no-store"
    return {"modo": "simulacion", "persistido": False, "total": len(resultados),
        "conteos": {estado: sum(r["clasificacion"] == estado for r in resultados)
            for estado in ("preseleccionada", "revision_manual", "descartada")}, "items": resultados}
