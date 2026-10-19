"""Construye cada pantalla y diálogo con una página falsa.

No dibuja nada; detecta parámetros inválidos de Flet y errores al armar las vistas.
"""

from types import SimpleNamespace

import flet as ft
import pytest

from arbitros.db.models import ROL_CONSULTA
from arbitros.services.arbitros import DatosArbitro
from arbitros.ui.app import App
from arbitros.ui.shell import Shell
from arbitros.ui.vistas import acceso, arbitros, respaldos, usuarios


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
