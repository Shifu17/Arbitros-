import flet as ft

from arbitros.ui.comunes import encabezado, estado_vacio


def proximamente(seccion) -> ft.Control:
    return ft.Column(
        [
            encabezado(seccion.titulo),
            estado_vacio(
                ft.Icons.CONSTRUCTION,
                f"Este módulo llega en la fase {seccion.fase}",
                seccion.descripcion,
            ),
        ],
        expand=True,
    )
