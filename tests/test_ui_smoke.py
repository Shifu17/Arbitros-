"""Construye cada pantalla y diálogo con una página falsa.

No dibuja nada; detecta parámetros inválidos de Flet y errores al armar las vistas.
"""

import dataclasses
from types import SimpleNamespace

import flet as ft
from flet.controls.base_control import BaseControl
from flet.utils.validation import validate
import pytest

from datetime import date, time

from arbitros import colegios
from arbitros.db.models import DISP_HORARIO, ROL_CONSULTA, TIPO_TORNEO
from arbitros.services.disponibilidad import DatosDisponibilidad
from arbitros.services.arbitros import DatosArbitro
from arbitros.services.jornadas import DatosPartido
from arbitros.services.ligas import DatosLiga
from arbitros.ui.app import App
from arbitros.ui.shell import Shell
from arbitros.ui.vistas import (
    acceso, arbitros, cedulas, cobros, disponibilidad, jornadas, ligas, pagos, reportes, respaldos, rol, usuarios,
)


def validar_arbol(control, vistos=None) -> None:
    """Aplica las mismas validaciones que Flet hace al actualizar (p. ej. una celda con su control oculto)."""
    vistos = set() if vistos is None else vistos
    if id(control) in vistos or not getattr(control, "visible", True):
        return
    vistos.add(id(control))
    validate(control)
    for f in dataclasses.fields(control):
        if f.name.startswith("_") or f.name == "parent":
            continue
        valor = getattr(control, f.name, None)
        for hijo in (valor if isinstance(valor, list) else [valor]):
            if isinstance(hijo, BaseControl):
                validar_arbol(hijo, vistos)


class PaginaFalsa:
    def __init__(self):
        self.controls = []
        self.dialogos = []
        self.theme_mode = ft.ThemeMode.LIGHT
        self.window = SimpleNamespace()

    def add(self, *controles):
        self.controls.extend(controles)

    def update(self, *_):
        for c in [*self.controls, *self.dialogos]:
            validar_arbol(c)

    def show_dialog(self, d):
        validar_arbol(d)
        self.dialogos.append(d)

    def pop_dialog(self):
        return self.dialogos.pop() if self.dialogos else None


@pytest.fixture
def app(db, rutas):
    a = App(PaginaFalsa(), rutas.base)
    a.usar(colegios.COAHUILA, rutas, db)
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
    p1 = a.jornadas.listar_partidos(j.id)[0]
    a.jornadas.actualizar_partido(p1.id, DatosPartido(p1.fecha, p1.hora, p1.local_id, p1.visitante_id, p1.campo_id,
                                                      ["central", "asistente_1"]))
    juan = a.arbitros.listar()[0]
    a.arbitros.crear(DatosArbitro(nombre="Ana López", telefono="3322222222", apodo="Anita"))
    a.disponibilidad.guardar(juan.id, [date(2026, 10, 24)], DatosDisponibilidad(DISP_HORARIO, time(8), time(9), "Temprano"))
    a.asignaciones.asignar(p1.id, "central", juan.id, forzar=True)  # queda con aviso (fuera de horario)
    a.ligas.crear(DatosLiga(nombre="Copa Relámpago", tipo=TIPO_TORNEO), dias_torneo=[date(2026, 11, 1)])
    # Liga con categorías (sub-ligas)
    premier = a.ligas.crear(DatosLiga(nombre="Liga Premier"))
    oro = a.ligas.categorias.crear(premier.id, "Oro")
    a.ligas.categorias.crear(premier.id, "Plata")
    a.ligas.configurar_categoria(oro.id, ["central", "asistente_1"], {"central": 40000})
    a.ligas.configurar_cuota_equipo(premier.id, "futbol_11", 45000)
    a.ligas.equipos.crear_varios(premier.id, "Leones\nHalcones", categoria_id=oro.id)
    campo_p = a.ligas.campos.crear(premier.id, "Unidad Deportiva")
    eqp = {e.nombre: e.id for e in a.ligas.equipos.listar(premier.id)}
    jp = a.jornadas.crear(premier.id, date(2026, 10, 24))
    a.jornadas.crear_partido(jp.id, DatosPartido(date(2026, 10, 24), time(9), eqp["Leones"], eqp["Halcones"],
                                                 campo_p.id, ["central"], categoria_id=oro.id))
    # Liga de bardas: sus equipos juegan en todas las categorías
    bardas = a.ligas.crear(DatosLiga(nombre="Berrendos", modalidad="bardas", posiciones=["central", "anotador"]))
    juvenil = a.ligas.categorias.crear(bardas.id, "Juvenil")
    a.ligas.categorias.crear(bardas.id, "Mayor")
    a.ligas.configurar_categoria(juvenil.id, None, {"central": 30000, "anotador": 10000})
    a.ligas.equipos.crear_varios(bardas.id, "Toros\nVenados")
    a.ligas.campos.crear(bardas.id, "Bardas Norte")
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


