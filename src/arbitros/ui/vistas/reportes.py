"""Reportes del periodo y exportación a Excel."""

import logging
import os
from pathlib import Path

import flet as ft

from arbitros.db.models import ESTADOS_PARTIDO, POSICIONES
from arbitros.services.dinero import formatear_monto
from arbitros.ui import tema
from arbitros.ui.comunes import FiltroPeriodo, avisar, encabezado, estado_vacio, fecha_corta, tarjeta, tarjeta_dato

log = logging.getLogger(__name__)


def construir(app, shell) -> ft.Control:
    return VistaReportes(app, shell).construir()


class VistaReportes:
    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.page = app.page
        self.filtro = FiltroPeriodo(app, self.refrescar)
        self.contenido = ft.Column(spacing=16)

    def construir(self) -> ft.Control:
        self.refrescar(actualizar=False)
        return ft.Column(
            [
                encabezado("Reportes", "Partidos arbitrados, pagos y cédulas del periodo.",
                           [ft.FilledButton("Exportar a Excel…", icon=ft.Icons.TABLE_VIEW, on_click=self._exportar)]),
                self.filtro.control,
                self.contenido,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def refrescar(self, actualizar: bool = True) -> None:
        desde, hasta = self.filtro.rango
        liga_id = self.filtro.liga_id
        estados = self.app.reportes.partidos_por_estado(desde, hasta, liga_id)
        arbitrajes = self.app.reportes.arbitrajes(desde, hasta, liga_id)
        resumen = self.app.pagos.resumen_por_arbitro(desde, hasta, liga_id)
        cedulas = self.app.reportes.cedulas_pendientes(desde, hasta, liga_id)
        pendiente = sum(r.pendiente for r in resumen)

        datos = ft.Row(
            [
                tarjeta_dato("Partidos",
                             str(estados.get("programado", 0) + estados.get("jugado", 0)), icono=ft.Icons.SPORTS_SOCCER),
                tarjeta_dato("Cancelados / suspendidos",
                             str(estados.get("cancelado", 0) + estados.get("suspendido", 0)), icono=ft.Icons.EVENT_BUSY),
                tarjeta_dato("Pagos pendientes", formatear_monto(pendiente),
                             tema.PELIGRO_TEXTO if pendiente else tema.EXITO_TEXTO, ft.Icons.PAYMENTS),
                tarjeta_dato("Cédulas pendientes", str(len(cedulas)),
                             tema.PELIGRO_TEXTO if cedulas else tema.EXITO_TEXTO, ft.Icons.DESCRIPTION),
            ],
            spacing=12,
        )
        if arbitrajes:
            posiciones = [p for p in POSICIONES if any(f.por_posicion.get(p) for f in arbitrajes)]
            tabla_arbitros = tarjeta(ft.DataTable(
                columns=[ft.DataColumn(ft.Text("Árbitro"))]
                + [ft.DataColumn(ft.Text(POSICIONES[p]), numeric=True) for p in posiciones]
                + [ft.DataColumn(ft.Text("Total"), numeric=True), ft.DataColumn(ft.Text("Ganado"), numeric=True),
                   ft.DataColumn(ft.Text("Pendiente"), numeric=True)],
                rows=[ft.DataRow(cells=[ft.DataCell(ft.Text(f.nombre, weight=ft.FontWeight.W_500))]
                                 + [ft.DataCell(ft.Text(str(f.por_posicion.get(p, 0)))) for p in posiciones]
                                 + [ft.DataCell(ft.Text(str(f.total_partidos), weight=ft.FontWeight.BOLD)),
                                    ft.DataCell(ft.Text(formatear_monto(f.ganado))),
                                    ft.DataCell(ft.Text(formatear_monto(f.pendiente),
                                                        color=tema.PELIGRO_TEXTO if f.pendiente else None))])
                      for f in arbitrajes],
                heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            ))
        else:
            tabla_arbitros = estado_vacio(ft.Icons.PEOPLE_OUTLINE, "Sin partidos arbitrados en este periodo")

        estados_txt = " · ".join(f"{ESTADOS_PARTIDO[e]}: {n}" for e, n in estados.items() if n) or "Sin partidos"
        controles = [
            datos,
            ft.Text(estados_txt, color=ft.Colors.ON_SURFACE_VARIANT),
            ft.Text("Partidos arbitrados por árbitro", size=18, weight=ft.FontWeight.W_600),
            tabla_arbitros,
        ]
        if cedulas:
            controles += [
                ft.Row([ft.Text("Cédulas pendientes", size=18, weight=ft.FontWeight.W_600),
                        ft.TextButton("Ir a Cédulas", on_click=lambda _: self.shell.ir_a("cedulas"))]),
                tarjeta(ft.Column([
                    ft.Text(f"{fecha_corta(c.partido.fecha)} {c.partido.hora:%H:%M} · {c.liga.nombre} · "
                            f"{c.partido.local.nombre} vs {c.partido.visitante.nombre}")
                    for c in cedulas[:30]
                ] + ([ft.Text(f"… y {len(cedulas) - 30} más", italic=True)] if len(cedulas) > 30 else []), spacing=4)),
            ]
        self.contenido.controls = controles
        if actualizar:
            self.page.update()

    async def _exportar(self, _) -> None:
        desde, hasta = self.filtro.rango
        nombre = "reporte_arbitros" + (f"_{desde:%Y%m%d}_{hasta:%Y%m%d}" if desde and hasta else "") + ".xlsx"
        ruta = await self.app.selector_archivos.save_file(
            dialog_title="Guardar reporte de Excel", file_name=nombre,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["xlsx"])
        if not ruta:
            return
        try:
            destino = self.app.reportes.exportar_excel(Path(ruta), desde, hasta, self.filtro.liga_id)
        except PermissionError:
            avisar(self.page, "No se pudo guardar: ¿el archivo está abierto en Excel? Ciérralo e inténtalo de nuevo.",
                   error=True)
            return
        except Exception:
            log.exception("Error al exportar a Excel")
            avisar(self.page, "No se pudo exportar el reporte.", error=True)
            return
        avisar(self.page, f"Reporte guardado en {destino}")
        try:
            os.startfile(destino)
        except OSError:
            pass
