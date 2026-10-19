from datetime import date

import pytest

from arbitros.db.models import TIPO_TORNEO
from arbitros.services.dinero import a_centavos, formatear_monto, monto_editable
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import JornadaService
from arbitros.services.ligas import DatosLiga, LigaService


@pytest.fixture
def ligas(db):
    return LigaService(db)


def test_dinero():
    assert a_centavos("350") == 35000
    assert a_centavos("$1,200.5") == 120050
    assert a_centavos("") == 0
    with pytest.raises(ValueError):
        a_centavos("12.345")
    with pytest.raises(ValueError):
        a_centavos("abc")
    assert formatear_monto(120050) == "$1,200.50"
    assert formatear_monto(35000) == "$350"
    assert monto_editable(120050) == "1200.50"


def test_crear_liga_y_resumen(ligas):
    liga = ligas.crear(DatosLiga(nombre="  Liga   Municipal ", posiciones=["central", "asistente_1"]))
    assert liga.nombre == "Liga Municipal"
    assert liga.lista_posiciones == ["central", "asistente_1"]
    ligas.equipos.crear(liga.id, "Tigres")
    ligas.campos.crear(liga.id, "Campo 1", direccion="Av. Siempre Viva")
    [r] = ligas.listar()
    assert (r.equipos, r.campos, r.jornadas) == (1, 1, 0)


def test_nombre_liga_unico(ligas):
    ligas.crear(DatosLiga(nombre="Liga A"))
    with pytest.raises(ErrorValidacion) as e:
        ligas.crear(DatosLiga(nombre="liga a"))
    assert "nombre" in e.value.campos


def test_torneo_crea_sus_dias(ligas, db):
    t = ligas.crear(
        DatosLiga(nombre="Copa Navidad", tipo=TIPO_TORNEO),
        dias_torneo=[date(2026, 12, 20), date(2026, 12, 19)],
    )
    dias = JornadaService(db).listar(t.id)
    assert [(d.jornada.numero, d.jornada.fecha_inicio) for d in dias] == [
        (1, date(2026, 12, 19)),
        (2, date(2026, 12, 20)),
    ]


def test_torneo_requiere_fecha(ligas):
    with pytest.raises(ErrorValidacion):
        ligas.crear(DatosLiga(nombre="Copa", tipo=TIPO_TORNEO), dias_torneo=[])


def test_archivar(ligas):
    liga = ligas.crear(DatosLiga(nombre="Liga A"))
    ligas.cambiar_activa(liga.id, False)
    assert ligas.listar() == [] and len(ligas.listar(activas=False)) == 1
    assert not ligas.hay_ligas()


def test_equipos_varios(ligas):
    liga = ligas.crear(DatosLiga(nombre="Liga A"))
    ligas.equipos.crear(liga.id, "Tigres")
    creados, omitidos = ligas.equipos.crear_varios(liga.id, "Pumas\n\n  tigres \nÁguilas\npumas")
    assert creados == ["Pumas", "Águilas"]
    assert omitidos == ["tigres", "pumas"]
    assert [e.nombre for e in ligas.equipos.listar(liga.id)] == ["Águilas", "Pumas", "Tigres"]


def test_equipo_duplicado_y_renombrar(ligas):
    liga = ligas.crear(DatosLiga(nombre="Liga A"))
    t = ligas.equipos.crear(liga.id, "Tigres")
    p = ligas.equipos.crear(liga.id, "Pumas")
    with pytest.raises(ErrorValidacion):
        ligas.equipos.actualizar(p.id, "TIGRES")
    ligas.equipos.crear(liga.id, "Águilas")
    with pytest.raises(ErrorValidacion):
        ligas.equipos.crear(liga.id, "aguilas")
    ligas.equipos.actualizar(t.id, "Tigres FC")
    assert [e.nombre for e in ligas.equipos.listar(liga.id)] == ["Águilas", "Pumas", "Tigres FC"]


def test_mismo_equipo_en_otra_liga(ligas):
    a = ligas.crear(DatosLiga(nombre="Liga A"))
    b = ligas.crear(DatosLiga(nombre="Liga B"))
    ligas.equipos.crear(a.id, "Tigres")
    ligas.equipos.crear(b.id, "Tigres")


def test_tarifas_y_posiciones(ligas):
    liga = ligas.crear(DatosLiga(nombre="Liga A"))
    assert ligas.tarifas(liga.id)["central"] == 0
    ligas.configurar_posiciones_y_tarifas(
        liga.id, ["asistente_2", "central"], {"central": 35000, "asistente_1": 20000}
    )
    assert ligas.obtener(liga.id).lista_posiciones == ["central", "asistente_2"]
    assert ligas.tarifas(liga.id) == {"central": 35000, "asistente_1": 20000, "asistente_2": 0, "cuarto": 0}
    with pytest.raises(ErrorValidacion):
        ligas.configurar_posiciones_y_tarifas(liga.id, [], {})
