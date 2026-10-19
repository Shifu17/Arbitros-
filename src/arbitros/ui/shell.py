"""Ventana principal: menú lateral + área de contenido.

Para agregar un módulo nuevo, añade una `Seccion` a SECCIONES con su función
`construir(app, shell) -> ft.Control`. Las que tienen `construir=None` se
muestran como "Próximamente" con la fase en la que llegarán.
"""

from dataclasses import dataclass
from typing import Callable

import flet as ft

from arbitros.ui.vistas import arbitros as vista_arbitros
from arbitros.ui.vistas import disponibilidad as vista_disponibilidad
from arbitros.ui.vistas import inicio as vista_inicio
from arbitros.ui.vistas import jornadas as vista_jornadas
from arbitros.ui.vistas import ligas as vista_ligas
from arbitros.ui.vistas import respaldos as vista_respaldos
from arbitros.ui.vistas import rol as vista_rol
from arbitros.ui.vistas import usuarios as vista_usuarios
from arbitros.ui.vistas.proximamente import proximamente


@dataclass(frozen=True)
class Seccion:
    clave: str
    titulo: str
    icono: str
    icono_activo: str
    construir: Callable | None = None
    fase: int | None = None
    solo_admin: bool = False
    descripcion: str = ""


SECCIONES = [
    Seccion("inicio", "Inicio", ft.Icons.HOME_OUTLINED, ft.Icons.HOME, vista_inicio.construir),
    Seccion("arbitros", "Árbitros", ft.Icons.PEOPLE_OUTLINE, ft.Icons.PEOPLE, vista_arbitros.construir),
    Seccion("ligas", "Ligas y torneos", ft.Icons.EMOJI_EVENTS_OUTLINED, ft.Icons.EMOJI_EVENTS, vista_ligas.construir),
    Seccion(
        "jornadas", "Jornadas y partidos", ft.Icons.CALENDAR_MONTH_OUTLINED, ft.Icons.CALENDAR_MONTH,
        vista_jornadas.construir,
    ),
    Seccion(
        "disponibilidad", "Disponibilidad", ft.Icons.EVENT_AVAILABLE_OUTLINED, ft.Icons.EVENT_AVAILABLE,
        vista_disponibilidad.construir,
    ),
    Seccion("rol", "Rol para WhatsApp", ft.Icons.SEND_OUTLINED, ft.Icons.SEND, vista_rol.construir),
    Seccion(
        "pagos", "Pagos", ft.Icons.PAYMENTS_OUTLINED, ft.Icons.PAYMENTS, fase=5,
        descripcion="Tarifa, pagado en campo y saldo pendiente de cada árbitro.",
    ),
    Seccion(
        "cedulas", "Cédulas", ft.Icons.DESCRIPTION_OUTLINED, ft.Icons.DESCRIPTION, fase=5,
        descripcion="Sube la cédula (PDF o foto) de cada partido y revisa cuáles faltan.",
    ),
    Seccion(
        "reportes", "Reportes", ft.Icons.BAR_CHART_OUTLINED, ft.Icons.BAR_CHART, fase=5,
        descripcion="Partidos arbitrados, pagos pendientes y exportación a Excel.",
    ),
    Seccion("respaldos", "Respaldos", ft.Icons.BACKUP_OUTLINED, ft.Icons.BACKUP, vista_respaldos.construir),
    Seccion(
        "usuarios", "Usuarios", ft.Icons.MANAGE_ACCOUNTS_OUTLINED, ft.Icons.MANAGE_ACCOUNTS,
        vista_usuarios.construir, solo_admin=True,
    ),
]


class Shell:
    def __init__(self, app):
        self.app = app
        self.secciones = [s for s in SECCIONES if app.es_admin or not s.solo_admin]
        self.contenido = ft.Container(expand=True, padding=ft.Padding.symmetric(horizontal=32, vertical=24))
        self.menu = ft.NavigationRail(
            selected_index=0,
            extended=True,
            min_extended_width=220,
            scrollable=True,
            leading=self._cabecera_menu(),
            trailing=self._pie_menu(),
            destinations=[
                ft.NavigationRailDestination(icon=s.icono, selected_icon=s.icono_activo, label=s.titulo)
                for s in self.secciones
            ],
            on_change=lambda e: self._mostrar(self.secciones[e.control.selected_index]),
        )

    def construir(self) -> ft.Control:
        self._mostrar(self.secciones[0], actualizar=False)
        return ft.Row([self.menu, ft.VerticalDivider(width=1), self.contenido], expand=True, spacing=0)

    def ir_a(self, clave: str) -> None:
        for i, s in enumerate(self.secciones):
            if s.clave == clave:
                self.menu.selected_index = i
                self._mostrar(s)
                return

    def _mostrar(self, seccion: Seccion, actualizar: bool = True) -> None:
        if seccion.construir:
            self.contenido.content = seccion.construir(self.app, self)
        else:
            self.contenido.content = proximamente(seccion)
        if actualizar:
            self.app.page.update()

    def _cabecera_menu(self) -> ft.Control:
        u = self.app.usuario
        return ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            ft.Icon(ft.Icons.SPORTS_SOCCER, color=ft.Colors.PRIMARY, size=30),
                            ft.Text("Árbitros", size=22, weight=ft.FontWeight.BOLD),
                        ]
                    ),
                    ft.Text(
                        f"{u.nombre} · {'Administrador' if u.es_admin else 'Consulta'}",
                        size=12,
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                ],
                spacing=4,
            ),
            padding=ft.Padding.only(left=16, top=8, bottom=16),
            width=200,
        )

    def _pie_menu(self) -> ft.Control:
        from arbitros.ui.vistas.usuarios import dialogo_cambiar_mi_password

        oscuro = self.app.page.theme_mode == ft.ThemeMode.DARK
        boton_tema = ft.IconButton(
            ft.Icons.LIGHT_MODE if oscuro else ft.Icons.DARK_MODE,
            tooltip="Cambiar tema claro/oscuro",
        )

        def tema(_):
            self.app.alternar_tema()
            boton_tema.icon = (
                ft.Icons.LIGHT_MODE if self.app.page.theme_mode == ft.ThemeMode.DARK else ft.Icons.DARK_MODE
            )
            self.app.page.update()

        boton_tema.on_click = tema
        return ft.Container(
            ft.Row(
                [
                    boton_tema,
                    ft.IconButton(
                        ft.Icons.KEY, tooltip="Cambiar mi contraseña",
                        on_click=lambda _: dialogo_cambiar_mi_password(self.app),
                    ),
                    ft.IconButton(ft.Icons.LOGOUT, tooltip="Cerrar sesión", on_click=lambda _: self.app.ir_a_login()),
                ]
            ),
            padding=ft.Padding.only(top=16, bottom=8),
        )