def test_elegir_colegio(tmp_path):
    a = App(PaginaFalsa(), tmp_path)
    a.iniciar()
    validar_arbol(a.page.controls[-1])
    # Un colegio nuevo arranca con su propia base vacía, en su carpeta, y pide crear el admin
    a.abrir_colegio(colegios.SALTILLO)
    assert colegios.activo() is colegios.SALTILLO
    assert a.rutas.base == tmp_path / "colegios" / "saltillo" and a.rutas.db.exists()
    assert not a.auth.hay_usuarios()
    assert "Saltillo" in a.page.title
    a.auth.crear_admin_inicial("admin", "Admin Saltillo", "secreta1")
    a.entrar(a.auth.autenticar("admin", "secreta1"))
    validar_arbol(a.page.controls[-1])
    # Saltillo pide foto del árbitro y logo de la liga (para la designación)
    from PIL import Image

    juan = a.arbitros.crear(DatosArbitro(nombre="Juan Pérez", telefono="3312345678"))
    Image.new("RGB", (50, 50), "red").save(tmp_path / "foto.png")
    a.imagenes.guardar_foto(juan.id, tmp_path / "foto.png")
    vista = arbitros.VistaArbitros(a)
    vista.construir()
    vista.abrir_formulario(a.arbitros.obtener(juan.id))
    vista.abrir_formulario()
    liga = a.ligas.crear(DatosLiga(nombre="Liga Saltillo", posiciones=["central"]))
    ligas.VistaLigas(a, Shell(a)).dialogo_editar(liga)
    a.page.update()
    assert len(a.page.dialogos) == 3
    # Coahuila sigue usando la carpeta de siempre y no ve los usuarios de Saltillo
    a.abrir_colegio(colegios.COAHUILA)
    assert a.rutas.base == tmp_path and not a.auth.hay_usuarios()
    a.db.cerrar()


def test_ligas_y_jornadas(app):
    shell = Shell(app)
    shell.construir()
    vl = ligas.VistaLigas(app, shell)
    vl.construir()
    vl.dialogo_nueva()
    for r in app.ligas.listar():
        for pestana in ("categorias", "equipos", "campos", "tarifas"):
            vl.mostrar_detalle(r.liga.id, pestana)
            validar_arbol(vl.cuerpo)
        vl.dialogo_editar(r.liga)
        for panel in (ligas.PanelEquipos(app, r.liga), ligas.PanelCampos(app, r.liga), ligas.PanelCategorias(app, r.liga)):
            panel.construir()
            panel._varios()
            for item in panel.catalogo.listar(r.liga.id):
                panel._editar(item)
                if isinstance(panel, ligas.PanelCategorias):
                    panel._configurar(item)
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
                for pos in partidos[0].lista_posiciones:
                    vj.dialogo_asignar(partidos[0], pos)
                vj._asignar_siguiente_faltante()
                vj._cambiar_estado(partidos[:1], "cancelado", "Lluvia")
                vj.dialogo_partido(rj.jornada.id, app.jornadas.obtener_partido(partidos[0].id))
        vj.dialogo_jornada()
    assert app.page.dialogos


def test_jornadas_sin_ligas(db, rutas):
    a = App(PaginaFalsa(), rutas.base)
    a.usar(colegios.COAHUILA, rutas, db)
    a.auth.crear_admin_inicial("admin", "Admin", "secreta1")
    a.usuario = a.auth.autenticar("admin", "secreta1")
    shell = Shell(a)
    shell.construir()
    shell.ir_a("jornadas")
    shell.ir_a("ligas")


