import flet as ft

from arbitros.ui import filtros

from arbitros.db.models import ROL_ADMIN, ROL_CONSULTA, Usuario
from arbitros.services.errores import ErrorValidacion
from arbitros.ui.comunes import ANCHO_DIALOGO, avisar, campo_password, encabezado, etiqueta, mostrar_errores

NOMBRES_ROL = {ROL_ADMIN: "Administrador", ROL_CONSULTA: "Consulta (solo ver)"}


def construir(app, shell) -> ft.Control:
    return VistaUsuarios(app).construir()


class VistaUsuarios:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.tabla_contenedor = ft.Column()

    def construir(self) -> ft.Control:
        self.refrescar(actualizar=False)
        return ft.Column(
            [
                encabezado(
                    "Usuarios",
                    "Quién puede entrar a la app. Los usuarios de consulta solo pueden ver la información.",
                    [ft.FilledButton("Nuevo usuario", icon=ft.Icons.PERSON_ADD, on_click=lambda _: self._nuevo())],
                ),
                self.tabla_contenedor,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def refrescar(self, actualizar: bool = True) -> None:
        filas = []
        for u in self.app.auth.listar_usuarios():
            yo = u.id == self.app.usuario.id
            acciones = [
                ft.IconButton(ft.Icons.LOCK_RESET, tooltip="Asignar contraseña nueva", on_click=lambda _, u=u: self._restablecer(u))
            ]
            if not yo:
                acciones.append(
                    ft.IconButton(
                        ft.Icons.PERSON_OFF if u.activo else ft.Icons.PERSON,
                        tooltip="Desactivar" if u.activo else "Reactivar",
                        on_click=lambda _, u=u: self._alternar_activo(u),
                    )
                )
            filas.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(u.nombre + (" (tú)" if yo else ""), weight=ft.FontWeight.W_500)),
                        ft.DataCell(ft.Text(u.usuario)),
                        ft.DataCell(ft.Text(NOMBRES_ROL.get(u.rol, u.rol))),
                        ft.DataCell(etiqueta("Activo" if u.activo else "Inactivo", u.activo)),
                        ft.DataCell(ft.Row(acciones, spacing=0)),
                    ]
                )
            )
        self.tabla_contenedor.controls = [
            ft.DataTable(
                columns=[
                    ft.DataColumn(ft.Text("Nombre")),
                    ft.DataColumn(ft.Text("Usuario")),
                    ft.DataColumn(ft.Text("Rol")),
                    ft.DataColumn(ft.Text("Estado")),
                    ft.DataColumn(ft.Text("Acciones")),
                ],
                rows=filas,
                heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
                border_radius=8,
            )
        ]
        if actualizar:
            self.page.update()

    def _alternar_activo(self, u: Usuario) -> None:
        try:
            self.app.auth.cambiar_activo(u.id, not u.activo)
        except ErrorValidacion as e:
            avisar(self.page, e.mensaje, error=True)
            return
        self.refrescar()

    def _nuevo(self) -> None:
        nombre = ft.TextField(label="Nombre *", autofocus=True, input_filter=filtros.NOMBRE_PERSONA, max_length=120, counter="")
        usuario = ft.TextField(label="Usuario *", helper="Sin espacios", input_filter=filtros.USUARIO, max_length=50, counter="")
        rol = ft.Dropdown(
            label="Rol",
            value=ROL_CONSULTA,
            options=[ft.DropdownOption(key=k, text=v) for k, v in NOMBRES_ROL.items()],
            width=ANCHO_DIALOGO,
        )
        password = campo_password("Contraseña *", helper="Mínimo 6 caracteres")
        confirmar_ = campo_password("Repite la contraseña *")
        campos = {"nombre": nombre, "usuario": usuario, "password": password, "confirmar": confirmar_}

        def guardar(_):
            if (password.value or "") != (confirmar_.value or ""):
                mostrar_errores(campos, {"confirmar": "Las contraseñas no coinciden"})
                self.page.update()
                return
            try:
                self.app.auth.crear_usuario(usuario.value or "", nombre.value or "", password.value or "", rol.value)
            except ErrorValidacion as e:
                mostrar_errores(campos, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, "Usuario creado.")
            self.refrescar()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Nuevo usuario"),
                content=ft.Column([nombre, usuario, rol, password, confirmar_], tight=True, spacing=14, width=ANCHO_DIALOGO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Crear", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )

    def _restablecer(self, u: Usuario) -> None:
        password = campo_password("Contraseña nueva *", helper="Mínimo 6 caracteres", autofocus=True)
        confirmar_ = campo_password("Repite la contraseña *")
        campos = {"password": password, "confirmar": confirmar_}

        def guardar(_):
            if (password.value or "") != (confirmar_.value or ""):
                mostrar_errores(campos, {"confirmar": "Las contraseñas no coinciden"})
                self.page.update()
                return
            try:
                self.app.auth.restablecer_password(u.id, password.value or "")
            except ErrorValidacion as e:
                mostrar_errores(campos, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, f"Contraseña de {u.nombre} actualizada.")

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Contraseña nueva para {u.nombre}"),
                content=ft.Column([password, confirmar_], tight=True, spacing=14, width=ANCHO_DIALOGO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )


def dialogo_cambiar_mi_password(app) -> None:
    page = app.page
    actual = campo_password("Contraseña actual", autofocus=True)
    nueva = campo_password("Contraseña nueva", helper="Mínimo 6 caracteres")
    confirmar_ = campo_password("Repite la contraseña nueva")
    campos = {"actual": actual, "password": nueva, "confirmar": confirmar_}

    def guardar(_):
        if (nueva.value or "") != (confirmar_.value or ""):
            mostrar_errores(campos, {"confirmar": "Las contraseñas no coinciden"})
            page.update()
            return
        try:
            app.auth.cambiar_password(app.usuario.id, actual.value or "", nueva.value or "")
        except ErrorValidacion as e:
            mostrar_errores(campos, e.campos)
            page.update()
            return
        page.pop_dialog()
        avisar(page, "Tu contraseña se cambió.")

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text("Cambiar mi contraseña"),
            content=ft.Column([actual, nueva, confirmar_], tight=True, spacing=14, width=ANCHO_DIALOGO),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
            ],
        )
    )
