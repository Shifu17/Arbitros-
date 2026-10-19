import flet as ft

from arbitros import __version__
from arbitros.ui.comunes import encabezado, fecha_legible, hace_cuanto, tarjeta


def _dato(icono, titulo: str, valor: str, detalle: str = "") -> ft.Control:
    return tarjeta(
        ft.Row(
            [
                ft.Icon(icono, size=36, color=ft.Colors.PRIMARY),
                ft.Column(
                    [
                        ft.Text(titulo, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(valor, size=24, weight=ft.FontWeight.BOLD),
                        ft.Text(detalle, size=12, color=ft.Colors.ON_SURFACE_VARIANT, visible=bool(detalle)),
                    ],
                    spacing=2,
                    expand=True,
                ),
            ],
            spacing=16,
        ),
        expand=True,
    )


def _paso(numero: int, texto: str, hecho: bool, accion: ft.Control | None = None) -> ft.Control:
    return ft.Row(
        [
            ft.Icon(
                ft.Icons.CHECK_CIRCLE if hecho else ft.Icons.RADIO_BUTTON_UNCHECKED,
                color=ft.Colors.PRIMARY if hecho else ft.Colors.OUTLINE,
            ),
            ft.Text(f"{numero}. {texto}", expand=True),
            accion or ft.Container(),
        ]
    )


def construir(app, shell) -> ft.Control:
    activos = app.arbitros.contar_activos()
    ligas = app.ligas.listar()
    hay_partidos = any(j.partidos for r in ligas for j in app.jornadas.listar(r.liga.id))
    ultimo = app.respaldos.ultimo()
    respaldo_valor = hace_cuanto(ultimo.fecha).capitalize() if ultimo else "Ninguno"
    respaldo_detalle = fecha_legible(ultimo.fecha) if ultimo else "Crea uno en Respaldos"

    pasos = [
        _paso(
            1,
            "Registra a tus árbitros",
            activos > 0,
            ft.TextButton("Ir a Árbitros", on_click=lambda _: shell.ir_a("arbitros")),
        ),
        _paso(
            2,
            "Da de alta tus ligas o torneos, con sus equipos y campos",
            any(r.equipos and r.campos for r in ligas),
            ft.TextButton("Ir a Ligas", on_click=lambda _: shell.ir_a("ligas")),
        ),
        _paso(
            3,
            "Carga la jornada con sus partidos",
            hay_partidos,
            ft.TextButton("Ir a Jornadas", on_click=lambda _: shell.ir_a("jornadas")),
        ),
        _paso(
            4,
            "Marca la disponibilidad y asigna árbitros a cada partido",
            app.asignaciones.hay_asignaciones(),
            ft.TextButton("Ir a Disponibilidad", on_click=lambda _: shell.ir_a("disponibilidad")),
        ),
        _paso(
            5,
            "Genera el rol y compártelo por WhatsApp",
            False,
            ft.TextButton("Ir al Rol", on_click=lambda _: shell.ir_a("rol")),
        ),
        _paso(6, "Registra pagos y cédulas (fase 5)", False),
    ]

    return ft.Column(
        [
            encabezado(f"Hola, {app.usuario.nombre.split()[0]}", "Resumen de tu organización arbitral."),
            ft.Row(
                [
                    _dato(ft.Icons.PEOPLE, "Árbitros activos", str(activos)),
                    _dato(ft.Icons.EMOJI_EVENTS, "Ligas y torneos activos", str(len(ligas))),
                    _dato(ft.Icons.BACKUP, "Último respaldo", respaldo_valor, respaldo_detalle),
                    _dato(ft.Icons.INFO_OUTLINE, "Versión", __version__),
                ],
                spacing=16,
            ),
            tarjeta(
                ft.Column(
                    [ft.Text("Primeros pasos", size=18, weight=ft.FontWeight.W_500), *pasos],
                    spacing=10,
                )
            ),
        ],
        spacing=20,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
