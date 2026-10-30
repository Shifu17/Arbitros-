"""Identidad visual del colegio activo (colores y logo, ver `colegios.py`).

Los colores de *estado* (bien / aviso / falta) son fijos y distintos del rojo de la
marca, para que un "Falta árbitro" nunca se confunda con un botón principal.
"""

from functools import cache
from pathlib import Path

import flet as ft

from arbitros import colegios
from arbitros.colegios import Colegio

NEGRO = "#121212"
TEXTO_MENU = "#E6E6E6"

EXITO_FONDO, EXITO_TEXTO, EXITO_ICONO = "#D6F0DA", "#1B5E20", "#2E7D32"
AVISO_FONDO, AVISO_TEXTO, AVISO_ICONO = "#FFF0C2", "#5C4300", "#B07D00"
PELIGRO_FONDO, PELIGRO_TEXTO = "#FBD5D5", "#8E1014"


_SUPERFICIES_CLARAS = dict(
    surface="#FFFFFF", on_surface="#1C1C1C", surface_tint="#00000000",
    surface_container_lowest="#FFFFFF", surface_container_low="#F7F7F7", surface_container="#F1F1F1",
    surface_container_high="#EBEBEB", surface_container_highest="#E3E3E3",
)
_SUPERFICIES_OSCURAS = dict(
    surface="#141414", on_surface="#EDEDED", surface_tint="#00000000",
    surface_container_lowest="#0E0E0E", surface_container_low="#1A1A1A", surface_container="#1F1F1F",
    surface_container_high="#262626", surface_container_highest="#303030",
)


def marca() -> Colegio:
    return colegios.activo()


@cache
def _logo_bytes(ruta: Path) -> bytes:
    return ruta.read_bytes()


def logo(tamano: int, colegio: Colegio | None = None) -> ft.Image:
    return ft.Image(src=_logo_bytes((colegio or marca()).ruta_logo), width=tamano, height=tamano)


def franja(alto: int, ancho: int | None = None, colegio: Colegio | None = None, **kwargs) -> ft.Container:
    """Línea de dos colores (acento | primario) que acompaña al logo."""
    c = colegio or marca()
    return ft.Container(height=alto, width=ancho, gradient=ft.LinearGradient(
        colors=[c.acento, c.acento, c.primario, c.primario], stops=[0, 0.5, 0.5, 1]), **kwargs)


def tema(oscuro: bool) -> ft.Theme:
    c = marca()
    return ft.Theme(
        color_scheme_seed=c.primario,
        color_scheme=ft.ColorScheme(
            primary=c.primario_oscuro if oscuro else c.primario,
            on_primary="#FFFFFF",
            secondary=c.acento,
            on_secondary=NEGRO,
            secondary_container="#5A4700" if oscuro else "#FFE9A8",
            on_secondary_container="#FFE9A8" if oscuro else "#3A2E00",
            # Fondos neutros (sin el tinte rojizo que generaría la semilla)
            **(_SUPERFICIES_OSCURAS if oscuro else _SUPERFICIES_CLARAS),
        ),
        scaffold_bgcolor="#141414" if oscuro else "#FAFAFA",
        navigation_rail_theme=ft.NavigationRailTheme(
            bgcolor=c.fondo,
            indicator_color=c.acento,
            selected_label_text_style=ft.TextStyle(color=c.acento, weight=ft.FontWeight.W_600),
            unselected_label_text_style=ft.TextStyle(color=TEXTO_MENU),
        ),
    )
