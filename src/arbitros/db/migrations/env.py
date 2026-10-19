from alembic import context
from sqlalchemy import create_engine

from arbitros.db.models import Base

config = context.config
target_metadata = Base.metadata


def run_migrations_online() -> None:
    conexion = config.attributes.get("connection")
    if conexion is not None:
        _configurar_y_migrar(conexion)
        return
    # Uso desde la línea de comandos (p. ej. autogenerate)
    engine = create_engine(config.get_main_option("sqlalchemy.url"))
    with engine.begin() as conexion:
        _configurar_y_migrar(conexion)


def _configurar_y_migrar(conexion) -> None:
    # render_as_batch: SQLite no soporta ALTER TABLE completo
    context.configure(
        connection=conexion, target_metadata=target_metadata, render_as_batch=True
    )
    with context.begin_transaction():
        context.run_migrations()


run_migrations_online()