def test_disponibilidad(app):
    vd = disponibilidad.VistaDisponibilidad(app)
    app.seleccion["semana"] = date(2026, 10, 19)
    vd = disponibilidad.VistaDisponibilidad(app)
    vd.construir()
    juan = app.arbitros.listar()[0]
    vd._editar(juan, date(2026, 10, 24), app.disponibilidad.de_dia(juan.id, date(2026, 10, 24)))
    vd._editar(juan, date(2026, 10, 25), None)
    vd._ajustes()
    vd._copiar()
    vd._mover(7)
    vd.busqueda.value = "zzz"
    vd.refrescar()


def test_rol(app):
    shell = Shell(app)
    shell.construir()
    for r in app.ligas.listar():
        app.seleccion["liga_id"] = r.liga.id
        app.seleccion["jornada_id"] = None
        vr = rol.VistaRol(app, shell)
        vr.construir()
        for agrupar in ("campo", "hora", "arbitro"):
            vr.opciones.agrupar = agrupar
            for modo in ("texto", "imagen"):
                vr.modo = modo
                vr.refrescar()
        vr._dialogo_individual()
        vr._publicar()
        vr.refrescar()
    assert "**" in rol.whatsapp_a_markdown("*Hola* _bien_ ~no~")


def test_pagos_cedulas_reportes(app, tmp_path):
    shell = Shell(app)
    shell.construir()
    juan = app.arbitros.listar()[0]
    linea = app.pagos.lineas()[0]
    app.pagos.registrar_en_campo(linea.asignacion_id, 0, tarifa=30000)
    vp = pagos.VistaPagos(app, shell)
    vp.construir()
    vp.filtro.periodo.value = "todo"
    for pestana in ("arbitros", "campo", "historial", "equipos"):
        vp.pestana = pestana
        vp.refrescar()
    # Cobro a equipos: pestaña, diálogos y recibo
    pe = cobros.PanelEquipos(app, shell)
    pe.construir()
    l = app.cobros.lineas()[0]
    pe._dialogo_registrar(l)
    pe._completo(l)
    pe._recibo(l)
    pe._deshacer(app.cobros.lineas()[0])
    pe._todos_completo([x.clave for x in app.cobros.lineas()])
    # Pagos adelantados: diálogo, tabla y borrar
    pe._dialogo_abono()
    abono = app.cobros.registrar_abono(l.equipo.id, 100000, nota="De la temporada pasada")
    pe.refrescar()
    pe._borrar_abono(abono)
    app.cobros.registrar_abono(l.rival.id, 20000)
    pe._dialogo_registrar(next(x for x in app.cobros.lineas() if x.abonado))
    app.cobros.registrar(l.partido.id, l.equipo.id, 100, forma_pago="efectivo", nota="Parcial")
    pe.refrescar()
    app.usuario = SimpleNamespace(nombre="Consulta", es_admin=False, rol=ROL_CONSULTA)
    pe.refrescar()
    app.usuario = app.auth.autenticar("admin", "secreta1")
    r = app.pagos.resumen_por_arbitro()[0]
    vp._detalle(r)
    vp._estado_cuenta(r)
    vp._dialogo_pagar(juan.id)
    pendientes = app.pagos.pendientes_de(juan.id)
    if pendientes:
        app.pagos.liquidar(juan.id, [l.asignacion_id for l in pendientes])
    vp.pestana = "historial"
    vp.refrescar()

    p = app.cedulas.listar()[0].partido
    foto = tmp_path / "c.png"
    foto.write_bytes(b"png")
    app.cedulas.subir(p.id, [foto])
    vc = cedulas.VistaCedulas(app)
    vc.construir()
    for filtro in ("pendientes", "registradas", "excepciones", "todas"):
        vc.filtro_estado = filtro
        vc.refrescar()
    fila = app.cedulas.listar()[0]
    vc._excepcion(fila)

    vr = reportes.VistaReportes(app, shell)
    vr.construir()
    vr.filtro.periodo.value = "todo"
    vr.refrescar()
    vr._recibo(app.cobros.resumen_por_equipo()[0].equipo.id)
    vr._ir_a_cobros()
    va = arbitros.VistaArbitros(app)
    va.construir()
    va._historial(juan)
    for clave in ("inicio", "pagos", "cedulas", "reportes"):
        shell.ir_a(clave)


