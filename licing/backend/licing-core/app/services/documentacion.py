"""Registro transaccional de texto y hechos extraídos por un proceso externo.

No descarga URLs, no recibe binarios, no llama a un LLM y no clasifica oportunidades.
"""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from typing import Literal
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, NaiveDatetime, field_validator, model_validator
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ..models.documentacion import Documento, Extraccion, Fragmento, Prestacion, Requisito, PeriodoServicio
from ..models.licitacion import Licitacion
from ..models.licitacion_item import LicitacionItem


class Entrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)


class DocumentoEntrada(Entrada):
    nombre: str = Field(min_length=1, max_length=500)
    tipo: Literal["bases", "anexo", "aclaracion", "modificacion", "otro"]
    url_origen: str = Field(min_length=1, max_length=1500)
    version: str = Field(min_length=1, max_length=100)
    huella_archivo: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    fecha_fuente: AwareDatetime | None = None

    @field_validator("url_origen")
    @classmethod
    def url_publica(cls, valor):
        url = urlsplit(valor)
        if url.scheme != "https" or not url.hostname or url.username or url.password:
            raise ValueError("Usa una URL pública HTTPS sin credenciales")
        if {k.lower() for k in parse_qs(url.query)} & {"ticket", "token", "access_token", "apikey", "api_key"}:
            raise ValueError("No guardes credenciales de API en la URL documental")
        return valor


class Cobertura(Entrada):
    paginas_totales: int = Field(ge=1, le=10000)
    paginas_procesadas: list[int] = Field(default_factory=list, max_length=10000)
    paginas_con_error: list[int] = Field(default_factory=list, max_length=10000)
    observaciones: str | None = Field(default=None, max_length=5000)

    @model_validator(mode="after")
    def paginas_validas(self):
        for lista in (self.paginas_procesadas, self.paginas_con_error):
            if len(lista) != len(set(lista)) or any(p < 1 or p > self.paginas_totales for p in lista):
                raise ValueError("La cobertura contiene páginas repetidas o fuera del documento")
        if set(self.paginas_procesadas) & set(self.paginas_con_error):
            raise ValueError("Una página no puede estar procesada y con error a la vez")
        return self


class FragmentoEntrada(Entrada):
    orden: int = Field(gt=0)
    pagina_inicio: int = Field(gt=0)
    pagina_fin: int = Field(gt=0)
    seccion: str | None = Field(default=None, max_length=500)
    tipo_seccion: Literal["objeto", "tecnica", "administrativa", "evaluacion", "formulario", "aclaracion", "otra"]
    texto: str = Field(min_length=1, max_length=100000)
    requiere_ocr: bool | None = None


class EvidenciaEntrada(Entrada):
    fragmento_orden: int = Field(gt=0)
    estado_dato: Literal["confirmado", "no_informado", "ambiguo", "contradictorio"]
    confianza: Decimal | None = Field(default=None, ge=0, le=1)


class PrestacionEntrada(EvidenciaEntrada):
    clave: str = Field(min_length=1, max_length=100)
    tipo: str = Field(min_length=1, max_length=60)
    nombre: str = Field(min_length=1, max_length=500)
    descripcion: str | None = Field(default=None, max_length=5000)
    item_correlativo: int | None = Field(default=None, gt=0)
    modalidad: str | None = Field(default=None, max_length=1000)
    oferta_parcial: bool | None = None
    grupo_servicios: str | None = Field(default=None, max_length=200)
    adjudicacion: str | None = Field(default=None, max_length=1000)


class RequisitoEntrada(EvidenciaEntrada):
    prestacion_clave: str | None = Field(default=None, max_length=100)
    tipo: str = Field(min_length=1, max_length=60)
    clave: str = Field(min_length=1, max_length=100)
    texto_original: str = Field(min_length=1, max_length=10000)
    caracter: Literal["obligatorio", "evaluable", "condicional", "no_exigido", "no_indicado"]
    operador: str | None = Field(default=None, max_length=40)
    valor_texto: str | None = Field(default=None, max_length=5000)
    valor_min: Decimal | None = None
    valor_max: Decimal | None = None
    unidad: str | None = Field(default=None, max_length=100)
    alcance: str | None = Field(default=None, max_length=1000)
    grupo_alternativa: str | None = Field(default=None, max_length=200)
    condicion: str | None = Field(default=None, max_length=5000)
    excepciones: str | None = Field(default=None, max_length=5000)
    ponderacion: Decimal | None = Field(default=None, ge=0, le=100)
    parametros: dict | None = None

    @model_validator(mode="after")
    def rango_valido(self):
        if self.valor_min is not None and self.valor_max is not None and self.valor_min > self.valor_max:
            raise ValueError("El mínimo de un requisito supera su máximo")
        return self


