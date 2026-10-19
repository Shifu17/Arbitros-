"""Piezas de interfaz reutilizadas por todas las pantallas."""

import inspect
from datetime import datetime

import flet as ft

ANCHO_DIALOGO = 460


def avisar(page: ft.Page, mensaje: str, error: bool = False) -> None:
    page.show_dialog(
        ft.SnackBar(
            ft.Text(mensaje, color=ft.Colors.ON_ERROR if error else None),
            bgcolor=ft.Colors.ERROR if error else None,
            show_close_icon=True,
        )
    )


def confirmar(page: ft.Page, titulo: str, mensaje: str, al_confirmar, texto_confirmar: str = "Sí, continuar") -> None:
    async def aceptar(_):
        page.pop_dialog()
        resultado = al_confirmar()
        if inspect.isawaitable(resultado):
            await resultado

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje, width=ANCHO_DIALOGO),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(texto_confirmar, on_click=aceptar),
            ],
        )
    )


def mostrar_errores(campos: dict[str, ft.TextField], errores: dict[str, str]) -> None:
    """Marca en rojo los campos con error y limpia los demás."""
    for nombre, campo in campos.items():
        campo.error = errores.get(nombre)


def encabezado(titulo: str, subtitulo: str | None = None, acciones: list[ft.Control] | None = None) -> ft.Control:
    textos = [ft.Text(titulo, size=26, weight=ft.FontWeight.BOLD)]
    if subtitulo:
        textos.append(ft.Text(subtitulo, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Row(
        [ft.Column(textos, spacing=2, expand=True), ft.Row(acciones or [], spacing=8)],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def tarjeta(contenido: ft.Control, expand: bool | int = False, width: float | None = None) -> ft.Card:
    return ft.Card(content=ft.Container(contenido, padding=20), expand=expand, width=width)


def estado_vacio(icono, titulo: str, detalle: str = "") -> ft.Control:
    return ft.Container(
        ft.Column(
            [
                ft.Icon(icono, size=56, color=ft.Colors.OUTLINE_VARIANT),
                ft.Text(titulo, size=18, weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
                ft.Text(detalle, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
        alignment=ft.Alignment.CENTER,
        padding=40,
    )


def etiqueta(texto: str, positiva: bool) -> ft.Control:
    """Pastilla de estado (Activo / Inactivo)."""
    return ft.Container(
        ft.Text(
            texto,
            size=12,
            weight=ft.FontWeight.W_500,
            color=ft.Colors.ON_PRIMARY_CONTAINER if positiva else ft.Colors.ON_SURFACE_VARIANT,
        ),
        bgcolor=ft.Colors.PRIMARY_CONTAINER if positiva else ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )


def campo_password(etiqueta_: str, **kwargs) -> ft.TextField:
    return ft.TextField(label=etiqueta_, password=True, can_reveal_password=True, **kwargs)


def fecha_legible(fecha: datetime) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{fecha.day} {meses[fecha.month - 1]} {fecha.year}, {fecha:%H:%M}"


def hace_cuanto(fecha: datetime, ahora: datetime | None = None) -> str:
    dias = ((ahora or datetime.now()).date() - fecha.date()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {dias} días"
