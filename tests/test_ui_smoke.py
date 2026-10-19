"""Construye cada pantalla y diálogo con una página falsa.

No dibuja nada; detecta parámetros inválidos de Flet y errores al armar las vistas.
"""

from types import SimpleNamespace

import flet as ft
import pytest

from datetime import date, time

from arbitros.db.models import ROL_CONSULTA, TIPO_TORNEO
from arbitros.services.arbitros import DatosArbitro
from arbitros.services.jornadas import DatosPartido
from arbitros.services.ligas import DatosLiga
from arbitros.ui.app import App
from arbitros.ui.shell import Shell
from arbitros.ui.vistas import acceso, arbitros, jornadas, ligas, respaldos, usuarios


class PaginaFalsa:
    def __init__(self):
        self.controls = []
        self.dialogos = []
        self.theme_mode = ft.ThemeMode.LIGHT
        self.window = SimpleNamespace()

    def add(self, *controles):
        self.controls.extend(controles)

    def update(self, *_):
        pass

    def show_dialog(self, d):
        self.dialogos.append(d)

    def pop_dialog(self):
        return self.dialogos.pop() if self.dialogos else None


@pytest.fixture
def app(db, rutas):
    a = App(PaginaFalsa(), rutas, db)
    a.auth.crear_admin_inicial("admin", "Coordinador General", "secreta1")
    a.usuario = a.auth.autenticar("admin", "secreta1")
    a.arbitros.crear(DatosArbitro(nombre="Juan Pérez", telefono="3312345678"))
    a.respaldos.crear()
    liga = a.ligas.crear(DatosLiga(nombre="Liga Sabatina", posiciones=["central", "asistente_1"]))
    a.ligas.equipos.crear_varios(liga.id, "Tigres\nPumas")
    campo = a.ligas.campos.crear(liga.id, "Campo 1")
    eq = {e.nombre: e.id for e in a.ligas.equipos.listar(liga.id)}
    j = a.jornadas.crear(liga.id, date(2026, 10, 24))
    a.jornadas.crear_partido(
        j.id, DatosPartido(date(2026, 10, 24), time(10), eq["Tigres"], eq["Pumas"], campo.id, ["central"])
    )
    a.ligas.crear(DatosLiga(nombre="Copa Relámpago", tipo=TIPO_TORNEO), dias_torneo=[date(2026, 11, 1)])
    return a


def test_pantallas_de_acceso(app):
    acceso.pantalla_login(app, "Hola")
    acceso.pantalla_configuracion_inicial(app)
    acceso.pantalla_recuperar(app)
    acceso.mostrar_clave_recuperacion(app, "ABCD-EFGH-JKLM-NPQR", lambda: None)
    assert app.page.dialogos


@pytest.mark.parametrize("rol_admin", [True, False])
def test_todas_las_secciones(app, rol_admin):
    if not rol_admin:
        app.auth.crear_usuario("lector", "Lector", "secreta2", ROL_CONSULTA)
        app.usuario = app.auth.autenticar("lector", "secreta2")
    shell = Shell(app)
    shell.construir()
    claves = [s.clave for s in shell.secciones]
    assert ("usuarios" in claves) == rol_admin
    for clave in claves:
        shell.ir_a(clave)
        assert shell.contenido.content is not None


def test_dialogos(app):
    vista = arbitros.VistaArbitros(app)
    vista.construir()
    vista.abrir_formulario()
    vista.abrir_formulario(app.arbitros.listar()[0])
    vu = usuarios.VistaUsuarios(app)
    vu.construir()
    vu._nuevo()
    vu._restablecer(app.usuario)
    usuarios.dialogo_cambiar_mi_password(app)
    respaldos.VistaRespaldos(app).construir()
    assert len(app.page.dialogos) == 5


def test_flujo_login(app):
    usuario = app.usuario
    app.iniciar()
    assert app.usuario is None and app.page.controls
    app.entrar(usuario)
    assert app.usuario.es_admin


def test_ligas_y_jornadas(app):
    shell = Shell(app)
    shell.construir()
    vl = ligas.VistaLigas(app, shell)
    vl.construir()
    vl.dialogo_nueva()
    for r in app.ligas.listar():
        for pestana in ("equipos", "campos", "tarifas"):
            vl.mostrar_detalle(r.liga.id, pestana)
        vl.dialogo_editar(r.liga)
    vl.mostrar_lista()

    vj = jornadas.VistaJornadas(app, shell)
    vj.construir()
    for r in app.ligas.listar():
        vj.cambiar_liga(r.liga.id)
        for rj in vj.jornadas:
            vj.seleccionar(rj.jornada.id)
            vj.dialogo_jornada(rj)
            vj.dialogo_partido(rj.jornada.id)
            partidos = app.jornadas.listar_partidos(rj.jornada.id)
            for p in partidos:
                vj.dialogo_partido(rj.jornada.id, p)
            if partidos:
                vj.dialogo_cancelar_varios(partidos)
                vj.dialogo_cancelar_varios(partidos[:1])
                # Partido cancelado: tabla, menú y formulario con motivo
                vj._cambiar_estado(partidos[:1], "cancelado", "Lluvia")
                vj.dialogo_partido(rj.jornada.id, app.jornadas.obtener_partido(partidos[0].id))
        vj.dialogo_jornada()
    assert app.page.dialogos


def test_jornadas_sin_ligas(db, rutas):
    a = App(PaginaFalsa(), rutas, db)
    a.auth.crear_admin_inicial("admin", "Admin", "secreta1")
    a.usuario = a.auth.autenticar("admin", "secreta1")
    shell = Shell(a)
    shell.construir()
    shell.ir_a("jornadas")
    shell.ir_a("ligas")
