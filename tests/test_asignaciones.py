from datetime import date, time

import pytest

from arbitros.db.models import DISP_HORARIO, DISP_NO_DISPONIBLE, DISP_TODO_EL_DIA, ESTADO_CANCELADO
from arbitros.services.arbitros import ArbitroService, DatosArbitro
from arbitros.services.asignaciones import (
    CONFLICTO,
    LIBRE,
    NO_DISPONIBLE,
    SIN_REGISTRAR,
    AsignacionService,
)
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.disponibilidad import DatosDisponibilidad, DisponibilidadService, dias_de_semana, lunes_de
from arbitros.services.errores import AvisosPendientes, ErrorValidacion
from arbitros.services.jornadas import DatosPartido, JornadaService
from arbitros.services.ligas import DatosLiga, LigaService

SAB = date(2026, 10, 24)


@pytest.fixture
def ctx(db):
    ligas, jornadas, arbitros = LigaService(db), JornadaService(db), ArbitroService(db)
    disp = DisponibilidadService(db)
    asig = AsignacionService(db, ConfiguracionService(db))
    liga = ligas.crear(DatosLiga(nombre="Liga A", posiciones=["central", "asistente_1"]))
    ligas.equipos.crear_varios(liga.id, "Tigres\nPumas\nÁguilas\nToros")
    c1 = ligas.campos.crear(liga.id, "Campo 1")
    c2 = ligas.campos.crear(liga.id, "Campo 2")
    eq = {e.nombre: e.id for e in ligas.equipos.listar(liga.id)}
    j = jornadas.crear(liga.id, SAB)
    p10 = jornadas.crear_partido(
        j.id, DatosPartido(SAB, time(10), eq["Tigres"], eq["Pumas"], c1.id, ["central", "asistente_1"]))
    p11 = jornadas.crear_partido(j.id, DatosPartido(SAB, time(11), eq["Águilas"], eq["Toros"], c2.id, ["central"]))
    juan = arbitros.crear(DatosArbitro(nombre="Juan Pérez", telefono="3311111111"))
    ana = arbitros.crear(DatosArbitro(nombre="Ana López", telefono="3322222222"))
    luis = arbitros.crear(DatosArbitro(nombre="Luis Mora", telefono="3333333333"))
    return dict(ligas=ligas, jornadas=jornadas, arbitros=arbitros, disp=disp, asig=asig, j=j, p10=p10, p11=p11,
                juan=juan, ana=ana, luis=luis)


def test_semana():
    assert lunes_de(SAB) == date(2026, 10, 19)
    assert dias_de_semana(date(2026, 10, 19))[5] == SAB


def test_disponibilidad_guardar_y_borrar(ctx):
    d = ctx["disp"]
    d.guardar(ctx["juan"].id, [SAB], DatosDisponibilidad(DISP_HORARIO, time(9), time(14), "Sale temprano"))
    fila = d.de_dia(ctx["juan"].id, SAB)
    assert (fila.tipo, fila.desde, fila.hasta, fila.nota) == (DISP_HORARIO, time(9), time(14), "Sale temprano")
    d.guardar(ctx["juan"].id, [SAB], DatosDisponibilidad(DISP_TODO_EL_DIA))
    fila = d.de_dia(ctx["juan"].id, SAB)
    assert fila.tipo == DISP_TODO_EL_DIA and fila.desde is None
    d.guardar(ctx["juan"].id, [SAB], DatosDisponibilidad(None))
    assert d.de_dia(ctx["juan"].id, SAB) is None


def test_horario_invalido(ctx):
    with pytest.raises(ErrorValidacion) as e:
        ctx["disp"].guardar(ctx["juan"].id, [SAB], DatosDisponibilidad(DISP_HORARIO, time(14), time(9)))
    assert "hasta" in e.value.campos


def test_copiar_semana_y_marcar_todos(ctx):
    d = ctx["disp"]
    lunes = lunes_de(SAB)
    d.guardar(ctx["juan"].id, [SAB], DatosDisponibilidad(DISP_NO_DISPONIBLE))
    assert d.marcar_dia_para_todos(SAB, DatosDisponibilidad(DISP_TODO_EL_DIA)) == 2  # Juan ya tenía
    siguiente = date(2026, 10, 26)
    assert d.copiar_semana(lunes, siguiente) == 3
    assert d.de_dia(ctx["juan"].id, date(2026, 10, 31)).tipo == DISP_NO_DISPONIBLE
    assert d.copiar_semana(lunes, siguiente) == 0  # no sobrescribe
    assert d.copiar_semana(lunes, siguiente, sobrescribir=True) == 3


def test_candidatos_ordenados(ctx):
    d, asig = ctx["disp"], ctx["asig"]
    d.guardar(ctx["ana"].id, [SAB], DatosDisponibilidad(DISP_TODO_EL_DIA))
    d.guardar(ctx["luis"].id, [SAB], DatosDisponibilidad(DISP_NO_DISPONIBLE, nota="Trabaja"))
    cands = asig.candidatos(ctx["p10"].id, "central")
    assert [(c.arbitro.nombre, c.estado) for c in cands] == [
        ("Ana López", LIBRE), ("Juan Pérez", SIN_REGISTRAR), ("Luis Mora", NO_DISPONIBLE)]
    assert "Trabaja" in cands[2].avisos[0]


