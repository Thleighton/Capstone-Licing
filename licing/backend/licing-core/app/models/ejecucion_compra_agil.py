from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Integer,
    String,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class EjecucionCompraAgil(Base):
    __tablename__ = "ejecucion_compra_agil"

    __table_args__ = (
        CheckConstraint(
            "estado IN "
            "('en_curso', 'completada', 'parcial', 'error', 'interrumpida')",
            name="ck_ejecucion_compra_agil_estado",
        ),
        CheckConstraint(
            "paginas_solicitadas BETWEEN 1 AND 10",
            name="ck_ejecucion_compra_agil_paginas_solicitadas",
        ),
        CheckConstraint(
            "maximo_detalles BETWEEN 1 AND 5",
            name="ck_ejecucion_compra_agil_maximo_detalles",
        ),
    )

    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
    )

    inicio: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    fin: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
    )

    estado: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=text("'en_curso'"),
    )

    paginas_solicitadas: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    maximo_detalles: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    paginas_consultadas: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    codigos_encontrados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    omitidos_ya_procesados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    codigos_invalidos: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    detalles_intentados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    descargados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    reutilizados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    detalles_procesados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    compras_nuevas: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    detenido_por_limite: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    detenido_por_error_api: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    detenido_por_429: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    listados_raw_ids: Mapped[list[int]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    resultados: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )

    errores: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )