import json
import zipfile
from datetime import datetime, timedelta

import pytest

from alembic import command

from arbitros.db.database import Database
from arbitros.db.migrar import configuracion_alembic, migrar, necesita_migrar, revision_actual
from arbitros.services.arbitros import ArbitroService, DatosArbitro
from arbitros.services.errores import ErrorValidacion
from arbitros.services.respaldos import MAX_AUTOMATICOS, RespaldoService


@pytest.fixture
def svc(db, rutas):
    return RespaldoService(db, rutas)


def test_crear_y_restaurar(db, rutas, svc):
    arbitros = ArbitroService(db)
    arbitros.crear(DatosArbitro(nombre="Juan", telefono="3312345678"))
    (rutas.documentos / "cedulas").mkdir()
    (rutas.documentos / "cedulas" / "c1.pdf").write_bytes(b"pdf")
    zip_ = svc.crear()

    arbitros.crear(DatosArbitro(nombre="Ana", telefono="3311112222"))
    (rutas.documentos / "cedulas" / "c1.pdf").unlink()

    previo = svc.restaurar(zip_)
    migrar(db)
    assert previo.exists()
    assert [a.nombre for a in arbitros.listar()] == ["Juan"]
    assert (rutas.documentos / "cedulas" / "c1.pdf").read_bytes() == b"pdf"


def test_rechaza_respaldo_de_otro_colegio(svc):
    from arbitros import colegios

    zip_ = svc.crear()
    colegios.activar(colegios.SALTILLO)
    with pytest.raises(ErrorValidacion, match="Coahuila"):
        svc.restaurar(zip_)


def test_rechaza_zip_ajeno(tmp_path, svc):
    malo = tmp_path / "otro.zip"
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("hola.txt", "x")
    with pytest.raises(ErrorValidacion):
        svc.restaurar(malo)


def test_rechaza_rutas_peligrosas(tmp_path, svc):
    malo = tmp_path / "malo.zip"
    with zipfile.ZipFile(malo, "w") as z:
        z.writestr("manifest.json", json.dumps({"app": "arbitros"}))
        z.writestr("arbitros.db", b"")
        z.writestr("../fuera.txt", "x")
    with pytest.raises(ErrorValidacion):
        svc.restaurar(malo)
    assert not (tmp_path / "fuera.txt").exists()


def test_rechaza_archivo_no_zip(tmp_path, svc):
    f = tmp_path / "x.zip"
    f.write_text("no soy zip")
    with pytest.raises(ErrorValidacion):
        svc.restaurar(f)


def test_respaldo_automatico_semanal(svc):
    assert svc.respaldo_automatico_si_toca() is not None
    assert svc.respaldo_automatico_si_toca() is None
    en_8_dias = datetime.now() + timedelta(days=8)
    assert svc.respaldo_automatico_si_toca(en_8_dias) is not None


def test_poda_automaticos(svc):
    for _ in range(MAX_AUTOMATICOS + 3):
        svc.crear(prefijo="auto_")
    svc._podar_automaticos()
    assert len([r for r in svc.listar() if r.automatico]) == MAX_AUTOMATICOS


def test_necesita_migrar(tmp_path):
    db = Database.desde_archivo(tmp_path / "x.db")
    assert revision_actual(db) is None and not necesita_migrar(db)  # instalación nueva
    command.upgrade(configuracion_alembic(db), "0001")
    assert necesita_migrar(db)
    migrar(db)
    assert not necesita_migrar(db)
    db.cerrar()