def test_asignar_y_avisos(ctx):
    d, asig = ctx["disp"], ctx["asig"]
    d.guardar(ctx["ana"].id, [SAB], DatosDisponibilidad(DISP_TODO_EL_DIA))
    asig.asignar(ctx["p10"].id, "central", ctx["ana"].id)
    # 11:00 está a menos de 60+30 min del de las 10:00 → choque
    with pytest.raises(AvisosPendientes) as e:
        asig.asignar(ctx["p11"].id, "central", ctx["ana"].id)
    assert "ya tiene partido a las 10:00" in e.value.avisos[0]
    asig.asignar(ctx["p11"].id, "central", ctx["ana"].id, forzar=True)
    assert len(asig.revisar_jornada(ctx["j"].id)) == 2
    # Sin disponibilidad registrada → aviso
    with pytest.raises(AvisosPendientes):
        asig.asignar(ctx["p10"].id, "asistente_1", ctx["juan"].id)


def test_ajuste_de_duracion_elimina_choque(ctx):
    d, asig = ctx["disp"], ctx["asig"]
    d.guardar(ctx["ana"].id, [SAB], DatosDisponibilidad(DISP_TODO_EL_DIA))
    asig.guardar_ajustes(50, 10)
    asig.asignar(ctx["p10"].id, "central", ctx["ana"].id)
    asig.asignar(ctx["p11"].id, "central", ctx["ana"].id)  # 60 min de separación ≥ 50+10
    assert asig.revisar_jornada(ctx["j"].id) == {}
    with pytest.raises(ErrorValidacion):
        asig.guardar_ajustes(5, 10)


def test_fuera_de_horario(ctx):
    ctx["disp"].guardar(ctx["ana"].id, [SAB], DatosDisponibilidad(DISP_HORARIO, time(8), time(10, 30)))
    [c] = [c for c in ctx["asig"].candidatos(ctx["p10"].id, "central") if c.arbitro.id == ctx["ana"].id]
    assert c.estado == CONFLICTO and "solo puede de 08:00 a 10:30" in c.avisos[0]


def test_errores_duros(ctx):
    asig, j = ctx["asig"], ctx["jornadas"]
    asig.asignar(ctx["p10"].id, "central", ctx["ana"].id, forzar=True)
    with pytest.raises(ErrorValidacion):
        asig.asignar(ctx["p10"].id, "asistente_1", ctx["ana"].id, forzar=True)  # repetido en el partido
    with pytest.raises(ErrorValidacion):
        asig.asignar(ctx["p11"].id, "asistente_1", ctx["juan"].id, forzar=True)  # p11 no lleva asistente
    ctx["arbitros"].cambiar_activo(ctx["luis"].id, False)
    with pytest.raises(ErrorValidacion):
        asig.asignar(ctx["p11"].id, "central", ctx["luis"].id, forzar=True)
    j.cambiar_estado([ctx["p11"].id], ESTADO_CANCELADO)
    with pytest.raises(ErrorValidacion):
        asig.asignar(ctx["p11"].id, "central", ctx["juan"].id, forzar=True)


def test_reemplazar_quitar_y_faltantes(ctx):
    asig, jornadas = ctx["asig"], ctx["jornadas"]
    asig.asignar(ctx["p10"].id, "central", ctx["ana"].id, forzar=True)
    asig.asignar(ctx["p10"].id, "central", ctx["juan"].id, forzar=True)
    assert asig.de_partido(ctx["p10"].id)["central"].arbitro.nombre == "Juan Pérez"
    partidos = jornadas.listar_partidos(ctx["j"].id)
    assert asig.faltantes(partidos, asig.de_jornada(ctx["j"].id)) == 2  # A1 del de 10 y central del de 11
    asig.quitar(ctx["p10"].id, "central")
    assert asig.de_partido(ctx["p10"].id) == {}
    assert asig.partidos_por_arbitro(SAB, SAB) == {}


def test_quitar_posicion_del_partido_libera_asignacion(ctx):
    asig, jornadas = ctx["asig"], ctx["jornadas"]
    asig.asignar(ctx["p10"].id, "asistente_1", ctx["ana"].id, forzar=True)
    p = ctx["p10"]
    jornadas.actualizar_partido(
        p.id, DatosPartido(p.fecha, p.hora, p.local_id, p.visitante_id, p.campo_id, ["central"]))
    assert asig.de_partido(p.id) == {}


def test_partido_cancelado_no_cuenta_para_choques(ctx):
    asig, jornadas = ctx["asig"], ctx["jornadas"]
    ctx["disp"].guardar(ctx["ana"].id, [SAB], DatosDisponibilidad(DISP_TODO_EL_DIA))
    asig.asignar(ctx["p10"].id, "central", ctx["ana"].id)
    jornadas.cambiar_estado([ctx["p10"].id], ESTADO_CANCELADO)
    asig.asignar(ctx["p11"].id, "central", ctx["ana"].id)  # sin avisos
    assert asig.partidos_por_arbitro(SAB, SAB) == {(ctx["ana"].id, SAB): 1}
