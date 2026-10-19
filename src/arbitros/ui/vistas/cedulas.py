"""Cédulas arbitrales: subir PDF o fotos por partido, excepciones y pendientes."""

import os
from pathlib import Path

import flet as ft

from arbitros.services.cedulas import (
    EXCEPCION,
    NOMBRES_ESTADO,
    NO_REQUERIDA,
    PENDIENTE,
    PROXIMA,
    REGISTRADA,
    FilaCedula,
)
from arbitros.services.errores import ErrorValidacion
from arbitros.ui import tema
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    FiltroPeriodo,
    avisar,
    confirmar,
    encabezado,
    estado_vacio,
    fecha_corta,
    mostrar_errores,
    tarjeta,
)

FILTROS = {
    "pendientes": ("Pendientes", {PENDIENTE}),
    "registradas": ("Registradas", {REGISTRADA}),
    "excepciones": ("Excepciones", {EXCEPCION}),
    "todas": ("Todas", None),
}
COLORES = {
    REGISTRADA: (tema.EXITO_FONDO, tema.EXITO_TEXTO),
    EXCEPCION: (tema.AVISO_FONDO, tema.AVISO_TEXTO),
    PENDIENTE: (tema.PELIGRO_FONDO, tema.PELIGRO_TEXTO),
    PROXIMA: (ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT),
    NO_REQUERIDA: (ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT),
}


def construir(app, shell) -> ft.Control:
    return VistaCedulas(app).construir()


