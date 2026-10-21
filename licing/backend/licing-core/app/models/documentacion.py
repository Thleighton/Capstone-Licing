"""Información documental versionada. No almacena archivos PDF ni resultados de filtros."""
from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, DateTime, ForeignKey, ForeignKeyConstraint,
    Integer, Numeric, String, Text, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class Documento(Base):
    __tablename__ = "licitacion_documento"
    __table_args__ = (
        UniqueConstraint("licitacion_id", "url_origen", "version", name="uq_documento_origen_version"),
        UniqueConstraint("id", "licitacion_id", name="uq_documento_licitacion"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    licitacion_id: Mapped[int] = mapped_column(ForeignKey("licitacion.id"), index=True)
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(40))
    url_origen: Mapped[str] = mapped_column(String(1500))
    version: Mapped[str] = mapped_column(String(100))
    huella_archivo: Mapped[str | None] = mapped_column(String(64))
    fecha_fuente: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    registrado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Extraccion(Base):
    __tablename__ = "licitacion_extraccion"
    __table_args__ = (
        ForeignKeyConstraint(["documento_id", "licitacion_id"], ["licitacion_documento.id", "licitacion_documento.licitacion_id"], name="fk_extraccion_documento"),
        UniqueConstraint("id", "licitacion_id", name="uq_extraccion_licitacion"),
        UniqueConstraint("documento_id", "huella_contenido", name="uq_extraccion_contenido"),
        CheckConstraint("estado IN ('pendiente','completa','parcial','error')", name="ck_extraccion_estado"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    licitacion_id: Mapped[int] = mapped_column(Integer, index=True)
    documento_id: Mapped[int] = mapped_column(Integer, index=True)
    metodo: Mapped[str] = mapped_column(String(100))
    version_metodo: Mapped[str] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(String(20))
    huella_contenido: Mapped[str] = mapped_column(String(64))
    cobertura: Mapped[dict] = mapped_column(JSONB)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Fragmento(Base):
    __tablename__ = "documento_fragmento"
    __table_args__ = (
        UniqueConstraint("extraccion_id", "orden", name="uq_fragmento_orden"),
        UniqueConstraint("id", "extraccion_id", name="uq_fragmento_extraccion"),
        CheckConstraint("pagina_inicio > 0 AND pagina_fin >= pagina_inicio AND orden > 0", name="ck_fragmento_paginas"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    extraccion_id: Mapped[int] = mapped_column(ForeignKey("licitacion_extraccion.id"), index=True)
    orden: Mapped[int] = mapped_column(Integer)
    pagina_inicio: Mapped[int] = mapped_column(Integer)
    pagina_fin: Mapped[int] = mapped_column(Integer)
    seccion: Mapped[str | None] = mapped_column(Text)
    tipo_seccion: Mapped[str] = mapped_column(String(40))
    texto: Mapped[str] = mapped_column(Text)
    requiere_ocr: Mapped[bool | None] = mapped_column(Boolean)


class Evidencia:
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    licitacion_id: Mapped[int] = mapped_column(Integer, index=True)
    extraccion_id: Mapped[int] = mapped_column(Integer, index=True)
    fragmento_id: Mapped[int] = mapped_column(Integer)
    estado_dato: Mapped[str] = mapped_column(String(25))
    confianza: Mapped[Decimal | None] = mapped_column(Numeric())


def evidencia(tabla):
    return (
        ForeignKeyConstraint(["extraccion_id", "licitacion_id"], ["licitacion_extraccion.id", "licitacion_extraccion.licitacion_id"], name=f"fk_{tabla}_extraccion"),
        ForeignKeyConstraint(["fragmento_id", "extraccion_id"], ["documento_fragmento.id", "documento_fragmento.extraccion_id"], name=f"fk_{tabla}_fragmento"),
        CheckConstraint("estado_dato IN ('confirmado','no_informado','ambiguo','contradictorio')", name=f"ck_{tabla}_estado"),
        CheckConstraint("confianza BETWEEN 0 AND 1", name=f"ck_{tabla}_confianza"),
    )


class Prestacion(Evidencia, Base):
    __tablename__ = "licitacion_prestacion"
    __table_args__ = evidencia("prestacion") + (
        UniqueConstraint("id", "extraccion_id", "licitacion_id", name="uq_prestacion_contexto"),
        UniqueConstraint("extraccion_id", "clave", name="uq_prestacion_clave"),
    )
    clave: Mapped[str] = mapped_column(String(100))
    tipo: Mapped[str] = mapped_column(String(60))
    nombre: Mapped[str] = mapped_column(Text)
    descripcion: Mapped[str | None] = mapped_column(Text)
    item_correlativo: Mapped[int | None] = mapped_column(Integer)
    modalidad: Mapped[str | None] = mapped_column(Text)
    oferta_parcial: Mapped[bool | None] = mapped_column(Boolean)
    grupo_servicios: Mapped[str | None] = mapped_column(Text)
    adjudicacion: Mapped[str | None] = mapped_column(Text)


def contexto_prestacion(tabla):
    return ForeignKeyConstraint(
        ["prestacion_id", "extraccion_id", "licitacion_id"],
        ["licitacion_prestacion.id", "licitacion_prestacion.extraccion_id", "licitacion_prestacion.licitacion_id"],
        name=f"fk_{tabla}_prestacion",
    )


class Requisito(Evidencia, Base):
    __tablename__ = "licitacion_requisito"
    __table_args__ = evidencia("requisito") + (
        contexto_prestacion("requisito"),
        CheckConstraint("caracter IN ('obligatorio','evaluable','condicional','no_exigido','no_indicado')", name="ck_requisito_caracter"),
        CheckConstraint("valor_min IS NULL OR valor_max IS NULL OR valor_min <= valor_max", name="ck_requisito_rango"),
        CheckConstraint("ponderacion BETWEEN 0 AND 100", name="ck_requisito_ponderacion"),
    )
    prestacion_id: Mapped[int | None] = mapped_column(Integer, index=True)
    tipo: Mapped[str] = mapped_column(String(60))
    clave: Mapped[str] = mapped_column(String(100))
    texto_original: Mapped[str] = mapped_column(Text)
    caracter: Mapped[str] = mapped_column(String(20))
    operador: Mapped[str | None] = mapped_column(String(40))
    valor_texto: Mapped[str | None] = mapped_column(Text)
    valor_min: Mapped[Decimal | None] = mapped_column(Numeric())
    valor_max: Mapped[Decimal | None] = mapped_column(Numeric())
    unidad: Mapped[str | None] = mapped_column(Text)
    alcance: Mapped[str | None] = mapped_column(Text)
    grupo_alternativa: Mapped[str | None] = mapped_column(Text)
    condicion: Mapped[str | None] = mapped_column(Text)
    excepciones: Mapped[str | None] = mapped_column(Text)
    ponderacion: Mapped[Decimal | None] = mapped_column(Numeric())
    parametros: Mapped[dict | None] = mapped_column(JSONB)


class PeriodoServicio(Evidencia, Base):
    __tablename__ = "licitacion_periodo_servicio"
    __table_args__ = evidencia("periodo") + (
        contexto_prestacion("periodo"),
        CheckConstraint("precision IN ('exacta','intervalo','por_coordinar','no_informada')", name="ck_periodo_precision"),
        CheckConstraint("inicio_min IS NULL OR inicio_max IS NULL OR inicio_min <= inicio_max", name="ck_periodo_inicio"),
        CheckConstraint("fin_min IS NULL OR fin_max IS NULL OR fin_min <= fin_max", name="ck_periodo_fin"),
        CheckConstraint("inicio_min IS NULL OR fin_min IS NULL OR inicio_min <= fin_min", name="ck_periodo_orden"),
        CheckConstraint("cantidad_min IS NULL OR cantidad_max IS NULL OR cantidad_min <= cantidad_max", name="ck_periodo_cantidad"),
        CheckConstraint("cantidad_min >= 0 AND cantidad_max >= 0", name="ck_periodo_cantidad_positiva"),
        CheckConstraint("ocupantes_por_unidad > 0", name="ck_periodo_ocupantes"),
    )
    prestacion_id: Mapped[int] = mapped_column(Integer, index=True)
    tipo: Mapped[str] = mapped_column(String(40))
    precision: Mapped[str] = mapped_column(String(20))
    # Horas locales y zona explícita: no se inventa hora para una fecha sin hora.
    inicio_min: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    inicio_max: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fin_min: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fin_max: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    zona_horaria: Mapped[str | None] = mapped_column(String(60))
    incluye_hora: Mapped[bool] = mapped_column(Boolean)
    cantidad_min: Mapped[Decimal | None] = mapped_column(Numeric())
    cantidad_max: Mapped[Decimal | None] = mapped_column(Numeric())
    unidad: Mapped[str | None] = mapped_column(Text)
    tipo_habitacion: Mapped[str | None] = mapped_column(Text)
    ocupantes_por_unidad: Mapped[int | None] = mapped_column(Integer)
