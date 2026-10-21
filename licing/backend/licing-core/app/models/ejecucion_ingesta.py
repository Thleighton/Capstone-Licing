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


class EjecucionIngesta(Base):
    __tablename__ = "ejecucion_ingesta"

    __table_args__ = (
        CheckConstraint(
            "estado IN "
            "('en_curso', 'completada', 'parcial', 'error', 'interrumpida')",
            name="ck_ejecucion_ingesta_estado",
        ),
        CheckConstraint(
            "limite_detalles BETWEEN 1 AND 20",
            name="ck_ejecucion_ingesta_limite",
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

    limite_detalles: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    resumenes_recibidos: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    seleccionados: Mapped[int] = mapped_column(
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

    procesados: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
    )

    detenido_por_error_api: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("false"),
    )

    errores: Mapped[list[dict]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'[]'::jsonb"),
    )