class VistaCedulas:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.filtro_estado = app.seleccion.get("cedulas_filtro", "pendientes")
        self.filtro = FiltroPeriodo(app, self.refrescar, periodo="todo")
        self.resumen = ft.Text(weight=ft.FontWeight.W_600)
        self.lista = ft.Container()

    def construir(self) -> ft.Control:
        estados = ft.SegmentedButton(
            selected=[self.filtro_estado],
            segments=[ft.Segment(value=k, label=ft.Text(v[0])) for k, v in FILTROS.items()],
            on_change=self._cambiar_estado,
        )
        self.refrescar(actualizar=False)
        return ft.Column(
            [
                encabezado("Cédulas", "Sube la cédula (PDF o foto) de cada partido y revisa cuáles faltan."),
                ft.Row([estados, self.filtro.control], spacing=16, wrap=True),
                self.resumen,
                self.lista,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def _cambiar_estado(self, e) -> None:
        self.filtro_estado = e.control.selected[0]
        self.app.seleccion["cedulas_filtro"] = self.filtro_estado
        self.refrescar()

    def refrescar(self, actualizar: bool = True) -> None:
        desde, hasta = self.filtro.rango
        filas = self.app.cedulas.listar(liga_id=self.filtro.liga_id, desde=desde, hasta=hasta,
                                        estados=FILTROS[self.filtro_estado][1])
        pendientes = len(self.app.cedulas.listar(liga_id=self.filtro.liga_id, desde=desde, hasta=hasta,
                                                 estados={PENDIENTE}))
        self.resumen.value = (f"Faltan {pendientes} cédula(s) de partidos ya jugados." if pendientes
                              else "✓ No hay cédulas pendientes en este periodo.")
        self.resumen.color = tema.PELIGRO_TEXTO if pendientes else tema.EXITO_TEXTO
        if not filas:
            self.lista.content = estado_vacio(ft.Icons.DESCRIPTION, "No hay partidos con este filtro")
        else:
            self.lista.content = tarjeta(self._tabla(filas))
        if actualizar:
            self.page.update()

    def _tabla(self, filas: list[FilaCedula]) -> ft.Control:
        varias_ligas = len({f.liga.id for f in filas}) > 1
        datos = []
        for f in filas:
            p = f.partido
            fondo, color = COLORES[f.estado]
            estado = ft.Container(ft.Text(NOMBRES_ESTADO[f.estado], size=12, weight=ft.FontWeight.W_500, color=color),
                                  bgcolor=fondo, border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=4),
                                  tooltip=f.motivo_excepcion)
            archivos = [self._chip_archivo(a) for a in f.archivos]
            if f.motivo_excepcion:
                archivos.append(ft.Text(f"Motivo: {f.motivo_excepcion}", size=12, italic=True))
            acciones = []
            if self.app.es_admin and f.estado != NO_REQUERIDA:
                acciones.append(ft.FilledTonalButton("Subir", icon=ft.Icons.UPLOAD_FILE,
                                                     on_click=self._manejador_subir(f)))
                if f.estado == EXCEPCION:
                    acciones.append(ft.IconButton(ft.Icons.UNDO, tooltip="Quitar excepción",
                                                  on_click=lambda _, f=f: self._quitar_excepcion(f)))
                elif f.estado != REGISTRADA:
                    acciones.append(ft.IconButton(ft.Icons.BLOCK, tooltip="No requiere cédula (excepción)…",
                                                  on_click=lambda _, f=f: self._excepcion(f)))
            lugar = f"{f.liga.nombre} · {f.jornada}" if varias_ligas else f.jornada
            datos.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(f"{fecha_corta(p.fecha)} {p.hora:%H:%M}")),
                ft.DataCell(ft.Text(lugar)),
                ft.DataCell(ft.Column([ft.Text(f"{p.local.nombre} vs {p.visitante.nombre}", weight=ft.FontWeight.W_500),
                                       ft.Text(p.campo.nombre if p.campo else "", size=12,
                                               color=ft.Colors.ON_SURFACE_VARIANT)],
                                      spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER)),
                ft.DataCell(estado),
                ft.DataCell(ft.Row(archivos, wrap=True, spacing=4, width=260)),
                ft.DataCell(ft.Row(acciones, spacing=4, tight=True)),
            ]))
        return ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c)) for c in ("Fecha", "Jornada", "Partido", "Estado", "Archivos", "")],
            rows=datos, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST, column_spacing=16,
            data_row_max_height=90,
        )

    def _chip_archivo(self, archivo) -> ft.Control:
        icono = ft.Icons.PICTURE_AS_PDF if archivo.ruta.lower().endswith(".pdf") else ft.Icons.IMAGE
        controles = [ft.Icon(icono, size=16),
                     ft.Text(archivo.nombre_original, size=12, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, width=120)]
        if self.app.es_admin:
            controles.append(ft.IconButton(ft.Icons.CLOSE, icon_size=14, tooltip="Quitar archivo",
                                           on_click=lambda _: self._quitar_archivo(archivo), width=28, height=28))
        return ft.Container(
            ft.Row(controles, spacing=4, tight=True),
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=8,
            padding=ft.Padding.only(left=8, right=2), tooltip="Abrir", ink=True,
            on_click=lambda _: self._abrir(archivo),
        )

    # --- Acciones -------------------------------------------------------------

    def _abrir(self, archivo) -> None:
        ruta = self.app.cedulas.ruta_absoluta(archivo)
        if not ruta.exists():
            avisar(self.page, "No se encontró el archivo en la carpeta de documentos.", error=True)
            return
        os.startfile(ruta)

    def _manejador_subir(self, f: FilaCedula):
        # Flet solo espera (await) los manejadores que son funciones async; una lambda que
        # llama a una función async crea la corrutina y nunca la ejecuta (el clic no hace nada).
        async def manejador(_):
            await self._subir(f)

        return manejador

    async def _subir(self, f: FilaCedula) -> None:
        archivos = await self.app.selector_archivos.pick_files(
            dialog_title=f"Cédula: {f.partido.local.nombre} vs {f.partido.visitante.nombre}",
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["pdf", "jpg", "jpeg", "png"],
            allow_multiple=True,
        )
        rutas = [Path(a.path) for a in archivos or [] if a.path]
        if not rutas:
            return
        try:
            self.app.cedulas.subir(f.partido.id, rutas)
        except ErrorValidacion as e:
            avisar(self.page, e.mensaje, error=True)
            return
        avisar(self.page, f"{len(rutas)} archivo(s) guardados.")
        self.refrescar()

    def _quitar_archivo(self, archivo) -> None:
        def aplicar():
            self.app.cedulas.quitar_archivo(archivo.id)
            self.refrescar()

        confirmar(self.page, "Quitar archivo", f"¿Quitar «{archivo.nombre_original}» de este partido?", aplicar, "Quitar")

    def _excepcion(self, f: FilaCedula) -> None:
        motivo = ft.TextField(label="Motivo *", autofocus=True,
                              hint_text="Ej.: cédula única del torneo, la entregó la liga…")

        def guardar(_):
            try:
                self.app.cedulas.marcar_excepcion(f.partido.id, motivo.value or "")
            except ErrorValidacion as e:
                mostrar_errores({"motivo": motivo}, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            self.refrescar()

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text("Este partido no requiere cédula"),
            content=ft.Column([ft.Text(f"{f.partido.local.nombre} vs {f.partido.visitante.nombre}"), motivo],
                              tight=True, spacing=12, width=ANCHO_DIALOGO),
            actions=[ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                     ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar)],
        ))

    def _quitar_excepcion(self, f: FilaCedula) -> None:
        self.app.cedulas.quitar_excepcion(f.partido.id)
        self.refrescar()
