import pytest
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.auth import usuario_actual
from app.main import app
from app.models.documentacion import Documento, Extraccion, Fragmento, Prestacion, Requisito
from app.models.licitacion import Licitacion
from app.models.raw import RawMercadoPublico
from app.services.documentacion import ExtraccionEntrada, guardar_extraccion


def ejemplo():
    return {
        "documento": {"nombre": "Bases técnicas", "tipo": "bases", "url_origen": "https://www.mercadopublico.cl/bases/ejemplo.pdf", "version": "1"},
        "metodo": "revision_manual", "version_metodo": "1", "estado": "completa",
        "cobertura": {"paginas_totales": 1, "paginas_procesadas": [1]},
        "fragmentos": [{"orden": 1, "pagina_inicio": 1, "pagina_fin": 1, "tipo_seccion": "tecnica",
                        "texto": "Salón para 100 a 150 asistentes. Superficie mínima de 350 m². Santiago o Providencia. Se coordinará la fecha."}],
        "prestaciones": [{"clave": "salon", "tipo": "salon", "nombre": "Arriendo de salón", "fragmento_orden": 1, "estado_dato": "confirmado", "oferta_parcial": False}],
        "requisitos": [{"prestacion_clave": "salon", "tipo": "capacidad", "clave": "asistentes", "fragmento_orden": 1,
                        "estado_dato": "confirmado", "texto_original": "Salón para 100 a 150 asistentes.", "caracter": "obligatorio",
                        "valor_min": "100", "valor_max": "150", "unidad": "personas"},
                       {"prestacion_clave": "salon", "tipo": "ubicacion", "clave": "comunas", "fragmento_orden": 1,
                        "estado_dato": "confirmado", "texto_original": "Santiago o Providencia.", "caracter": "obligatorio",
                        "operador": "alguna_de", "parametros": {"comunas": ["Santiago", "Providencia"]}}],
        "periodos": [{"prestacion_clave": "salon", "fragmento_orden": 1, "estado_dato": "no_informado", "tipo": "evento", "precision": "por_coordinar"}],
    }


@pytest.mark.parametrize("cambio", [
    lambda x: x["requisitos"][0].update(fragmento_orden=99),
    lambda x: x["requisitos"][0].update(texto_original="Una exigencia inventada"),
    lambda x: x["requisitos"][0].update(prestacion_clave="otro"),
    lambda x: x["requisitos"][0].update(valor_min=151),
    lambda x: x["cobertura"].update(paginas_totales=2),
    lambda x: x["cobertura"].update(paginas_con_error=[1]),
    lambda x: x["documento"].update(url_origen="javascript:alert(1)"),
    lambda x: x["documento"].update(url_origen="https://www.mercadopublico.cl/api?ticket=secreto"),
    lambda x: x["periodos"][0].update(incluye_hora=True),
    lambda x: x.update(estado="error"),
])
def test_rechaza_extraccion_incoherente(cambio):
    datos = ejemplo()
    cambio(datos)
    with pytest.raises(ValidationError):
        ExtraccionEntrada.model_validate(datos)


def test_conserva_alternativas_desconocidos_y_evaluables():
    datos = ejemplo()
    datos["requisitos"][0].update(caracter="evaluable", ponderacion="5")
    entrada = ExtraccionEntrada.model_validate(datos)
    assert entrada.requisitos[0].caracter == "evaluable"
    assert entrada.requisitos[1].parametros["comunas"] == ["Santiago", "Providencia"]
    assert entrada.periodos[0].inicio_min is None
    assert entrada.prestaciones[0].confianza is None


def test_periodos_de_estadia_no_son_total_de_habitaciones():
    datos = ejemplo()
    datos["periodos"] = [{"prestacion_clave": "salon", "fragmento_orden": 1, "estado_dato": "confirmado", "tipo": "estadia", "precision": "exacta",
        "inicio_min": "2026-11-19T00:00:00", "inicio_max": "2026-11-19T00:00:00",
        "fin_min": "2026-11-29T00:00:00", "fin_max": "2026-11-29T00:00:00",
        "cantidad_min": 3, "cantidad_max": 3, "unidad": "habitaciones", "tipo_habitacion": "doble", "ocupantes_por_unidad": 2}]
    entrada = ExtraccionEntrada.model_validate(datos)
    assert entrada.periodos[0].cantidad_min == 3
    assert entrada.periodos[0].incluye_hora is False


