"""Consulta y registro de extracciones; todavía no ejecuta análisis documental."""
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import solo_rol, usuario_actual
from ..database import get_db
from ..models.documentacion import Documento, Extraccion, Fragmento, Prestacion, Requisito, PeriodoServicio
from ..models.licitacion import Licitacion
from ..services.documentacion import ExtraccionEntrada, como_dict, guardar_extraccion

router = APIRouter(prefix="/api/licitaciones", tags=["Documentación"])


@router.post("/{licitacion_id}/extracciones", dependencies=[Depends(solo_rol("administrador"))])
def registrar_extraccion(licitacion_id: int, entrada: ExtraccionEntrada, db: Session = Depends(get_db)):
    try:
        with db.begin_nested():
            identificador, creada = guardar_extraccion(db, licitacion_id, entrada)
        db.commit()
    except LookupError as exc:
        db.rollback()
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        db.rollback()
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        db.rollback()
        raise
    return {"extraccion_id": identificador, "creada": creada}


@router.get("/{licitacion_id}/documentos", dependencies=[Depends(usuario_actual)])
def documentos(licitacion_id: int, response: Response, limite: int = Query(50, ge=1, le=100),
               offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    if db.get(Licitacion, licitacion_id) is None:
        raise HTTPException(404, "No se encontró la licitación")
    filas = db.scalars(select(Documento).where(Documento.licitacion_id == licitacion_id)
        .order_by(Documento.id.desc()).offset(offset).limit(limite)).all()
    response.headers["Cache-Control"] = "no-store"
    return {"items": [como_dict(f) for f in filas], "limite": limite, "offset": offset}


@router.get("/{licitacion_id}/extracciones/{extraccion_id}", dependencies=[Depends(usuario_actual)])
def consultar_extraccion(licitacion_id: int, extraccion_id: int, response: Response,
                        incluir_texto: bool = False, db: Session = Depends(get_db)):
    fila = db.get(Extraccion, extraccion_id)
    if fila is None or fila.licitacion_id != licitacion_id:
        raise HTTPException(404, "No se encontró la extracción de esta licitación")
    salida = {"extraccion": como_dict(fila)}
    for nombre, modelo in (("fragmentos", Fragmento), ("prestaciones", Prestacion),
                           ("requisitos", Requisito), ("periodos", PeriodoServicio)):
        filas = db.scalars(select(modelo).where(modelo.extraccion_id == extraccion_id).order_by(modelo.id)).all()
        salida[nombre] = [como_dict(f) for f in filas]
    if not incluir_texto:
        for f in salida["fragmentos"]:
            f.pop("texto")
    response.headers["Cache-Control"] = "no-store"
    return salida
