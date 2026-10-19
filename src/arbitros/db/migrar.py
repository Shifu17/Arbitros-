"""Aplica las migraciones de Alembic al arrancar la app.

No se usa alembic.ini: la configuración se arma aquí para que funcione igual
en desarrollo y dentro del ejecutable empaquetado.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from arbitros.db.database import Database

CARPETA_MIGRACIONES = Path(__file__).parent / "migrations"


def configuracion_alembic(db: Database) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(CARPETA_MIGRACIONES))
    cfg.set_main_option("sqlalchemy.url", db.url)
    return cfg


def migrar(db: Database) -> None:
    """Lleva la base de datos a la última versión, todo o nada.

    En SQLite, cambiar una columna obliga a recrear la tabla (copiar, borrar, renombrar);
    con las llaves foráneas activas eso falla si otras tablas la referencian (p. ej. partidos →
    equipos). Por eso se desactivan durante la migración y al final se verifica que todo
    siga consistente antes de confirmar.
    """
    cfg = configuracion_alembic(db)
    with db.engine.connect() as conexion:
        crudo = conexion.connection.dbapi_connection
        crudo.execute("PRAGMA foreign_keys=OFF")  # solo tiene efecto fuera de una transacción
        try:
            with conexion.begin():
                _limpiar_tablas_temporales(conexion)
                cfg.attributes["connection"] = conexion
                command.upgrade(cfg, "head")
                rotas = conexion.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
                if rotas:
                    raise RuntimeError(f"La migración dejó referencias rotas: {rotas[:5]}")
        finally:
            crudo.execute("PRAGMA foreign_keys=ON")


def _limpiar_tablas_temporales(conexion) -> None:
    """Borra restos de una migración interrumpida en versiones anteriores de la app."""
    nombres = conexion.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").scalars()
    for nombre in [n for n in nombres if n.startswith("_alembic_tmp_")]:
        conexion.exec_driver_sql(f'DROP TABLE "{nombre}"')


def revision_actual(db: Database) -> str | None:
    """Revisión de Alembic de la base de datos; None si está vacía (instalación nueva)."""
    with db.engine.connect() as conexion:
        return MigrationContext.configure(conexion).get_current_revision()


def necesita_migrar(db: Database) -> bool:
    """True si hay datos existentes con una versión anterior del esquema."""
    actual = revision_actual(db)
    head = ScriptDirectory.from_config(configuracion_alembic(db)).get_current_head()
    return actual is not None and actual != head
