"""Aplica las migraciones de Alembic al arrancar la app.

No se usa alembic.ini: la configuración se arma aquí para que funcione igual
en desarrollo y dentro del ejecutable empaquetado.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

from arbitros.db.database import Database

CARPETA_MIGRACIONES = Path(__file__).parent / "migrations"


def configuracion_alembic(db: Database) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(CARPETA_MIGRACIONES))
    cfg.set_main_option("sqlalchemy.url", db.url)
    return cfg


def migrar(db: Database) -> None:
    cfg = configuracion_alembic(db)
    with db.engine.begin() as conexion:
        cfg.attributes["connection"] = conexion
        command.upgrade(cfg, "head")
