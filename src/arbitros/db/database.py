from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker


def _activar_foreign_keys(dbapi_conn, _record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


class Database:
    """Motor + fábrica de sesiones. `cerrar()` libera el archivo (necesario al restaurar)."""

    def __init__(self, url: str):
        self.url = url
        self.engine: Engine = create_engine(url)
        event.listen(self.engine, "connect", _activar_foreign_keys)
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
