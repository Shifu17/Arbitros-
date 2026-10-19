"""Cuadrícula semanal de disponibilidad: árbitros × días."""

from datetime import date, timedelta

import flet as ft

from arbitros.db.models import DISP_HORARIO, DISP_NO_DISPONIBLE, DISP_TODO_EL_DIA, Arbitro, Disponibilidad
from arbitros.services.disponibilidad import DatosDisponibilidad, describir, dias_de_semana, lunes_de
from arbitros.services.errores import ErrorValidacion
from arbitros.services.texto import sin_acentos
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    DIAS_CORTOS,
    MESES_CORTOS,
    CampoHora,
    avisar,
    confirmar,
    encabezado,
    estado_vacio,
    fecha_corta,
    mostrar_errores,
    tarjeta,
)

SIN_REGISTRAR = "sin_registrar"
OPCIONES = {
    DISP_TODO_EL_DIA: ("Todo el día", ft.Icons.CHECK_CIRCLE),
    DISP_HORARIO: ("Horario", ft.Icons.SCHEDULE),
    DISP_NO_DISPONIBLE: ("No disponible", ft.Icons.CANCEL),
    SIN_REGISTRAR: ("Sin registrar", ft.Icons.HELP_OUTLINE),
}


def colores(tipo: str | None) -> tuple[str, str]:
    """(fondo, texto) de la casilla según la disponibilidad."""
    return {
        DISP_TODO_EL_DIA: (ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER),
        DISP_HORARIO: (ft.Colors.TERTIARY_CONTAINER, ft.Colors.ON_TERTIARY_CONTAINER),
        DISP_NO_DISPONIBLE: (ft.Colors.ERROR_CONTAINER, ft.Colors.ON_ERROR_CONTAINER),
    }.get(tipo, (ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT))


def texto_corto(d: Disponibilidad | None) -> str:
    if d is None:
        return "—"
    if d.tipo == DISP_TODO_EL_DIA:
        return "✓ Todo el día"
    if d.tipo == DISP_HORARIO:
        return f"{d.desde:%H:%M}–{d.hasta:%H:%M}"
    return "✗ No"


def construir(app, shell) -> ft.Control:
    return VistaDisponibilidad(app).construir()


