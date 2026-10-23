"""Verifica tablas creadas manualmente; --registrar las incorpora a Alembic.

Nunca crea, elimina ni reemplaza tablas de datos. No modifica tablas de usuarios.
"""
import argparse

from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import CheckConstraint, Identity, inspect, text
from sqlalchemy.exc import SQLAlchemyError

from .config import CORE_DIR
from .database import Base, engine
from .models import ejecucion_ingesta, licitacion, licitacion_item, raw  # noqa: F401

REVISION_BASE = "83c9bcf6857f"
REVISION_RLS = "b7e29c41a806"
REVISION_ACTUAL = "b8654f3a89fc"
TABLAS_BASE = {"raw_mercado_publico", "licitacion", "licitacion_item", "ejecucion_ingesta"}
TABLAS = set(Base.metadata.tables)
COLUMNAS_NUEVAS = {
    "licitacion": {"tipo", "codigo_tipo", "estimacion", "visibilidad_monto", "justificacion_monto", "direccion_comprador", "direccion_entrega", "direccion_visita", "fechas_fuente", "condiciones_fuente", "normalizacion_version", "normalizado_en", "ubicacion_servicio"},
    "licitacion_item": {"codigo_categoria", "categoria", "estado_fuente", "adjudicacion_fuente", "posicion_fuente"},
    "raw_mercado_publico": {"verificado_en"},
}


def _solo_core(objeto, nombre, tipo, reflected, compare_to):
    if tipo == "table":
        return nombre in TABLAS
    tabla = getattr(objeto, "table", None)
    return tabla is None or tabla.name in TABLAS


def verificar_esquema(connection, *, legado=False) -> list[str]:
    """Compara columnas, tipos, defaults, índices, relaciones y restricciones."""
    inspector = inspect(connection)
    presentes = set(inspector.get_table_names(schema="public"))
    tablas = TABLAS_BASE if legado else TABLAS
    faltantes = tablas - presentes
    if faltantes:
        return ["Faltan tablas: " + ", ".join(sorted(faltantes))]

    def incluir(objeto, nombre, tipo, reflected, compare_to):
        if tipo == "table":
            return nombre in tablas
        tabla = getattr(objeto, "table", None)
        if tabla is not None and tabla.name not in tablas:
            return False
        if legado and tabla is not None:
            if tipo == "column" and nombre in COLUMNAS_NUEVAS.get(tabla.name, set()):
                return False
            if tipo == "index" and nombre == "ix_licitacion_item_codigo_categoria":
                return False
            if tipo == "unique_constraint" and nombre in {"uq_licitacion_item_correlativo", "uq_licitacion_item_posicion"}:
                return False
        return True

    contexto = MigrationContext.configure(connection, opts={
        "compare_type": True, "compare_server_default": True, "include_object": incluir,
    })
    errores = []
    for bloque in compare_metadata(contexto, Base.metadata):
        diferencias = bloque if isinstance(bloque, list) else [bloque]
        for diferencia in diferencias:
            # Table Editor puede usar IDENTITY en lugar de SERIAL. Ambos
            # generan el id que Core omite al insertar; no hay que convertirlos.
            if (diferencia[0] == "modify_default" and diferencia[3] == "id"
                    and isinstance(diferencia[-2], Identity) and diferencia[-1] is None):
                continue
            errores.append(str(diferencia))
    for nombre in sorted(tablas):
        tabla = Base.metadata.tables[nombre]
        columnas = {c["name"]: c for c in inspector.get_columns(nombre, schema="public")}
        pk = inspector.get_pk_constraint(nombre, schema="public")["constrained_columns"]
        if pk != [c.name for c in tabla.primary_key.columns]:
            errores.append(f"{nombre}: clave primaria diferente a la de Core")
        identificador = columnas.get("id", {})
        if not identificador.get("identity") and "nextval(" not in str(identificador.get("default", "")):
            errores.append(f"{nombre}.id: falta un generador de identificadores (IDENTITY o secuencia)")
        checks = {c["name"] for c in inspector.get_check_constraints(nombre, schema="public")}
        for restriccion in tabla.constraints:
            if legado and restriccion.name in {"ck_item_posicion_positiva", "ck_licitacion_ubicacion_evidencia"}:
                continue
            if isinstance(restriccion, CheckConstraint) and restriccion.name not in checks:
                errores.append(f"{nombre}: falta la restricción {restriccion.name}")
        if legado and nombre == "licitacion_item":
            if not any(set(c["column_names"]) == {"licitacion_id", "correlativo"} for c in inspector.get_unique_constraints(nombre, schema="public")):
                errores.append("licitacion_item: falta la unicidad original de correlativos")
    return errores


def registrar_esquema(connection):
    inspector = inspect(connection)
    versiones = []
    if inspector.has_table("alembic_version", schema="public"):
        versiones = connection.execute(text("SELECT version_num FROM public.alembic_version")).scalars().all()
    conocidas = {REVISION_BASE, REVISION_RLS, "c4f8a19d620e", "968329dc86b0", "b9a70e6d4a93", "5c7bbdaa3adf", "c08ccd7a1466", REVISION_ACTUAL}
    if versiones and (len(versiones) != 1 or versiones[0] not in conocidas):
        raise ValueError("El historial de Alembic tiene otra versión. Revisa la migración antes de continuar.")
    config = Config(str(CORE_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(CORE_DIR / "alembic"))
    config.attributes["connection"] = connection
    if versiones and versiones != [REVISION_ACTUAL]:
        command.upgrade(config, "head")
        errores = verificar_esquema(connection)
        if errores:
            raise ValueError("El esquema no coincide con Core:\n" + "\n".join(errores))
        return
    columnas_licitacion = {c["name"] for c in inspector.get_columns("licitacion", schema="public")} if inspector.has_table("licitacion", schema="public") else set()
    legado = versiones in ([REVISION_BASE], [REVISION_RLS]) or (
        not versiones and not COLUMNAS_NUEVAS["licitacion"] <= columnas_licitacion
    )
    errores = verificar_esquema(connection, legado=legado)
    if errores:
        raise ValueError("El esquema no coincide con Core:\n" + "\n".join(errores))

    if not versiones:
        # La comparación de tablas no detecta la función de limpieza.
        command.stamp(config, REVISION_BASE if legado else "b9a70e6d4a93")
    command.upgrade(config, "head")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registrar", action="store_true", help="Registrar el esquema verificado y aplicar RLS en una transacción")
    args = parser.parse_args()
    try:
        with engine.begin() as connection:
            if args.registrar:
                registrar_esquema(connection)
                print("Esquema registrado en Alembic y tablas de Core protegidas con RLS. Los datos se conservaron.")
            else:
                errores = verificar_esquema(connection)
                if errores:
                    print("El esquema requiere revisión; no se modificó la base:")
                    for error in errores:
                        print("- " + error)
                    return 1
                print("El esquema coincide con Core. No se modificó la base. Puedes continuar con --registrar.")
    except ValueError as exc:
        print(str(exc))
        return 1
    except SQLAlchemyError:
        print("No se pudo verificar PostgreSQL. Revisa la conexión y los permisos; no se completó el registro.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

