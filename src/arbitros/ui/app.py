"""Orquestador de pantallas: configuración inicial → login → aplicación.

`App` es el único objeto que las vistas reciben: da acceso a la página, los
servicios y el usuario con sesión iniciada.
"""

import asyncio
import logging
import os
import tempfile
from pathlib import Path

import flet as ft

from arbitros import __version__
from arbitros.config import APP_NOMBRE, ORGANIZACION, REPO_ACTUALIZACIONES, Rutas, es_instalada
from arbitros.db.database import Database
from arbitros.db.migrar import migrar
from arbitros.db.models import Usuario
from arbitros.services.arbitros import ArbitroService
from arbitros.services.auth import AuthService
from arbitros.services.actualizador import Actualizador, ErrorActualizacion, InfoVersion
from arbitros.services.asignaciones import AsignacionService
from arbitros.services.cedulas import CedulaService
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.disponibilidad import DisponibilidadService
from arbitros.services.jornadas import JornadaService
from arbitros.services.ligas import LigaService
from arbitros.services.pagos import PagoService
from arbitros.services.reportes import ReporteService
from arbitros.services.respaldos import PREFIJO_ACTUALIZACION, RespaldoService
from arbitros.services.rol import RolService
from arbitros.ui import tema

log = logging.getLogger(__name__)

CLAVE_TEMA = "tema"