def test_dialogo_actualizacion(app):
    from arbitros.services.actualizador import InfoVersion

    app._dialogo_actualizacion(InfoVersion("9.9.9", "- Novedad", "https://github.com/x", "A-9.9.9-instalador.exe", 10, None))
    assert app.page.dialogos


def _controles(control, tipo):
    """Todos los controles de un tipo dentro de un árbol."""
    encontrados, pendientes, vistos = [], [control], set()
    while pendientes:
        c = pendientes.pop()
        if id(c) in vistos:
            continue
        vistos.add(id(c))
        if isinstance(c, tipo):
            encontrados.append(c)
        for f in dataclasses.fields(c):
            if f.name.startswith("_") or f.name == "parent":
                continue
            valor = getattr(c, f.name, None)
            pendientes += [h for h in (valor if isinstance(valor, list) else [valor]) if isinstance(h, BaseControl)]
    return encontrados


def test_tarifas_por_tipo_de_partido(app):
    liga = next(r.liga for r in app.ligas.listar() if r.liga.nombre == "Liga Sabatina")
    panel = ligas.PanelTarifas(app, liga).construir()
    campos = [c for c in _controles(panel, ft.TextField)]
    assert len(campos) == 3 + 4 + 2 + 3  # arbitraje por equipo de cada tipo + pago al árbitro por posición
    for c in campos:
        c.value = "300"
    boton = next(b for b in _controles(panel, ft.FilledButton) if b.content == "Guardar")
    boton.on_click(None)
    assert app.ligas.cuota_equipo(liga.id, "futbol_7") == 30000
    assert app.ligas.tarifas(liga.id)["central"] == 30000


def test_liga_con_varios_tipos_de_partido(app):
    liga = app.ligas.crear(DatosLiga(nombre="Liga Mixta", posiciones=["central"], otras_modalidades=["bardas"]))
    app.ligas.equipos.crear_varios(liga.id, "Tigres\nPumas")
    app.ligas.campos.crear(liga.id, "Campo 1")
    bardas = app.ligas.campos.crear(liga.id, "Bardas Norte", modalidad="bardas")
    liga = app.ligas.obtener(liga.id)

    # Campos: cada cancha puede tener su tipo
    panel = ligas.PanelCampos(app, liga)
    validar_arbol(panel.construir())
    assert [c.data for c in panel.extra_alta] == ["modalidad"]
    panel._editar(next(c for c in app.ligas.campos.listar(liga.id) if c.id == bardas.id))
    tipo = next(c for c in app.page.dialogos[-1].content.controls if c.data == "modalidad")
    assert tipo.value == "bardas" and {o.key for o in tipo.options} == {"cualquiera", "futbol_11", "bardas"}

    # Tarifas: solo se ven los tipos que juega; marcar Fútbol 7 lo agrega
    panel = ligas.PanelTarifas(app, liga).construir()
    casillas_tipo = [c for c in _controles(panel, ft.Checkbox) if c.label == "Fútbol 7"]
    casillas_tipo[0].value = True
    casillas_tipo[0].on_change(SimpleNamespace(control=casillas_tipo[0]))
    validar_arbol(panel)
    boton = next(b for b in _controles(panel, ft.FilledButton) if b.content == "Guardar")
    boton.on_click(None)
    assert app.ligas.obtener(liga.id).lista_modalidades == ["futbol_11", "futbol_7", "bardas"]

    # Partido: al elegir la cancha de bardas el tipo cambia solo
    shell = Shell(app)
    shell.construir()
    vj = jornadas.VistaJornadas(app, shell)
    vj.construir()
    vj.cambiar_liga(liga.id)
    j = app.jornadas.crear(liga.id, date(2026, 10, 31))
    vj.dialogo_partido(j.id)
    dialogo = app.page.dialogos[-1]
    campo = next(d for d in _controles(dialogo, ft.Dropdown) if d.label == "Campo *")
    tipo = next(d for d in _controles(dialogo, ft.Dropdown) if d.label == "Tipo de partido")
    assert tipo.value == "futbol_11"
    campo.value = str(bardas.id)
    campo.on_select(None)
    assert tipo.value == "bardas"
