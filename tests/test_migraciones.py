"""Migraciones sobre bases de datos con datos reales (el caso que falló en producción)."""

import sqlite3

from alembic import command

from arbitros.db.database import Database
from arbitros.db.migrar import configuracion_alembic, migrar, revision_actual


def _db_en_0004_con_partido(ruta):
    db = Database.desde_archivo(ruta)
    command.upgrade(configuracion_alembic(db), "0004")
    db.cerrar()
    con = sqlite3.connect(ruta)
    con.executescript("""
        INSERT INTO ligas (id, nombre, tipo, posiciones_defecto, activa) VALUES (1, 'Liga', 'liga', 'central', 1);
        INSERT INTO equipos (id, liga_id, nombre, activo) VALUES (1, 1, 'Tigres', 1), (2, 1, 'Pumas', 1);
        INSERT INTO campos (id, liga_id, nombre, activo) VALUES (1, 1, 'Campo 1', 1);
        INSERT INTO jornadas (id, liga_id, numero, fecha_inicio) VALUES (1, 1, 1, '2026-10-24');
        INSERT INTO partidos (id, jornada_id, fecha, hora, campo_id, local_id, visitante_id, posiciones, estado)
            VALUES (1, 1, '2026-10-24', '10:00:00.000000', 1, 1, 2, 'central', 'programado');
    """)
    con.commit()
    con.close()


def _contar(ruta, tabla):
    con = sqlite3.connect(ruta)
    try:
        return con.execute(f"SELECT count(*) FROM {tabla}").fetchone()[0]
    finally:
        con.close()


def test_migrar_tabla_referenciada_con_datos(tmp_path):
    ruta = tmp_path / "a.db"
    _db_en_0004_con_partido(ruta)
    db = Database.desde_archivo(ruta)
    migrar(db)
    assert revision_actual(db) == "0005"
    db.cerrar()
    assert _contar(ruta, "partidos") == 1 and _contar(ruta, "equipos") == 2


def test_recupera_migracion_que_quedo_a_medias(tmp_path):
    """Estado que dejó la versión anterior: tablas de 0005 creadas, tabla temporal y versión 0004."""
    ruta = tmp_path / "b.db"
    _db_en_0004_con_partido(ruta)
    con = sqlite3.connect(ruta)
    con.executescript("""
        CREATE TABLE categorias (id INTEGER PRIMARY KEY, liga_id INTEGER NOT NULL, nombre VARCHAR(120) NOT NULL,
            posiciones_defecto VARCHAR(100), activo BOOLEAN NOT NULL);
        CREATE TABLE tarifas_categoria (categoria_id INTEGER NOT NULL, posicion VARCHAR(20) NOT NULL,
            monto_centavos INTEGER NOT NULL, PRIMARY KEY (categoria_id, posicion));
        CREATE TABLE _alembic_tmp_equipos (id INTEGER, liga_id INTEGER, categoria_id INTEGER, nombre VARCHAR(120),
            activo BOOLEAN);
    """)
    con.commit()
    con.close()
    db = Database.desde_archivo(ruta)
    migrar(db)
    assert revision_actual(db) == "0005"
    db.cerrar()
    con = sqlite3.connect(ruta)
    tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    columnas = [r[1] for r in con.execute("PRAGMA table_info(equipos)")]
    con.close()
    assert "_alembic_tmp_equipos" not in tablas and "categoria_id" in columnas


def test_ddl_es_transaccional(tmp_path):
    """Si algo falla a mitad de una transacción, también se deshacen los CREATE TABLE."""
    db = Database.desde_archivo(tmp_path / "c.db")
    try:
        with db.engine.begin() as con:
            con.exec_driver_sql("CREATE TABLE x (id INTEGER)")
            raise RuntimeError("falla simulada")
    except RuntimeError:
        pass
    with db.engine.connect() as con:
        assert con.exec_driver_sql("SELECT count(*) FROM sqlite_master WHERE name='x'").scalar() == 0
    db.cerrar()
