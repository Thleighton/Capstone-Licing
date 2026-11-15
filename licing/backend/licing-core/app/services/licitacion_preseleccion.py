"""Cola acotada de licitaciones cuya evaluación aún no se ha confirmado en Filtradas."""
import json
from datetime import datetime

from sqlalchemy import String, cast, func, or_, select, text

from ..models.licitacion import Licitacion
from .preseleccion import CHILE, version_filtro

LIMITE_POR_LOTE = 100


def _pendientes():
    marca = Licitacion.preseleccion
    return or_(marca.is_(None), marca['version'].astext.is_distinct_from(version_filtro()),
        marca['raw_id'].astext.is_distinct_from(cast(Licitacion.raw_id, String)),
        marca['normalizacion_version'].astext.is_distinct_from(Licitacion.normalizacion_version))


def _disponibles():
    ahora = datetime.now(CHILE).replace(tzinfo=None)
    return (or_(Licitacion.fecha_cierre.is_(None), Licitacion.fecha_cierre > ahora),
        or_(Licitacion.codigo_estado.is_(None), Licitacion.codigo_estado.notin_([6, 7, 8, 18, 19])),
        func.lower(func.coalesce(Licitacion.estado, '')).notin_(
            ['cerrada', 'desierta', 'adjudicada', 'revocada', 'suspendida', 'cancelada']))


def pendientes(db, limite=LIMITE_POR_LOTE):
    return list(db.scalars(select(Licitacion.id).where(_pendientes(), *_disponibles())
        .order_by(Licitacion.id).limit(limite)))


def ids_disponibles(db):
    return list(db.scalars(select(Licitacion.id).where(*_disponibles()).order_by(Licitacion.id)))


def contar_pendientes(db):
    return db.scalar(select(func.count()).select_from(Licitacion).where(_pendientes(), *_disponibles()))


def registrar(db, parte, respuesta):
    """Confirma solo fuentes aceptadas y aún actuales. Una actualización SQL por grupo."""
    guardadas = {e['codigo']: e for e in respuesta.get('evaluadas', [])}
    filas = []
    for entrada in parte:
        d = entrada['datos']
        e = guardadas.get(d['codigo_externo'])
        if e:
            filas.append({'id': d['id'], 'raw_id': d['raw_id'], 'norm': d.get('normalizacion_version'),
                'marca': {'firma': entrada['hash_fuente'], 'version': version_filtro(), 'raw_id': d['raw_id'],
                    'normalizacion_version': d.get('normalizacion_version'), 'evaluacion_id': e['evaluacion_id']}})
    if not filas:
        return []
    actualizadas = set(db.scalars(text('''
        UPDATE public.licitacion AS l SET preseleccion=x.marca
        FROM jsonb_to_recordset(CAST(:filas AS jsonb)) AS x(id integer,raw_id integer,norm text,marca jsonb)
        WHERE l.id=x.id AND l.raw_id=x.raw_id AND l.normalizacion_version IS NOT DISTINCT FROM x.norm
        RETURNING l.id
    '''), {'filas': json.dumps(filas, ensure_ascii=False)}))
    return [guardadas[e['datos']['codigo_externo']] for e in parte
            if e['datos']['id'] in actualizadas]


async def evaluar_pendientes(db, *, limite=LIMITE_POR_LOTE, actor=None):
    from ..api.preseleccion import evaluar_lote
    ids = pendientes(db, limite)
    if not ids:
        return {'evaluadas': [], 'pendientes': 0}
    resultado = await evaluar_lote(db, ids, actor)
    return {**resultado, 'pendientes': contar_pendientes(db),
            'sin_guardar': len(ids) - len(resultado.get('evaluadas', []))}
