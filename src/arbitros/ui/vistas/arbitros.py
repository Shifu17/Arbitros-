import flet as ft

from arbitros.db.models import POSICIONES, Arbitro
from arbitros.services.arbitros import (
    FILTRO_ACTIVOS,
    FILTRO_INACTIVOS,
    FILTRO_TODOS,
    DatosArbitro,
    enlace_whatsapp,
    formatear_telefono,
)
from arbitros.services.dinero import formatear_monto
from arbitros.services.errores import ErrorValidacion
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    avisar,
    confirmar,
    estado_vacio,
    etiqueta,
    fecha_corta,
    mostrar_errores,
)
from arbitros.ui.vistas.pagos import etiqueta_pago


def construir(app, shell) -> ft.Control:
    return VistaArbitros(app).construir()


class VistaArbitros:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.filtro = FILTRO_ACTIVOS
        self.busqueda = ft.TextField(
            hint_text="Buscar por nombre, apodo, teléfono o categoría",
            prefix_icon=ft.Icons.SEARCH,
            on_change=lambda _: self.refrescar(),
            expand=True,
        )
        self.selector_filtro = ft.SegmentedButton(
            selected=[FILTRO_ACTIVOS],
            segments=[
                ft.Segment(value=FILTRO_ACTIVOS, label=ft.Text("Activos")),
                ft.Segment(value=FILTRO_INACTIVOS, label=ft.Text("Inactivos")),
                ft.Segment(value=FILTRO_TODOS, label=ft.Text("Todos")),
            ],
            on_change=self._cambiar_filtro,
        )
        self.subtitulo = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
        self.resultados = ft.Column(expand=True, scroll=ft.ScrollMode.AUTO)

    def construir(self) -> ft.Control:
        acciones = []
        if self.app.es_admin:
            acciones.append(
                ft.FilledButton("Nuevo árbitro", icon=ft.Icons.PERSON_ADD, on_click=lambda _: self.abrir_formulario())
            )
        self.refrescar(actualizar=False)
        return ft.Column(
            [
                ft.Row(
                    [
                        ft.Column(
                            [ft.Text("Árbitros", size=26, weight=ft.FontWeight.BOLD), self.subtitulo],
                            spacing=2,
                            expand=True,
                        ),
                        *acciones,
                    ]
                ),
                ft.Row([self.busqueda, self.selector_filtro], spacing=16),
                self.resultados,
            ],
            spacing=16,
            expand=True,
        )

    def refrescar(self, actualizar: bool = True) -> None:
        lista = self.app.arbitros.listar(self.busqueda.value or "", self.filtro)
        activos = self.app.arbitros.contar_activos()
        self.subtitulo.value = f"{activos} árbitro{'s' if activos != 1 else ''} activo{'s' if activos != 1 else ''}"
        if lista:
            self.resultados.controls = [self._tabla(lista)]
        elif self.busqueda.value or self.filtro != FILTRO_ACTIVOS:
            self.resultados.controls = [
                estado_vacio(ft.Icons.PERSON_SEARCH, "No hay resultados", "Prueba con otra búsqueda o filtro.")
            ]
        else:
            detalle = "Pulsa «Nuevo árbitro» para registrar el primero." if self.app.es_admin else ""
            self.resultados.controls = [estado_vacio(ft.Icons.PEOPLE_OUTLINE, "Aún no hay árbitros registrados", detalle)]
        if actualizar:
            self.page.update()

    def _cambiar_filtro(self, e) -> None:
        self.filtro = e.control.selected[0] if e.control.selected else FILTRO_ACTIVOS
        self.refrescar()

    def _tabla(self, lista: list[Arbitro]) -> ft.Control:
        filas = []
        for a in lista:
            acciones = [
                ft.IconButton(
                    ft.Icons.CHAT,
                    tooltip="Abrir chat de WhatsApp",
                    url=enlace_whatsapp(a.telefono),
                    icon_color=ft.Colors.PRIMARY,
                ),
                ft.IconButton(ft.Icons.HISTORY, tooltip="Historial de partidos y pagos",
                              on_click=lambda _, a=a: self._historial(a)),
                ft.IconButton(
                    ft.Icons.EDIT if self.app.es_admin else ft.Icons.VISIBILITY,
                    tooltip="Editar" if self.app.es_admin else "Ver detalle",
                    on_click=lambda _, a=a: self.abrir_formulario(a),
                ),
            ]
            if self.app.es_admin:
                acciones.append(
                    ft.IconButton(
                        ft.Icons.PERSON_OFF if a.activo else ft.Icons.PERSON,
                        tooltip="Desactivar" if a.activo else "Reactivar",
                        on_click=lambda _, a=a: self._alternar_activo(a),
                    )
                )
            filas.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(a.nombre, weight=ft.FontWeight.W_500)),
                        ft.DataCell(ft.Text(a.apodo or "—")),
                        ft.DataCell(ft.Text(formatear_telefono(a.telefono), selectable=True)),
                        ft.DataCell(ft.Text(a.categoria or "—")),
                        ft.DataCell(etiqueta("Activo" if a.activo else "Inactivo", a.activo)),
                        ft.DataCell(ft.Row(acciones, spacing=0)),
                    ]
                )
            )
        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Nombre")),
                ft.DataColumn(ft.Text("Apodo")),
                ft.DataColumn(ft.Text("Teléfono")),
                ft.DataColumn(ft.Text("Categoría")),
                ft.DataColumn(ft.Text("Estado")),
                ft.DataColumn(ft.Text("Acciones")),
            ],
            rows=filas,
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            border_radius=8,
            expand=True,
        )

    def _historial(self, a: Arbitro) -> None:
        lineas = sorted(self.app.pagos.lineas(arbitro_id=a.id), key=lambda l: (l.partido.fecha, l.partido.hora),
                        reverse=True)
        pagos = self.app.pagos.historial(a.id)
        jugados = [l for l in lineas if l.partido.se_juega]
        resumen = (f"{len(jugados)} partido(s) asignados · ganado {formatear_monto(sum(l.tarifa for l in lineas))} · "
                   f"pendiente {formatear_monto(sum(l.saldo for l in lineas if l.jugado and not l.liquidada))}")
        filas = [
            ft.DataRow(cells=[
                ft.DataCell(ft.Text(f"{fecha_corta(l.partido.fecha)} {l.partido.fecha.year}")),
                ft.DataCell(ft.Text(f"{l.liga.nombre} · {l.jornada}")),
                ft.DataCell(ft.Text(f"{l.partido.local.nombre} vs {l.partido.visitante.nombre}")),
                ft.DataCell(ft.Text(POSICIONES[l.posicion])),
                ft.DataCell(ft.Text(formatear_monto(l.tarifa))),
                ft.DataCell(etiqueta_pago(l)),
            ])
            for l in lineas[:100]
        ]
        contenido = [ft.Text(resumen, weight=ft.FontWeight.W_600)]
        if filas:
            contenido.append(ft.DataTable(
                columns=[ft.DataColumn(ft.Text(c)) for c in ("Fecha", "Liga", "Partido", "Posición", "Tarifa", "Pago")],
                rows=filas, column_spacing=16, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST))
        else:
            contenido.append(ft.Text("Todavía no tiene partidos asignados.", color=ft.Colors.ON_SURFACE_VARIANT))
        if pagos:
            contenido += [ft.Text("Pagos recibidos", weight=ft.FontWeight.W_600)] + [
                ft.Text(f"• {p.fecha:%d/%m/%Y}: {formatear_monto(p.monto_centavos)} ({n} partido(s))"
                        + (f" · {p.nota}" if p.nota else ""))
                for p, n in pagos]
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"Historial · {a.nombre}"),
            content=ft.Column(contenido, spacing=10, scroll=ft.ScrollMode.AUTO, height=480, width=ANCHO_DIALOGO + 420),
            actions=[ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())],
        ))

    def _alternar_activo(self, a: Arbitro) -> None:
        def aplicar():
            self.app.arbitros.cambiar_activo(a.id, not a.activo)
            avisar(self.page, f"{a.nombre} {'reactivado' if not a.activo else 'desactivado'}.")
            self.refrescar()

        if a.activo:
            confirmar(
                self.page,
                "Desactivar árbitro",
                f"{a.nombre} ya no aparecerá para asignar partidos. Su historial se conserva "
                "y puedes reactivarlo cuando quieras.",
                aplicar,
                "Desactivar",
            )
        else:
            aplicar()

    def abrir_formulario(self, arbitro: Arbitro | None = None) -> None:
        editable = self.app.es_admin
        nuevo = arbitro is None
        nombre = ft.TextField(label="Nombre completo *", value=arbitro.nombre if arbitro else "", autofocus=True)
        apodo = ft.TextField(label="Apodo", value=(arbitro.apodo or "") if arbitro else "")
        telefono = ft.TextField(
            label="Teléfono (WhatsApp) *",
            value=formatear_telefono(arbitro.telefono) if arbitro else "",
            keyboard_type=ft.KeyboardType.PHONE,
            prefix_icon=ft.Icons.PHONE,
            helper="10 dígitos, ej.: 33 1234 5678",
        )
        categoria = ft.TextField(
            label="Categoría o nivel",
            value=(arbitro.categoria or "") if arbitro else "",
            helper="Opcional. Ej.: A, B, Juvenil",
        )
        notas = ft.TextField(
            label="Notas", value=(arbitro.notas or "") if arbitro else "", multiline=True, min_lines=2, max_lines=4
        )
        activo = ft.Switch(label="Activo", value=arbitro.activo if arbitro else True, visible=not nuevo)
        campos = {"nombre": nombre, "telefono": telefono}
        for c in (nombre, apodo, telefono, categoria, notas, activo):
            c.disabled = not editable

        def datos() -> DatosArbitro:
            return DatosArbitro(
                nombre=nombre.value or "",
                telefono=telefono.value or "",
                apodo=apodo.value or "",
                categoria=categoria.value or "",
                notas=notas.value or "",
                activo=bool(activo.value),
            )

        def guardar(otro: bool):
            try:
                if nuevo:
                    guardado = self.app.arbitros.crear(datos())
                else:
                    guardado = self.app.arbitros.actualizar(arbitro.id, datos())
            except ErrorValidacion as e:
                mostrar_errores(campos, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, f"{guardado.nombre} guardado.")
            self.refrescar()
            if otro:
                self.abrir_formulario()

        if not editable:
            acciones = [ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())]
        else:
            acciones = [ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog())]
            if nuevo:
                acciones.append(ft.OutlinedButton("Guardar y agregar otro", on_click=lambda _: guardar(True)))
            acciones.append(ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=lambda _: guardar(False)))

        titulo = "Nuevo árbitro" if nuevo else ("Editar árbitro" if editable else "Detalle del árbitro")
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(titulo),
                content=ft.Column(
                    [nombre, apodo, telefono, categoria, notas, activo],
                    tight=True,
                    spacing=14,
                    width=ANCHO_DIALOGO,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=acciones,
            )
        )
