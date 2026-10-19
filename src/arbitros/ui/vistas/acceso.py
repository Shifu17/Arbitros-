"""Pantallas previas a la sesión: configuración inicial, login y recuperación."""

import flet as ft

from arbitros import __version__
from arbitros.config import APP_NOMBRE, ORGANIZACION
from arbitros.ui import tema
from arbitros.services.errores import ErrorAutenticacion, ErrorValidacion
from arbitros.ui.comunes import ANCHO_DIALOGO, avisar, campo_password, mostrar_errores

ANCHO_TARJETA = 420


def _marco(titulo: str, subtitulo: str, controles: list[ft.Control]) -> ft.Control:
    """Tarjeta centrada con el logo de la app."""
    cabecera = [
        ft.Text(titulo, size=22, weight=ft.FontWeight.BOLD),
        ft.Text(subtitulo, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
    ]
    tarjeta = ft.Card(
        ft.Container(
            ft.Column(
                [*cabecera, ft.Container(height=8), *controles],
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                spacing=12,
                tight=True,
            ),
            padding=32,
            width=ANCHO_TARJETA,
        ),
        elevation=4,
    )
    marca = [
        tema.logo(120),
        ft.Text(ORGANIZACION.upper(), size=20, weight=ft.FontWeight.BOLD, color="#FFFFFF",
                text_align=ft.TextAlign.CENTER),
        ft.Container(height=4, width=160, gradient=ft.LinearGradient(
            colors=[tema.AMARILLO, tema.AMARILLO, tema.ROJO, tema.ROJO], stops=[0, 0.5, 0.5, 1])),
        ft.Container(height=8),
    ]
    return ft.Container(
        ft.Column(
            [*marca, tarjeta,
             ft.Text(f"{APP_NOMBRE} · versión {__version__}", size=12, color=tema.TEXTO_MENU)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
            scroll=ft.ScrollMode.AUTO,
        ),
        alignment=ft.Alignment.CENTER,
        expand=True,
        padding=24,
        bgcolor=tema.NEGRO,
    )


def _mensaje_error() -> ft.Text:
    return ft.Text("", color=ft.Colors.ERROR, visible=False, text_align=ft.TextAlign.CENTER)


def _mostrar_error(texto: ft.Text, mensaje: str | None) -> None:
    texto.value = mensaje or ""
    texto.visible = bool(mensaje)


def pantalla_login(app, mensaje: str | None = None) -> ft.Control:
    usuario = ft.TextField(label="Usuario", prefix_icon=ft.Icons.PERSON, autofocus=True)
    password = campo_password("Contraseña", prefix_icon=ft.Icons.LOCK)
    error = _mensaje_error()

    def entrar(_):
        try:
            u = app.auth.autenticar(usuario.value or "", password.value or "")
        except ErrorAutenticacion as e:
            _mostrar_error(error, str(e))
            password.value = ""
            app.page.update()
            return
        app.entrar(u)

    usuario.on_submit = entrar
    password.on_submit = entrar
    controles = [
        usuario,
        password,
        error,
        ft.FilledButton("Entrar", icon=ft.Icons.LOGIN, on_click=entrar, width=ANCHO_TARJETA),
        ft.TextButton("¿Olvidaste tu contraseña?", on_click=lambda _: app.ir_a_recuperar()),
    ]
    if mensaje:
        controles.insert(0, ft.Text(mensaje, color=ft.Colors.PRIMARY, text_align=ft.TextAlign.CENTER))
    return _marco("Iniciar sesión", "Escribe tu usuario y contraseña.", controles)


def pantalla_configuracion_inicial(app) -> ft.Control:
    nombre = ft.TextField(label="Tu nombre", prefix_icon=ft.Icons.BADGE, autofocus=True)
    usuario = ft.TextField(label="Usuario para entrar", prefix_icon=ft.Icons.PERSON, helper="Sin espacios, ej.: coordinador")
    password = campo_password("Contraseña", prefix_icon=ft.Icons.LOCK, helper="Mínimo 6 caracteres")
    confirmar = campo_password("Repite la contraseña", prefix_icon=ft.Icons.LOCK)
    error = _mensaje_error()
    campos = {"nombre": nombre, "usuario": usuario, "password": password, "confirmar": confirmar}

    def crear(_):
        _mostrar_error(error, None)
        if (password.value or "") != (confirmar.value or ""):
            mostrar_errores(campos, {"confirmar": "Las contraseñas no coinciden"})
            app.page.update()
            return
        try:
            clave = app.auth.crear_admin_inicial(usuario.value or "", nombre.value or "", password.value or "")
        except ErrorValidacion as e:
            mostrar_errores(campos, e.campos)
            _mostrar_error(error, None if e.campos else e.mensaje)
            app.page.update()
            return
        u = app.auth.autenticar(usuario.value or "", password.value or "")
        mostrar_clave_recuperacion(app, clave, lambda: app.entrar(u))

    confirmar.on_submit = crear
    return _marco(
        "¡Bienvenido!",
        "Crea tu usuario administrador para empezar. Con él podrás registrar árbitros, ligas y pagos.",
        [
            nombre,
            usuario,
            password,
            confirmar,
            error,
            ft.FilledButton("Crear usuario y entrar", icon=ft.Icons.CHECK, on_click=crear, width=ANCHO_TARJETA),
        ],
    )


def pantalla_recuperar(app) -> ft.Control:
    clave = ft.TextField(
        label="Clave de recuperación",
        prefix_icon=ft.Icons.KEY,
        hint_text="XXXX-XXXX-XXXX-XXXX",
        capitalization=ft.TextCapitalization.CHARACTERS,
        autofocus=True,
    )
    usuario = ft.TextField(label="Usuario administrador", prefix_icon=ft.Icons.PERSON)
    password = campo_password("Contraseña nueva", prefix_icon=ft.Icons.LOCK, helper="Mínimo 6 caracteres")
    confirmar = campo_password("Repite la contraseña nueva", prefix_icon=ft.Icons.LOCK)
    error = _mensaje_error()
    campos = {"password": password, "confirmar": confirmar}

    def recuperar(_):
        _mostrar_error(error, None)
        if (password.value or "") != (confirmar.value or ""):
            mostrar_errores(campos, {"confirmar": "Las contraseñas no coinciden"})
            app.page.update()
            return
        try:
            nueva_clave = app.auth.recuperar_con_clave(clave.value or "", usuario.value or "", password.value or "")
        except ErrorValidacion as e:
            mostrar_errores(campos, e.campos)
            _mostrar_error(error, None if e.campos else e.mensaje)
            app.page.update()
            return
        except ErrorAutenticacion as e:
            mostrar_errores(campos, {})
            _mostrar_error(error, str(e))
            app.page.update()
            return
        mostrar_clave_recuperacion(
            app,
            nueva_clave,
            lambda: app.ir_a_login("Contraseña cambiada. Ya puedes entrar."),
            aviso="Tu clave anterior ya no sirve. Esta es tu clave NUEVA.",
        )

    confirmar.on_submit = recuperar
    return _marco(
        "Recuperar acceso",
        "Usa la clave de recuperación que guardaste al instalar la app.",
        [
            clave,
            usuario,
            password,
            confirmar,
            error,
            ft.FilledButton("Cambiar contraseña", icon=ft.Icons.LOCK_RESET, on_click=recuperar, width=ANCHO_TARJETA),
            ft.TextButton("Volver al inicio de sesión", on_click=lambda _: app.ir_a_login()),
        ],
    )


def mostrar_clave_recuperacion(app, clave: str, al_continuar, aviso: str | None = None) -> None:
    """Diálogo que muestra la clave una sola vez; no deja continuar sin confirmar que se guardó."""
    page = app.page
    continuar = ft.FilledButton("Continuar", disabled=True)
    guardada = ft.Checkbox(label="Ya la anoté o guardé en un lugar seguro")

    def marcar(_):
        continuar.disabled = not guardada.value
        page.update()

    async def copiar(_):
        await app.portapapeles.set(clave)
        avisar(page, "Clave copiada al portapapeles.")

    def cerrar(_):
        page.pop_dialog()
        al_continuar()

    guardada.on_change = marcar
    continuar.on_click = cerrar
    textos = [
        ft.Text(
            "Si olvidas tu contraseña, esta clave es la ÚNICA forma de recuperar el acceso. "
            "Anótala en papel o guárdala en tu teléfono.",
        ),
        ft.Container(
            ft.Text(clave, size=26, weight=ft.FontWeight.BOLD, font_family="Consolas", selectable=True),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8,
            padding=16,
            alignment=ft.Alignment.CENTER,
        ),
        ft.OutlinedButton("Copiar clave", icon=ft.Icons.CONTENT_COPY, on_click=copiar),
        guardada,
    ]
    if aviso:
        textos.insert(0, ft.Text(aviso, weight=ft.FontWeight.BOLD, color=ft.Colors.ERROR))
    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            icon=ft.Icon(ft.Icons.KEY, color=ft.Colors.PRIMARY),
            title=ft.Text("Tu clave de recuperación"),
            content=ft.Column(textos, tight=True, spacing=14, width=ANCHO_DIALOGO),
            actions=[continuar],
        )
    )
