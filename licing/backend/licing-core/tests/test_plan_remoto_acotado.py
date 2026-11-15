import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.services import compra_agil_preseleccion as ca, filtradas


def preparar(monkeypatch):
    filas = [SimpleNamespace(id=i, codigo_externo=f'100-{i}-COT26', raw_id=i+1000)
             for i in range(1, 306)]
    monkeypatch.setattr(ca, 'pendientes', lambda db, limite: [])
    db = Mock()
    db.execute.return_value.all.return_value = filas
    return db, filas


def test_reconciliacion_remota_usa_una_consulta_y_solo_recibe_codigos(monkeypatch):
    db, filas = preparar(monkeypatch)
    operar = AsyncMock(return_value={'codigos_pendientes': [filas[304].codigo_externo], 'total': 1})
    monkeypatch.setattr(filtradas, 'operar', operar)
    assert asyncio.run(ca.plan_pendientes(db)) == [305]
    operar.assert_awaited_once()
    op, datos = operar.call_args.args
    assert op == 'listar' and datos['solo_pendientes'] is True and datos['solo_firmas'] is True
    assert len(datos['codigos']) == 305 and len(datos['fuentes']) == 305
    assert datos['limite'] == 100


def test_catalogo_al_dia_no_repite_lecturas_paginadas(monkeypatch):
    db, _ = preparar(monkeypatch)
    operar = AsyncMock(return_value={'codigos_pendientes': [], 'total': 0})
    monkeypatch.setattr(filtradas, 'operar', operar)
    assert asyncio.run(ca.plan_pendientes(db)) == []
    operar.assert_awaited_once()


def test_compatibilidad_con_filtradas_anterior_solo_lee_firmas_una_vez(monkeypatch):
    db, filas = preparar(monkeypatch)
    # Una evaluación invalidada y otra oportunidad ausente siguen recuperándose.
    guardadas = [{'codigo_externo': f.codigo_externo, 'estado_seleccion': 'descartada'} for f in filas[:-1]]
    guardadas[100]['estado_seleccion'] = 'pendiente_evaluacion'
    operar = AsyncMock(return_value={'filas': guardadas})
    monkeypatch.setattr(filtradas, 'operar', operar)
    assert asyncio.run(ca.plan_pendientes(db)) == [101, 305]
    operar.assert_awaited_once()