class VistaDisponibilidad:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.lunes = app.seleccion.get("semana") or lunes_de(date.today())
        self.titulo_semana = ft.Text(size=18, weight=ft.FontWeight.W_600)
        self.busqueda = ft.TextField(
            hint_text="Buscar árbitro", prefix_icon=ft.Icons.SEARCH, width=260, dense=True,
            on_change=lambda _: self.refrescar(),
        )
        self.tabla = ft.Container()

    def construir(self) -> ft.Control:
        acciones = []
        if self.app.es_admin:
            acciones = [
                ft.OutlinedButton("Copiar semana anterior", icon=ft.Icons.CONTENT_COPY, on_click=lambda _: self._copiar()),
                ft.IconButton(ft.Icons.TUNE, tooltip="Ajustes de choques de horario", on_click=lambda _: self._ajustes()),
            ]
        leyenda = ft.Row(
            [self._chip(t, OPCIONES[t][0]) for t in (DISP_TODO_EL_DIA, DISP_HORARIO, DISP_NO_DISPONIBLE, SIN_REGISTRAR)]
            + [ft.Text("· El número indica partidos ya asignados ese día.", size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
            wrap=True,
            spacing=8,
        )
        self.refrescar(actualizar=False)
        return ft.Column(
            [
                encabezado(
                    "Disponibilidad",
                    "Marca quién puede trabajar cada día. Haz clic en una casilla para cambiarla."
                    if self.app.es_admin else "Quién puede trabajar cada día.",
                    acciones,
                ),
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Semana anterior", on_click=lambda _: self._mover(-7)),
                        self.titulo_semana,
                        ft.IconButton(ft.Icons.CHEVRON_RIGHT, tooltip="Semana siguiente", on_click=lambda _: self._mover(7)),
                        ft.TextButton("Esta semana", on_click=lambda _: self._ir_a(lunes_de(date.today()))),
                        ft.Container(expand=True),
                        self.busqueda,
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                leyenda,
                self.tabla,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    # --- Semana -------------------------------------------------------------

    def _mover(self, dias: int) -> None:
        self._ir_a(self.lunes + timedelta(days=dias))

    def _ir_a(self, lunes: date) -> None:
        self.lunes = lunes
        self.app.seleccion["semana"] = lunes
        self.refrescar()

    def refrescar(self, actualizar: bool = True) -> None:
        dias = dias_de_semana(self.lunes)
        fin = dias[-1]
        mes_ini, mes_fin = MESES_CORTOS[self.lunes.month - 1], MESES_CORTOS[fin.month - 1]
        self.titulo_semana.value = (
            f"Semana del {self.lunes.day} al {fin.day} de {mes_fin} {fin.year}" if mes_ini == mes_fin
            else f"Semana del {self.lunes.day} {mes_ini} al {fin.day} {mes_fin} {fin.year}"
        )
        arbitros = self.app.arbitros.listar(self.busqueda.value or "")
        if not arbitros:
            self.tabla.content = estado_vacio(
                ft.Icons.PEOPLE_OUTLINE,
                "No hay árbitros" if not self.busqueda.value else "Sin resultados",
                "Registra árbitros en la sección Árbitros." if not self.busqueda.value else "",
            )
        else:
            disp = self.app.disponibilidad.de_semana(self.lunes)
            partidos = self.app.asignaciones.partidos_por_arbitro(self.lunes, fin)
            self.tabla.content = tarjeta(self._tabla(arbitros, dias, disp, partidos))
        if actualizar:
            self.page.update()

    # --- Tabla --------------------------------------------------------------

    @staticmethod
    def _chip(tipo: str | None, texto: str, extra: int = 0) -> ft.Control:
        fondo, color = colores(None if tipo == SIN_REGISTRAR else tipo)
        controles = [ft.Text(texto, size=12, weight=ft.FontWeight.W_500, color=color)]
        if extra:
            controles.append(
                ft.Container(ft.Text(str(extra), size=11, color=ft.Colors.ON_PRIMARY, weight=ft.FontWeight.BOLD),
                             bgcolor=ft.Colors.PRIMARY, border_radius=10, padding=ft.Padding.symmetric(horizontal=6))
            )
        return ft.Container(ft.Row(controles, spacing=4, tight=True), bgcolor=fondo, border_radius=8,
                            padding=ft.Padding.symmetric(horizontal=8, vertical=4))

    def _tabla(self, arbitros: list[Arbitro], dias: list[date], disp, partidos) -> ft.Control:
        hoy = date.today()
        columnas = [ft.DataColumn(ft.Text("Árbitro"))]
        for d in dias:
            etiqueta = ft.Text(f"{DIAS_CORTOS[d.weekday()].capitalize()} {d.day}",
                               weight=ft.FontWeight.BOLD if d == hoy else None,
                               color=ft.Colors.PRIMARY if d == hoy else None)
            if self.app.es_admin:
                etiqueta = ft.Row([etiqueta, self._menu_dia(d)], spacing=0, tight=True)
            columnas.append(ft.DataColumn(etiqueta))
        filas = []
        for a in arbitros:
            celdas = [ft.DataCell(ft.Text(a.apodo or a.nombre, weight=ft.FontWeight.W_500, tooltip=a.nombre))]
            for d in dias:
                registro = disp.get((a.id, d))
                chip = self._chip(registro.tipo if registro else SIN_REGISTRAR, texto_corto(registro),
                                  partidos.get((a.id, d), 0))
                chip.tooltip = describir(registro) + (f" · {registro.nota}" if registro and registro.nota else "")
                if self.app.es_admin:
                    chip.on_click = lambda _, a=a, d=d, r=registro: self._editar(a, d, r)
                    chip.ink = True
                celdas.append(ft.DataCell(chip))
            filas.append(ft.DataRow(cells=celdas))
        return ft.DataTable(columns=columnas, rows=filas, column_spacing=12,
                            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST)

    def _menu_dia(self, d: date) -> ft.Control:
        def todos_disponibles(_):
            n = self.app.disponibilidad.marcar_dia_para_todos(d, DatosDisponibilidad(DISP_TODO_EL_DIA))
            avisar(self.page, f"{n} árbitro(s) marcados como disponibles el {fecha_corta(d)}.")
            self.refrescar()

        def limpiar(_):
            def aplicar():
                self.app.disponibilidad.limpiar_dia(d)
                self.refrescar()

            confirmar(self.page, "Borrar el día", f"Se borrará la disponibilidad de todos el {fecha_corta(d)}.",
                      aplicar, "Borrar")

        return ft.PopupMenuButton(
            icon=ft.Icons.ARROW_DROP_DOWN,
            tooltip=f"Acciones para el {fecha_corta(d)}",
            items=[
                ft.PopupMenuItem("Marcar como disponibles todo el día a los que no han respondido",
                                 icon=ft.Icons.DONE_ALL, on_click=todos_disponibles),
                ft.PopupMenuItem("Borrar la disponibilidad de este día", icon=ft.Icons.DELETE_OUTLINE, on_click=limpiar),
            ],
        )

    # --- Diálogos ------------------------------------------------------------

    def _editar(self, arbitro: Arbitro, dia: date, registro: Disponibilidad | None) -> None:
        tipo_actual = registro.tipo if registro else SIN_REGISTRAR
        selector = ft.SegmentedButton(
            selected=[tipo_actual],
            segments=[ft.Segment(value=k, label=ft.Text(v[0]), icon=ft.Icon(v[1])) for k, v in OPCIONES.items()],
        )
        desde = CampoHora(self.page, "Desde *", registro.desde if registro else None, width=170)
        hasta = CampoHora(self.page, "Hasta *", registro.hasta if registro else None, width=170)
        horario = ft.Row([desde.campo, hasta.campo], spacing=12, visible=tipo_actual == DISP_HORARIO)
        nota = ft.TextField(label="Nota (opcional)", value=(registro.nota or "") if registro else "",
                            hint_text="Ej.: llega tarde, solo campo 1…")
        dias = dias_de_semana(self.lunes)
        otros_dias = {
            d: ft.Checkbox(label=f"{DIAS_CORTOS[d.weekday()]} {d.day}", value=d == dia, disabled=d == dia) for d in dias
        }

        def cambiar_tipo(e):
            horario.visible = e.control.selected[0] == DISP_HORARIO
            self.page.update()

        selector.on_change = cambiar_tipo

        def guardar(_):
            tipo = selector.selected[0]
            if tipo == DISP_HORARIO and not (desde.validar() & hasta.validar()):
                self.page.update()
                return
            datos = DatosDisponibilidad(
                None if tipo == SIN_REGISTRAR else tipo,
                desde.valor if tipo == DISP_HORARIO else None,
                hasta.valor if tipo == DISP_HORARIO else None,
                nota.value or "",
            )
            fechas = [d for d, chk in otros_dias.items() if chk.value]
            try:
                self.app.disponibilidad.guardar(arbitro.id, fechas, datos)
            except ErrorValidacion as e:
                mostrar_errores({"desde": desde.campo, "hasta": hasta.campo}, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            self.refrescar()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"{arbitro.nombre} · {fecha_corta(dia)}"),
                content=ft.Column(
                    [
                        selector,
                        horario,
                        nota,
                        ft.Text("Aplicar también a:", weight=ft.FontWeight.W_500),
                        ft.Row(list(otros_dias.values()), wrap=True, spacing=0),
                    ],
                    tight=True,
                    spacing=14,
                    width=ANCHO_DIALOGO + 200,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )

    def _copiar(self) -> None:
        anterior = self.lunes - timedelta(days=7)

        def aplicar():
            n = self.app.disponibilidad.copiar_semana(anterior, self.lunes)
            avisar(self.page, f"Se copiaron {n} día(s). Lo que ya estaba registrado esta semana no se cambió."
                   if n else "No había nada nuevo que copiar.")
            self.refrescar()

        confirmar(
            self.page,
            "Copiar semana anterior",
            "Se copiará lo que cada árbitro tenía la semana pasada (mismo día de la semana). "
            "Las casillas que ya tengan algo esta semana no se tocan.",
            aplicar,
            "Copiar",
        )

    def _ajustes(self) -> None:
        actuales = self.app.asignaciones.ajustes()
        duracion = ft.TextField(label="Duración de un partido (minutos)", value=str(actuales.duracion_min),
                                keyboard_type=ft.KeyboardType.NUMBER)
        descanso = ft.TextField(label="Tiempo mínimo entre partidos de un árbitro (minutos)",
                                value=str(actuales.descanso_min), keyboard_type=ft.KeyboardType.NUMBER,
                                helper="Para trasladarse de campo o descansar")

        def guardar(_):
            try:
                self.app.asignaciones.guardar_ajustes(int(duracion.value or 0), int(descanso.value or 0))
            except ValueError:
                mostrar_errores({"duracion": duracion, "descanso": descanso},
                                {"duracion": "Solo números", "descanso": "Solo números"})
                self.page.update()
                return
            except ErrorValidacion as e:
                mostrar_errores({"duracion": duracion, "descanso": descanso}, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, "Ajustes guardados.")

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Ajustes de choques de horario"),
                content=ft.Column(
                    [
                        ft.Text("Se usan para avisarte si a un árbitro se le cruzan dos partidos o si un partido "
                                "termina después de su horario disponible."),
                        duracion,
                        descanso,
                    ],
                    tight=True,
                    spacing=14,
                    width=ANCHO_DIALOGO,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )
