"""Orquestador de pantallas: configuración inicial → login → aplicación.

`App` es el único objeto que las vistas reciben: da acceso a la página, los
servicios y el usuario con sesión iniciada.
"""

import logging
from pathlib import Path

import flet as ft

from arbitros.config import APP_NOMBRE, ORGANIZACION, Rutas
from arbitros.db.database import Database
from arbitros.db.migrar import migrar
from arbitros.db.models import Usuario
from arbitros.services.arbitros import ArbitroService
from arbitros.services.auth import AuthService
from arbitros.services.asignaciones import AsignacionService
from arbitros.services.cedulas import CedulaService
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.disponibilidad import DisponibilidadService
from arbitros.services.jornadas import JornadaService
from arbitros.services.ligas import LigaService
from arbitros.services.pagos import PagoService
from arbitros.services.reportes import ReporteService
from arbitros.services.respaldos import RespaldoService
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
