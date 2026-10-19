from datetime import date, time

import pytest

from arbitros.db.models import ESTADO_CANCELADO, ESTADO_PROGRAMADO, TIPO_TORNEO
from arbitros.services.errores import AvisosPendientes, ErrorValidacion
from arbitros.services.jornadas import DatosPartido, JornadaService, etiqueta_jornada, texto_a_hora
from arbitros.services.ligas import DatosLiga, LigaService

SAB = date(2026, 10, 24)
DOM = date(2026, 10, 25)


@pytest.fixture
def ligas(db):
    return LigaService(db)


@pytest.fixture
def svc(db):
    return JornadaService(db)


@pytest.fixture
def liga(ligas):
    liga = ligas.crear(DatosLiga(nombre="Liga A", posiciones=["central", "asistente_1"]))
    for n in ("Tigres", "Pumas", "Águilas", "Toros"):
        ligas.equipos.crear(liga.id, n)
    ligas.campos.crear(liga.id, "Campo 1")
    ligas.campos.crear(liga.id, "Campo 2")
    return liga


def _ids(ligas, liga):
    equipos = {e.nombre: e.id for e in ligas.equipos.listar(liga.id)}
    campos = {c.nombre: c.id for c in ligas.campos.listar(liga.id)}
    return equipos, campos


def _partido(eq, ca, local="Tigres", visitante="Pumas", campo="Campo 1", hora=time(10), fecha=SAB):
    return DatosPartido(
        fecha=fecha, hora=hora, local_id=eq[local], visitante_id=eq[visitante],
        campo_id=ca[campo], posiciones=["central"],
    )


def test_jornadas_numeracion(svc, liga):
    j1 = svc.crear(liga.id, SAB, DOM)
    j2 = svc.crear(liga.id, date(2026, 10, 31))
    assert (j1.numero, j2.numero) == (1, 2)
    assert svc.siguiente_numero(liga.id) == 3
    assert etiqueta_jornada(liga, j2) == "Jornada 2"
    with pytest.raises(ErrorValidacion) as e:
        svc.crear(liga.id, SAB, numero=1)
    assert "numero" in e.value.campos
    with pytest.raises(ErrorValidacion) as e:
        svc.crear(liga.id, DOM, SAB)
    assert "fecha_fin" in e.value.campos


def test_dias_de_torneo_se_renumeran(ligas, svc):
    t = ligas.crear(DatosLiga(nombre="Copa", tipo=TIPO_TORNEO), dias_torneo=[SAB])
    domingo = svc.crear(t.id, DOM)
    viernes = svc.crear(t.id, date(2026, 10, 23))
    numeros = {r.jornada.fecha_inicio: r.jornada.numero for r in svc.listar(t.id)}
    assert numeros == {date(2026, 10, 23): 1, SAB: 2, DOM: 3}
    # Cambiar la fecha reordena
    svc.actualizar(viernes.id, date(2026, 10, 26))
    numeros = {r.jornada.fecha_inicio: r.jornada.numero for r in svc.listar(t.id)}
    assert numeros == {SAB: 1, DOM: 2, date(2026, 10, 26): 3}
    svc.eliminar(domingo.id)
    assert [r.jornada.numero for r in svc.listar(t.id)] == [1, 2]
    assert etiqueta_jornada(t, svc.listar(t.id)[0].jornada) == "Día 1"


def test_crear_partido_y_listar_ordenado(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB, DOM)
    svc.crear_partido(j.id, _partido(eq, ca, "Águilas", "Toros", hora=time(12)))
    p = svc.crear_partido(j.id, _partido(eq, ca))
    assert p.local.nombre == "Tigres" and p.campo.nombre == "Campo 1"
    assert [x.local.nombre for x in svc.listar_partidos(j.id)] == ["Tigres", "Águilas"]
    assert svc.listar(liga.id)[0].partidos == 2


