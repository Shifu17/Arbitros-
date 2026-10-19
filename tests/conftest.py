import pytest

from arbitros.config import Rutas
from arbitros.db.database import Database
from arbitros.db.migrar import migrar


@pytest.fixture
def rutas(tmp_path):
    return Rutas(tmp_path / "datos").crear()


@pytest.fixture
def db(rutas):
    base = Database.desde_archivo(rutas.db)
    migrar(base)
    yield base
    base.cerrar()