class PeriodoEntrada(EvidenciaEntrada):
    prestacion_clave: str = Field(min_length=1, max_length=100)
    tipo: Literal["evento", "montaje", "desmontaje", "estadia", "otro"]
    precision: Literal["exacta", "intervalo", "por_coordinar", "no_informada"]
    inicio_min: NaiveDatetime | None = None
    inicio_max: NaiveDatetime | None = None
    fin_min: NaiveDatetime | None = None
    fin_max: NaiveDatetime | None = None
    zona_horaria: str | None = Field(default=None, max_length=60)
    incluye_hora: bool = False
    cantidad_min: Decimal | None = Field(default=None, ge=0)
    cantidad_max: Decimal | None = Field(default=None, ge=0)
    unidad: str | None = Field(default=None, max_length=100)
    tipo_habitacion: str | None = Field(default=None, max_length=100)
    ocupantes_por_unidad: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def coherencia(self):
        for menor, mayor in ((self.inicio_min, self.inicio_max), (self.fin_min, self.fin_max),
                              (self.inicio_min, self.fin_min), (self.cantidad_min, self.cantidad_max)):
            if menor is not None and mayor is not None and menor > mayor:
                raise ValueError("El período contiene un rango invertido")
        if self.precision == "exacta" and (self.inicio_min is None or self.inicio_max != self.inicio_min or self.fin_min != self.fin_max):
            raise ValueError("Un período exacto necesita un inicio y extremos coincidentes")
        fechas = (self.inicio_min, self.inicio_max, self.fin_min, self.fin_max)
        if not self.incluye_hora and any(f and (f.hour or f.minute or f.second or f.microsecond) for f in fechas):
            raise ValueError("Una fecha sin hora no debe contener una hora inferida")
        if self.incluye_hora and not self.zona_horaria:
            raise ValueError("Las horas locales necesitan zona horaria")
        if self.zona_horaria:
            try:
                ZoneInfo(self.zona_horaria)
            except (ValueError, KeyError) as exc:
                raise ValueError("Zona horaria desconocida") from exc
        return self


class ExtraccionEntrada(Entrada):
    documento: DocumentoEntrada
    metodo: str = Field(min_length=1, max_length=100)
    version_metodo: str = Field(min_length=1, max_length=100)
    estado: Literal["pendiente", "completa", "parcial", "error"]
    cobertura: Cobertura
    fragmentos: list[FragmentoEntrada] = Field(default_factory=list, max_length=1000)
    prestaciones: list[PrestacionEntrada] = Field(default_factory=list, max_length=100)
    requisitos: list[RequisitoEntrada] = Field(default_factory=list, max_length=1000)
    periodos: list[PeriodoEntrada] = Field(default_factory=list, max_length=500)

    @model_validator(mode="after")
    def referencias_validas(self):
        fragmentos = {f.orden: f for f in self.fragmentos}
        claves = {p.clave for p in self.prestaciones}
        if len(fragmentos) != len(self.fragmentos) or len(claves) != len(self.prestaciones):
            raise ValueError("Hay fragmentos o prestaciones repetidos")
        if sum(len(f.texto) for f in self.fragmentos) > 1000000:
            raise ValueError("La extracción supera un millón de caracteres; registra un lote parcial con su cobertura")
        procesadas = set(self.cobertura.paginas_procesadas)
        for f in self.fragmentos:
            if f.pagina_fin < f.pagina_inicio or not set(range(f.pagina_inicio, f.pagina_fin + 1)) <= procesadas:
                raise ValueError("Un fragmento referencia páginas no procesadas")
        for dato in [*self.prestaciones, *self.requisitos, *self.periodos]:
            if dato.fragmento_orden not in fragmentos:
                raise ValueError("Cada dato necesita un fragmento de respaldo de esta extracción")
        for dato in [*self.requisitos, *self.periodos]:
            if dato.prestacion_clave is not None and dato.prestacion_clave not in claves:
                raise ValueError("Una condición referencia una prestación inexistente")
        for req in self.requisitos:
            if " ".join(req.texto_original.split()) not in " ".join(fragmentos[req.fragmento_orden].texto.split()):
                raise ValueError("La cita del requisito no aparece en su fragmento")
        if self.estado == "completa" and (self.cobertura.paginas_con_error or procesadas != set(range(1, self.cobertura.paginas_totales + 1))):
            raise ValueError("Una extracción completa debe cubrir todas las páginas sin errores")
        if self.estado in {"pendiente", "error"} and (self.prestaciones or self.requisitos or self.periodos):
            raise ValueError("Una extracción pendiente o fallida no debe publicar hechos")
        return self


