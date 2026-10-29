"""Reportes del periodo y exportación a Excel."""

import logging
import os
from pathlib import Path

import flet as ft

from arbitros.db.models import ESTADOS_PARTIDO, POSICIONES
from arbitros.services.dinero import formatear_monto
from arbitros.ui import tema
from arbitros.ui.comunes import FiltroPeriodo, avisar, encabezado, estado_vacio, fecha_corta, tarjeta, tarjeta_dato
from arbitros.ui.vistas.cobros import dialogo_recibo

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
                encabezado("Reportes", "Partidos arbitrados, pagos de árbitros y equipos, y cédulas del periodo.",
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
        controles += self._equipos(desde, hasta, liga_id)
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

    def _equipos(self, desde, hasta, liga_id) -> list[ft.Control]:
        """Quién pagó los arbitrajes: totales y tabla por equipo con su recibo."""
        resumen = self.app.cobros.resumen_por_equipo(desde, hasta, liga_id)
        total, pagado = sum(r.total for r in resumen), sum(r.pagado for r in resumen)
        debe = sum(r.pendiente for r in resumen)
        datos = ft.Row(
            [
                tarjeta_dato("Arbitrajes de equipos", formatear_monto(total), icono=ft.Icons.GROUPS),
                tarjeta_dato("Pagado por equipos", formatear_monto(pagado), tema.EXITO_TEXTO, ft.Icons.PAID),
                tarjeta_dato("Adeudo de equipos", formatear_monto(debe),
                             tema.PELIGRO_TEXTO if debe else tema.EXITO_TEXTO, ft.Icons.MONEY_OFF),
            ],
            spacing=12,
        )
        if not resumen:
            tabla = estado_vacio(ft.Icons.GROUPS, "Sin arbitrajes que cobrar en este periodo")
        else:
            filas = []
            for r in resumen:
                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Column([ft.Text(r.equipo.nombre, weight=ft.FontWeight.W_500),
                                           ft.Text(r.liga.nombre, size=12, color=ft.Colors.ON_SURFACE_VARIANT)],
                                          spacing=0, alignment=ft.MainAxisAlignment.CENTER)),
                    ft.DataCell(ft.Text(str(r.partidos))),
                    ft.DataCell(ft.Text(formatear_monto(r.total))),
                    ft.DataCell(ft.Text(formatear_monto(r.pagado), color=tema.EXITO_TEXTO if r.pagado else None)),
                    ft.DataCell(ft.Text(formatear_monto(r.pendiente), weight=ft.FontWeight.BOLD,
                                        color=tema.PELIGRO_TEXTO if r.pendiente else tema.EXITO_TEXTO)),
                    ft.DataCell(ft.Text(formatear_monto(r.a_favor), color=tema.EXITO_TEXTO if r.a_favor else None)),
                    ft.DataCell(ft.IconButton(ft.Icons.RECEIPT_LONG, tooltip="Ver recibo desglosado",
                                              on_click=lambda _, r=r: self._recibo(r.equipo.id))),
                ]))
            tabla = tarjeta(ft.Row([ft.DataTable(
                columns=[ft.DataColumn(ft.Text(t), numeric=n) for t, n in (
                    ("Equipo", False), ("Partidos", True), ("Arbitrajes", True), ("Pagado", True), ("Debe", True),
                    ("A favor", True), ("Recibo", False))],
                rows=filas, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST, data_row_max_height=60,
            )], scroll=ft.ScrollMode.AUTO))
        return [ft.Row([ft.Text("Arbitrajes pagados por equipo", size=18, weight=ft.FontWeight.W_600),
                        ft.TextButton("Registrar pagos", on_click=lambda _: self._ir_a_cobros())]),
                datos, tabla]

    def _recibo(self, equipo_id: int) -> None:
        desde, hasta = self.filtro.rango
        dialogo_recibo(self.app, self.app.cobros.recibo(equipo_id, desde, hasta))

    def _ir_a_cobros(self) -> None:
        self.app.seleccion["pagos_pestana"] = "equipos"
        self.shell.ir_a("pagos")

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
