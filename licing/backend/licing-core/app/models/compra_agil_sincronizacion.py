"""Estado de la sincronización incremental del listado de Compra Ágil."""
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base


class CompraAgilSincronizacion(Base):
    """Fila única (id = 1). Las fechas son hora de Chile, como fecha_ultimo_cambio de la API."""
    __tablename__ = "compra_agil_sincronizacion"
    __table_args__ = (CheckConstraint("id = 1", name="ck_compra_agil_sincronizacion_unica"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Los cambios anteriores ya se encolaron. NULL: falta la carga inicial de publicadas.
    cursor: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    # Ventana en curso; pagina es la siguiente por consultar, desde la última hacia la primera.
    ventana_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    ventana_hasta: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    ventana_estados: Mapped[str | None] = mapped_column(String(100))
    pagina: Mapped[int | None] = mapped_column(Integer)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )


class CompraAgilPendiente(Base):
    """Cola de detalles por descargar, alimentada por el listado."""
    __tablename__ = "compra_agil_pendiente"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo_externo: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    # fecha_ultimo_cambio informada por el listado, con milisegundos.
    cambio: Mapped[datetime] = mapped_column(DateTime(timezone=False), nullable=False)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=False))
    fecha_cierre: Mapped[datetime | None] = mapped_column(DateTime(timezone=False), index=True)
    detectado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
    intentos: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    reintentar_desde: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ultimo_error: Mapped[dict | None] = mapped_column(JSONB)
