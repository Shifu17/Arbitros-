from datetime import date, time
from urllib.parse import unquote

import pytest

from arbitros.db.models import ESTADO_CANCELADO
from arbitros.services.arbitros import ArbitroService, DatosArbitro
from arbitros.services.asignaciones import AsignacionService
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.jornadas import DatosPartido, JornadaService
from arbitros.services.ligas import DatosLiga, LigaService
from arbitros.services.rol import AGRUPAR_ARBITRO, AGRUPAR_HORA, OpcionesRol, RolService
from arbitros.services.rol_imagen import generar_png

SAB = date(2026, 10, 24)


@pytest.fixture
def ctx(db):
    ligas, jornadas, arbitros = LigaService(db), JornadaService(db), ArbitroService(db)
    asig = AsignacionService(db, ConfiguracionService(db))
    rol = RolService(db, jornadas, asig)
    liga = ligas.crear(DatosLiga(nombre="Liga Sabatina", posiciones=["central", "asistente_1"]))
    oro = ligas.categorias.crear(liga.id, "Oro")
    ligas.equipos.crear_varios(liga.id, "Tigres\nPumas\nÁguilas\nToros\nLeones\nHalcones", categoria_id=oro.id)
    c1 = ligas.campos.crear(liga.id, "Campo 1")
    c2 = ligas.campos.crear(liga.id, "Campo 2")
    eq = {e.nombre: e.id for e in ligas.equipos.listar(liga.id)}
    j = jornadas.crear(liga.id, SAB)

    def partido(local, visitante, campo, hora):
        return jornadas.crear_partido(j.id, DatosPartido(SAB, hora, eq[local], eq[visitante], campo.id,
                                                         ["central", "asistente_1"], categoria_id=oro.id), forzar=True)

    p1 = partido("Tigres", "Pumas", c1, time(9))
    p2 = partido("Águilas", "Toros", c2, time(9))
    p3 = partido("Leones", "Halcones", c1, time(11))
    juan = arbitros.crear(DatosArbitro(nombre="Juan Pérez", telefono="3311111111", apodo="Juanito"))
    ana = arbitros.crear(DatosArbitro(nombre="Ana López", telefono="3322222222"))
    asig.asignar(p1.id, "central", juan.id, forzar=True)
    asig.asignar(p1.id, "asistente_1", ana.id, forzar=True)
    asig.asignar(p3.id, "central", juan.id, forzar=True)
    return dict(rol=rol, jornadas=jornadas, asig=asig, j=j, p1=p1, p2=p2, p3=p3, juan=juan, ana=ana, oro=oro)


def test_texto_por_campo(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(nota="Llegar 20 min antes"))
    assert "*LIGA SABATINA*" in texto and "Jornada 1" in texto and "Sábado 24 de octubre" in texto
    assert texto.index("CAMPO 1") < texto.index("CAMPO 2")
    # Dentro de Campo 1, el de las 9 antes que el de las 11
    assert texto.index("Tigres vs Pumas") < texto.index("Leones vs Halcones")
    assert "Central: Juan Pérez" in texto and "_Por asignar_" in texto
    assert "Faltan 3 árbitros por confirmar" in texto and "📌 Llegar 20 min antes" in texto


def test_texto_por_hora_y_apodos(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(agrupar=AGRUPAR_HORA, usar_apodos=True))
    assert "🕒 *09:00*" in texto and "Central: Juanito" in texto
    assert texto.index("09:00") < texto.index("11:00")


def test_texto_por_arbitro(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(agrupar=AGRUPAR_ARBITRO))
    assert texto.index("Ana López") < texto.index("Juan Pérez")
    assert texto.count("Juan Pérez") == 1 and "(Central)" in texto


def test_cancelados(ctx):
    ctx["jornadas"].cambiar_estado([ctx["p2"].id], ESTADO_CANCELADO, "Lluvia")
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol())
    assert "CANCELADOS" in texto and "Lluvia" in texto
    assert "CAMPO 2" not in texto
    sin = ctx["rol"].texto(ctx["j"].id, OpcionesRol(incluir_cancelados=False))
    assert "CANCELADOS" not in sin


def test_filtro_categoria(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(categoria_id=ctx["oro"].id))
    assert "Categoría: *Oro*" in texto
    assert "No hay partidos" in ctx["rol"].texto(ctx["j"].id, OpcionesRol(categoria_id=999))


def test_mensajes_individuales(ctx):
    mensajes = ctx["rol"].mensajes_individuales(ctx["j"].id)
    assert [a.nombre for a, _, _ in mensajes] == ["Ana López", "Juan Pérez"]
    _, texto, enlace = mensajes[1]
    assert texto.startswith("Hola Juanito") and texto.count("🏟️") == 2
    assert enlace.startswith("https://wa.me/523311111111?text=") and unquote(enlace.split("text=")[1]) == texto


def test_cambios_desde_publicacion(ctx):
    rol, asig, jornadas = ctx["rol"], ctx["asig"], ctx["jornadas"]
    assert rol.cambios(ctx["j"].id) is None
    rol.publicar(ctx["j"].id)
    assert rol.cambios(ctx["j"].id) == []
    asig.quitar(ctx["p1"].id, "asistente_1")
    asig.asignar(ctx["p1"].id, "central", ctx["ana"].id, forzar=True)
    jornadas.cambiar_estado([ctx["p2"].id], ESTADO_CANCELADO, "Lluvia")
    p3 = ctx["p3"]
    jornadas.actualizar_partido(p3.id, DatosPartido(SAB, time(12), p3.local_id, p3.visitante_id, p3.campo_id,
                                                    p3.lista_posiciones, categoria_id=p3.categoria_id), forzar=True)
    cambios = rol.cambios(ctx["j"].id)
    texto = "\n".join(cambios)
    assert "Central: Juan Pérez → *Ana López*" in texto
    assert "Asistente 1: Ana López → *Por asignar*" in texto
    assert "CANCELADO" in texto and "Lluvia" in texto
    assert "ahora Sábado 24 de octubre 12:00" in texto and "antes Sábado 24 de octubre 11:00" in texto
    assert rol.texto_cambios(ctx["j"].id).startswith("🔄 *CAMBIOS AL ROL")
    rol.publicar(ctx["j"].id)
    assert rol.cambios(ctx["j"].id) == []


def test_partido_nuevo_y_eliminado_en_cambios(ctx):
    rol, jornadas = ctx["rol"], ctx["jornadas"]
    rol.publicar(ctx["j"].id)
    jornadas.eliminar_partido(ctx["p2"].id)
    texto = "\n".join(rol.cambios(ctx["j"].id))
    assert "Se quitó" in texto and "Águilas vs Toros" in texto


def test_imagen_png(ctx):
    datos = ctx["rol"].datos(ctx["j"].id, OpcionesRol(nota="Llegar 20 minutos antes"))
    png = generar_png(datos, OpcionesRol(nota="Llegar 20 minutos antes"))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000
    png_hora = generar_png(datos, OpcionesRol(agrupar=AGRUPAR_HORA))
    assert png_hora[:4] == b"\x89PNG"
