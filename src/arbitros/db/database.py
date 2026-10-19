from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _al_conectar(dbapi_conn, _record):
    # El driver sqlite3 de Python no abre transacción antes de CREATE/ALTER/DROP, así que
    # una migración fallida podía quedar a medias. Se desactiva su manejo automático y
    # SQLAlchemy emite BEGIN explícito (receta oficial de SQLAlchemy para SQLite).
    dbapi_conn.isolation_level = None
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def _al_iniciar_transaccion(conexion):
    conexion.exec_driver_sql("BEGIN")


class Database:
    """Motor + fábrica de sesiones. `cerrar()` libera el archivo (necesario al restaurar)."""

    def __init__(self, url: str):
        self.url = url
        self.engine: Engine = create_engine(url)
        event.listen(self.engine, "connect", _al_conectar)
        event.listen(self.engine, "begin", _al_iniciar_transaccion)
        self._fabrica = sessionmaker(self.engine, expire_on_commit=False)

    @classmethod
    def desde_archivo(cls, ruta: Path) -> "Database":
        return cls(f"sqlite:///{ruta}")

    @contextmanager
    def sesion(self) -> Iterator[Session]:
        """Sesión transaccional: confirma al salir, revierte si hay excepción."""
        s = self._fabrica()
        try:
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise
        finally:
            s.close()

    def cerrar(self) -> None:
        self.engine.dispose()
