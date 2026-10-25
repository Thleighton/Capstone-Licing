from logging.config import fileConfig

from alembic import context

from app.config import settings
from app.database import Base, engine

# Registran las tablas de Core en Base.metadata.
from app.models import (  # noqa: F401
    raw,
    licitacion,
    licitacion_item,
    licitacion_documento,
    ejecucion_ingesta,
    compra_agil,
    compra_agil_item,
    compra_agil_sincronizacion,
)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline():
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def migrar_con_conexion(connection):
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    # La adopción usa la misma transacción para registrar y proteger las tablas.
    connection = config.attributes.get("connection")
    if connection is not None:
        migrar_con_conexion(connection)
    else:
        with engine.connect() as connection:
            migrar_con_conexion(connection)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

