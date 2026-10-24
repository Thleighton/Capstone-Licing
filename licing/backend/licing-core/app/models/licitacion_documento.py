"""Documento de entrada: pertenece a Core, antes de cualquier filtro."""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Identity, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class LicitacionDocumento(Base):
    __tablename__ = "licitacion_documento"
    __table_args__ = (UniqueConstraint("licitacion_id", "hash_archivo", name="uq_documento_hash"),
                      UniqueConstraint("licitacion_id", "url_origen", "version"),
                      {"comment": "Documentos fuente de la ingesta. PDF en Storage privado de este mismo proyecto; texto conservado una sola vez con índices de página."})

    id: Mapped[int] = mapped_column(Integer, Identity(), primary_key=True)
    licitacion_id: Mapped[int] = mapped_column(ForeignKey("licitacion.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(Text)
    url_origen: Mapped[str] = mapped_column(Text)
    version: Mapped[int] = mapped_column(Integer)
    hash_archivo: Mapped[str] = mapped_column(Text)
    storage_path: Mapped[str] = mapped_column(Text, unique=True)
    estado_extraccion: Mapped[str] = mapped_column(Text)
    texto_extraido: Mapped[str | None] = mapped_column(Text)
    paginas: Mapped[int | None] = mapped_column(Integer)
    cobertura: Mapped[dict] = mapped_column(JSONB)
    vigente: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=text("clock_timestamp()"))