def crear_licitacion(db, codigo="DOC-TEST"):
    raw = RawMercadoPublico(fuente="licitaciones", tipo_consulta="detalle_codigo", codigo_externo=codigo, respuesta={}, http_status=200)
    db.add(raw)
    db.flush()
    lic = Licitacion(codigo_externo=codigo, raw_id=raw.id)
    db.add(lic)
    db.flush()
    return lic


def test_registro_idempotente_y_versiones_preservadas(integration_db):
    db = integration_db
    lic = crear_licitacion(db)
    datos = ejemplo()
    primera, creada = guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(datos))
    segunda, repetida = guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(datos))
    assert creada and not repetida and primera == segunda
    assert db.scalar(select(func.count()).select_from(Requisito)) == 2
    datos["documento"]["version"] = "2"
    tercera, creada = guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(datos))
    assert creada and tercera != primera
    assert db.scalar(select(func.count()).select_from(Documento)) == 2
    assert db.scalar(select(func.count()).select_from(Extraccion)) == 2


def test_rechaza_reescribir_version_y_item_de_otra_licitacion(integration_db):
    db = integration_db
    lic = crear_licitacion(db)
    guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(ejemplo()))
    datos = ejemplo()
    datos["documento"]["nombre"] = "Cambio silencioso"
    with pytest.raises(ValueError, match="nueva versión"):
        with db.begin_nested():
            guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(datos))
    datos = ejemplo()
    datos["prestaciones"][0]["item_correlativo"] = 999
    with pytest.raises(ValueError, match="no pertenece"):
        guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(datos))


def test_fk_impide_evidencia_de_otra_licitacion(integration_db):
    db = integration_db
    lic = crear_licitacion(db)
    otra = crear_licitacion(db, "OTRA-DOC-TEST")
    eid, _ = guardar_extraccion(db, lic.id, ExtraccionEntrada.model_validate(ejemplo()))
    fid = db.scalar(select(Fragmento.id).where(Fragmento.extraccion_id == eid))
    with pytest.raises(IntegrityError):
        with db.begin_nested():
            db.add(Prestacion(licitacion_id=otra.id, extraccion_id=eid, fragmento_id=fid,
                estado_dato="confirmado", clave="incorrecta", tipo="salon", nombre="Incorrecta"))
            db.flush()


def test_api_guarda_y_consulta_sin_binarios(client, integration_db):
    db = integration_db
    lic = crear_licitacion(db)
    app.dependency_overrides[usuario_actual] = lambda: {"rol": "administrador"}
    r = client.post(f"/api/licitaciones/{lic.id}/extracciones", json=ejemplo())
    assert r.status_code == 200, r.text
    eid = r.json()["extraccion_id"]
    consulta = client.get(f"/api/licitaciones/{lic.id}/extracciones/{eid}")
    assert consulta.status_code == 200
    assert "texto" not in consulta.json()["fragmentos"][0]
    assert consulta.json()["requisitos"][0]["valor_min"] == "100"
    assert client.get(f"/api/licitaciones/{lic.id}/extracciones/{eid}?incluir_texto=true").json()["fragmentos"][0]["texto"]
    assert client.get(f"/api/licitaciones/{lic.id}/documentos").json()["items"][0]["url_origen"].startswith("https://")
    assert client.get(f"/api/licitaciones/{lic.id+999}/extracciones/{eid}").status_code == 404


def test_sin_permiso_no_registra(client_usuario):
    assert client_usuario.post("/api/licitaciones/1/extracciones", json=ejemplo()).status_code == 403


def test_rls_documentacion(integration_db):
    nombres = ["licitacion_documento", "licitacion_extraccion", "documento_fragmento", "licitacion_prestacion", "licitacion_requisito", "licitacion_periodo_servicio"]
    filas = integration_db.execute(text("SELECT relname, relrowsecurity FROM pg_class WHERE relnamespace='public'::regnamespace AND relname = ANY(:nombres)"), {"nombres": nombres}).all()
    assert len(filas) == len(nombres) and all(f[1] for f in filas)