def test_errores_partido(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    with pytest.raises(ErrorValidacion) as e:
        svc.crear_partido(j.id, DatosPartido(None, None, eq["Tigres"], eq["Tigres"], None, []))
    assert set(e.value.campos) == {"fecha", "hora", "visitante", "campo", "posiciones"}


def test_equipo_de_otra_liga(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    otra = ligas.crear(DatosLiga(nombre="Liga B"))
    intruso = ligas.equipos.crear(otra.id, "Intruso")
    j = svc.crear(liga.id, SAB)
    datos = _partido(eq, ca)
    datos.visitante_id = intruso.id
    with pytest.raises(ErrorValidacion) as e:
        svc.crear_partido(j.id, datos)
    assert "visitante" in e.value.campos


def test_avisos_y_forzar(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB, DOM)
    svc.crear_partido(j.id, _partido(eq, ca))
    # Mismo campo 30 min después y Tigres repite
    choque = _partido(eq, ca, "Tigres", "Toros", hora=time(10, 30))
    with pytest.raises(AvisosPendientes) as e:
        svc.crear_partido(j.id, choque)
    textos = " ".join(e.value.avisos)
    assert "Tigres ya tiene otro partido" in textos and "Campo 1" in textos
    svc.crear_partido(j.id, choque, forzar=True)
    assert len(svc.listar_partidos(j.id)) == 2


def test_misma_hora_en_otro_campo_sin_avisos(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    svc.crear_partido(j.id, _partido(eq, ca))
    svc.crear_partido(j.id, _partido(eq, ca, "Águilas", "Toros", campo="Campo 2"))


def test_aviso_fecha_fuera_de_jornada(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB, DOM)
    with pytest.raises(AvisosPendientes) as e:
        svc.crear_partido(j.id, _partido(eq, ca, fecha=date(2026, 10, 27)))
    assert "fuera" in e.value.avisos[0]


def test_editar_no_choca_consigo_mismo(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    p = svc.crear_partido(j.id, _partido(eq, ca))
    datos = _partido(eq, ca, hora=time(10, 15))
    datos.posiciones = ["central", "cuarto"]
    actualizado = svc.actualizar_partido(p.id, datos)
    assert actualizado.lista_posiciones == ["central", "cuarto"]


def test_eliminar_jornada_borra_partidos(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    svc.crear_partido(j.id, _partido(eq, ca))
    svc.eliminar(j.id)
    assert svc.listar(liga.id) == []
    # El equipo ya no está en uso: se puede eliminar
    ligas.equipos.eliminar(eq["Tigres"])


def test_no_eliminar_equipo_o_campo_en_uso(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    svc.crear_partido(j.id, _partido(eq, ca))
    with pytest.raises(ErrorValidacion):
        ligas.equipos.eliminar(eq["Pumas"])
    with pytest.raises(ErrorValidacion):
        ligas.campos.eliminar(ca["Campo 1"])
    ligas.campos.eliminar(ca["Campo 2"])


def test_texto_a_hora():
    assert texto_a_hora("10") == time(10)
    assert texto_a_hora("1030") == time(10, 30)
    assert texto_a_hora("9:05") == time(9, 5)
    assert texto_a_hora("10.40") == time(10, 40)
    assert texto_a_hora("4:30 pm") == time(16, 30)
    assert texto_a_hora("4pm") == time(16)
    assert texto_a_hora("12 am") == time(0)
    assert texto_a_hora("16h") == time(16)
    for malo in ("", "25:00", "10:75", "abc", "10:3x"):
        assert texto_a_hora(malo) is None


def test_cancelar_varios_con_motivo(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    p1 = svc.crear_partido(j.id, _partido(eq, ca))
    p2 = svc.crear_partido(j.id, _partido(eq, ca, "Águilas", "Toros", campo="Campo 2"))
    assert svc.cambiar_estado([p1.id, p2.id], ESTADO_CANCELADO, " Lluvia ") == 2
    assert {(p.estado, p.motivo_estado) for p in svc.listar_partidos(j.id)} == {(ESTADO_CANCELADO, "Lluvia")}
    assert not svc.obtener_partido(p1.id).se_juega
    # Al reprogramar se borra el motivo
    svc.cambiar_estado([p1.id], ESTADO_PROGRAMADO, "ignorado")
    assert svc.obtener_partido(p1.id).motivo_estado is None
    with pytest.raises(ErrorValidacion):
        svc.cambiar_estado([], ESTADO_CANCELADO)


def test_cancelados_no_generan_choques(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    p = svc.crear_partido(j.id, _partido(eq, ca))
    svc.cambiar_estado([p.id], ESTADO_CANCELADO, "Lluvia")
    # Reprogramación: mismos equipos, mismo campo y hora → sin avisos
    svc.crear_partido(j.id, _partido(eq, ca))


def test_partidos_con_categoria(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    oro = ligas.categorias.crear(liga.id, "Oro")
    plata = ligas.categorias.crear(liga.id, "Plata")
    ligas.equipos.actualizar(eq["Tigres"], "Tigres", categoria_id=oro.id)
    ligas.equipos.actualizar(eq["Pumas"], "Pumas", categoria_id=oro.id)
    ligas.equipos.actualizar(eq["Toros"], "Toros", categoria_id=plata.id)
    j = svc.crear(liga.id, SAB)
    # La liga tiene categorías: es obligatorio elegirla
    with pytest.raises(ErrorValidacion) as e:
        svc.crear_partido(j.id, _partido(eq, ca))
    assert "categoria" in e.value.campos
    datos = _partido(eq, ca)
    datos.categoria_id = oro.id
    p = svc.crear_partido(j.id, datos)
    assert p.categoria.nombre == "Oro"
    # Equipo de otra categoría: aviso, no error
    cruzado = _partido(eq, ca, "Águilas", "Toros", campo="Campo 2")
    cruzado.categoria_id = oro.id
    with pytest.raises(AvisosPendientes) as e:
        svc.crear_partido(j.id, cruzado)
    assert "Toros es de la categoría Plata" in e.value.avisos[0]


def test_partidos_entre_solo_ligas_activas(ligas, svc, liga):
    eq, ca = _ids(ligas, liga)
    j = svc.crear(liga.id, SAB)
    svc.crear_partido(j.id, _partido(eq, ca))
    assert len(svc.partidos_entre(SAB, DOM)) == 1
    assert svc.partidos_entre(DOM, DOM) == []
    ligas.cambiar_activa(liga.id, False)
    assert svc.partidos_entre(SAB, DOM) == []