class App:
    def __init__(self, page: ft.Page, rutas: Rutas, db: Database):
        self.page = page
        self.rutas = rutas
        self.db = db
        self.config = ConfiguracionService(db)
        self.auth = AuthService(db)
        self.arbitros = ArbitroService(db)
        self.respaldos = RespaldoService(db, rutas)
        self.ligas = LigaService(db)
        self.jornadas = JornadaService(db)
        self.disponibilidad = DisponibilidadService(db)
        self.asignaciones = AsignacionService(db, self.config)
        self.rol = RolService(db, self.jornadas, self.asignaciones)
        self.pagos = PagoService(db, self.ligas)
        self.cedulas = CedulaService(db, rutas)
        self.reportes = ReporteService(self.pagos, self.cedulas)
        self.usuario: Usuario | None = None
        # Última liga/jornada vista, para que al cambiar de sección no se pierda la selección
        self.seleccion: dict = {"liga_id": None, "jornada_id": None}
        # Servicios de Flet: deben crearse dentro de main() para registrarse en la página
        self.selector_archivos = ft.FilePicker()
        self.portapapeles = ft.Clipboard()

    @property
    def es_admin(self) -> bool:
        return bool(self.usuario and self.usuario.es_admin)

    # --- Pantallas -------------------------------------------------------

    def iniciar(self) -> None:
        self._configurar_ventana()
        if self.auth.hay_usuarios():
            self.ir_a_login()
        else:
            self.ir_a_configuracion_inicial()

    def ir_a_login(self, mensaje: str | None = None) -> None:
        from arbitros.ui.vistas.acceso import pantalla_login

        self.usuario = None
        self.seleccion = {"liga_id": None, "jornada_id": None}
        self._mostrar(pantalla_login(self, mensaje))

    def ir_a_configuracion_inicial(self) -> None:
        from arbitros.ui.vistas.acceso import pantalla_configuracion_inicial

        self._mostrar(pantalla_configuracion_inicial(self))

    def ir_a_recuperar(self) -> None:
        from arbitros.ui.vistas.acceso import pantalla_recuperar

        self._mostrar(pantalla_recuperar(self))

    def entrar(self, usuario: Usuario) -> None:
        from arbitros.ui.shell import Shell

        self.usuario = usuario
        self._mostrar(Shell(self).construir())

    # --- Acciones globales ----------------------------------------------

    def alternar_tema(self) -> None:
        oscuro = self.page.theme_mode != ft.ThemeMode.DARK
        self.page.theme_mode = ft.ThemeMode.DARK if oscuro else ft.ThemeMode.LIGHT
        self.config.guardar(CLAVE_TEMA, "oscuro" if oscuro else "claro")
        self.page.update()

    def restaurar_respaldo(self, archivo: Path) -> Path:
        """Restaura y vuelve al login (los usuarios pueden haber cambiado)."""
        previo = self.respaldos.restaurar(archivo)
        migrar(self.db)
        log.info("Respaldo restaurado desde %s (previo: %s)", archivo, previo)
        self.ir_a_login("Datos restaurados. Inicia sesión de nuevo.")
        return previo

    # --- Actualizaciones --------------------------------------------------

    def buscar_actualizaciones(self, manual: bool = False) -> None:
        """Consulta en segundo plano si hay versión nueva. Automático solo en la app instalada."""
        if not manual and not es_instalada():
            return
        self.page.run_thread(self._buscar_actualizaciones, manual)

    def _buscar_actualizaciones(self, manual: bool) -> None:
        from arbitros.ui.comunes import avisar

        try:
            info = Actualizador(REPO_ACTUALIZACIONES, __version__).buscar()
        except ErrorActualizacion as e:
            log.info("Sin consulta de actualizaciones: %s", e)
            if manual:
                avisar(self.page, "No se pudo consultar si hay actualizaciones (¿hay internet?).", error=True)
            return
        if info is None:
            if manual:
                avisar(self.page, f"Ya tienes la versión más reciente ({__version__}).")
            return
        self._dialogo_actualizacion(info)

    def _dialogo_actualizacion(self, info: InfoVersion) -> None:
        import flet as ft

        from arbitros.ui.comunes import ANCHO_DIALOGO

        barra = ft.ProgressBar(value=0, visible=False, color=ft.Colors.PRIMARY)
        estado = ft.Text("", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
        boton_luego = ft.TextButton("Más tarde", on_click=lambda _: self.page.pop_dialog())
        boton_ok = ft.FilledButton("Actualizar ahora", icon=ft.Icons.SYSTEM_UPDATE)
        instalable = es_instalada()

        def progreso(fraccion: float) -> None:
            barra.value = fraccion
            estado.value = f"Descargando… {fraccion:.0%}"
            self.page.update()

        def actualizar() -> None:
            barra.visible = True
            boton_ok.disabled = boton_luego.disabled = True
            self.page.update()
            try:
                carpeta = Path(tempfile.gettempdir()) / "Arbitros-actualizacion"
                instalador = Actualizador(REPO_ACTUALIZACIONES, __version__).descargar(info, carpeta, progreso)
                estado.value = "Respaldando tus datos…"
                self.page.update()
                self.respaldos.crear(prefijo=PREFIJO_ACTUALIZACION)
            except ErrorActualizacion as e:
                estado.value = str(e)
                boton_ok.disabled = boton_luego.disabled = False
                barra.visible = False
                self.page.update()
                return
            estado.value = "Instalando… la app se cerrará y se volverá a abrir sola."
            self.page.update()
            log.info("Instalando versión %s desde %s", info.version, instalador)
            Actualizador.instalar(instalador)
            self.page.run_task(self._cerrar_para_actualizar)

        boton_ok.on_click = lambda _: self.page.run_thread(actualizar)
        contenido = [
            ft.Text(f"Tienes la versión {__version__}. La actualización conserva todos tus datos "
                    "(antes se hace un respaldo)."),
        ]
        if info.notas:
            contenido.append(ft.Container(
                ft.Markdown(info.notas, selectable=True), bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=8, padding=12, height=200))
        if not instalable:
            contenido.append(ft.Text("Estás usando la versión de desarrollo: instala con el .exe para "
                                     "actualizar automáticamente.", color=ft.Colors.ON_SURFACE_VARIANT, size=12))
            boton_ok.visible = False
        contenido += [barra, estado]
        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            icon=ft.Icon(ft.Icons.SYSTEM_UPDATE, color=ft.Colors.PRIMARY),
            title=ft.Text(f"Nueva versión {info.version} disponible"),
            content=ft.Column(contenido, tight=True, spacing=12, width=ANCHO_DIALOGO + 60),
            actions=[boton_luego, boton_ok],
        ))

    async def _cerrar_para_actualizar(self) -> None:
        # Se le da un momento al instalador para arrancar; él mismo cierra lo que quede abierto
        await asyncio.sleep(1.5)
        try:
            await self.page.window.destroy()
        finally:
            os._exit(0)

    # --- Internos --------------------------------------------------------

    def _configurar_ventana(self) -> None:
        p = self.page
        p.title = f"{APP_NOMBRE} · {ORGANIZACION}"
        p.window.width = 1240
        p.window.height = 800
        p.window.min_width = 960
        p.window.min_height = 620
        p.padding = 0
        espanol = ft.Locale("es", "MX")
        p.locale_configuration = ft.LocaleConfiguration(supported_locales=[espanol], current_locale=espanol)
        p.theme = tema.tema(oscuro=False)
        p.dark_theme = tema.tema(oscuro=True)
        if tema.RUTA_ICONO.exists():
            p.window.icon = str(tema.RUTA_ICONO)
        oscuro = self.config.obtener(CLAVE_TEMA) == "oscuro"
        p.theme_mode = ft.ThemeMode.DARK if oscuro else ft.ThemeMode.LIGHT

    def _mostrar(self, control: ft.Control) -> None:
        self.page.controls.clear()
        self.page.add(control)