def guardar_extraccion(db: Session, licitacion_id: int, entrada: ExtraccionEntrada) -> tuple[int, bool]:
    if db.get(Licitacion, licitacion_id) is None:
        raise LookupError("No se encontró la licitación")
    correlativos = {p.item_correlativo for p in entrada.prestaciones if p.item_correlativo is not None}
    existentes = set(db.scalars(select(LicitacionItem.correlativo).where(LicitacionItem.licitacion_id == licitacion_id)).all())
    if not correlativos <= existentes:
        raise ValueError("La prestación referencia un ítem que no pertenece a esta licitación")
    datos = entrada.documento.model_dump()
    # Un documento/version se registra una vez, incluso con importaciones simultáneas.
    db.execute(insert(Documento).values(licitacion_id=licitacion_id, **datos).on_conflict_do_nothing(constraint="uq_documento_origen_version"))
    documento = db.scalars(select(Documento).where(
        Documento.licitacion_id == licitacion_id, Documento.url_origen == datos["url_origen"], Documento.version == datos["version"],
    ).with_for_update()).one()
    if any(getattr(documento, k) != v for k, v in datos.items()):
        raise ValueError("Esta versión documental ya existe con otros metadatos; registra una nueva versión")
    huella = hashlib.sha256(json.dumps(entrada.model_dump(mode="json"), sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
    existente = db.scalar(select(Extraccion.id).where(Extraccion.documento_id == documento.id, Extraccion.huella_contenido == huella))
    if existente is not None:
        return existente, False
    extraccion = Extraccion(licitacion_id=licitacion_id, documento_id=documento.id, metodo=entrada.metodo,
        version_metodo=entrada.version_metodo, estado=entrada.estado, huella_contenido=huella, cobertura=entrada.cobertura.model_dump())
    db.add(extraccion)
    db.flush()
    fragmentos = {}
    for f in entrada.fragmentos:
        fila = Fragmento(extraccion_id=extraccion.id, **f.model_dump())
        db.add(fila)
        db.flush()
        fragmentos[f.orden] = fila.id
    prestaciones = {}
    contexto = {"licitacion_id": licitacion_id, "extraccion_id": extraccion.id}
    for p in entrada.prestaciones:
        valores = p.model_dump(exclude={"fragmento_orden"})
        fila = Prestacion(**contexto, fragmento_id=fragmentos[p.fragmento_orden], **valores)
        db.add(fila)
        db.flush()
        prestaciones[p.clave] = fila.id
    for modelo, filas in ((Requisito, entrada.requisitos), (PeriodoServicio, entrada.periodos)):
        for dato in filas:
            valores = dato.model_dump(exclude={"fragmento_orden", "prestacion_clave"})
            fila = modelo(**contexto, fragmento_id=fragmentos[dato.fragmento_orden],
                prestacion_id=prestaciones.get(dato.prestacion_clave), **valores)
            db.add(fila)
    db.flush()
    return extraccion.id, True


def como_dict(fila):
    salida = {}
    for columna in fila.__table__.columns:
        valor = getattr(fila, columna.name)
        salida[columna.name] = str(valor) if isinstance(valor, Decimal) else valor.isoformat() if isinstance(valor, datetime) else valor
    return salida
