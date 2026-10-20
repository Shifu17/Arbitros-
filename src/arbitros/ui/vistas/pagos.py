"""Pagos: resumen por árbitro, captura de lo pagado en campo e historial de liquidaciones."""

from datetime import date
from urllib.parse import quote

import flet as ft

from arbitros.ui import filtros

from arbitros.db.models import POSICIONES
from arbitros.services.arbitros import enlace_whatsapp
from arbitros.services.dinero import a_centavos, formatear_monto, monto_editable
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import etiqueta_jornada
from arbitros.services.pagos import LineaPago, ResumenArbitro
from arbitros.ui import tema
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    CampoFecha,
    FiltroPeriodo,
    avisar,
    confirmar,
    encabezado,
    estado_vacio,
    fecha_corta,
    rango_fechas,
    tarjeta,
    tarjeta_dato,
)


def construir(app, shell) -> ft.Control:
    return VistaPagos(app, shell).construir()


def etiqueta_pago(l: LineaPago) -> ft.Control:
    if l.liquidada:
        texto, fondo, color = "Pagado", tema.EXITO_FONDO, tema.EXITO_TEXTO
    elif l.saldo == 0:
        texto, fondo, color = "Pagado en campo", tema.EXITO_FONDO, tema.EXITO_TEXTO
    elif not l.jugado:
        texto, fondo, color = "Por jugarse", ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT
    else:
        texto, fondo, color = "Pendiente", tema.PELIGRO_FONDO, tema.PELIGRO_TEXTO
    return ft.Container(ft.Text(texto, size=12, weight=ft.FontWeight.W_500, color=color), bgcolor=fondo,
                        border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=4))


class VistaPagos:
    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.page = app.page
        self.pestana = app.seleccion.get("pagos_pestana", "arbitros")
        self.cuerpo = ft.Container(expand=True)
        self.filtro = FiltroPeriodo(app, self.refrescar)

    def construir(self) -> ft.Control:
        pestanas = ft.SegmentedButton(
            selected=[self.pestana],
            segments=[
                ft.Segment(value="arbitros", label=ft.Text("Por árbitro"), icon=ft.Icon(ft.Icons.PEOPLE)),
                ft.Segment(value="campo", label=ft.Text("Registrar pagos en campo"), icon=ft.Icon(ft.Icons.SPORTS)),
                ft.Segment(value="historial", label=ft.Text("Pagos realizados"), icon=ft.Icon(ft.Icons.HISTORY)),
            ],
            on_change=self._cambiar_pestana,
        )
        self.refrescar(actualizar=False)
        return ft.Column(
            [encabezado("Pagos", "Tarifa − pagado en campo − pagado después = lo que se le debe al árbitro."),
             pestanas, self.cuerpo],
            spacing=16,
            expand=True,
        )

    def _cambiar_pestana(self, e) -> None:
        self.pestana = e.control.selected[0]
        self.app.seleccion["pagos_pestana"] = self.pestana
        self.refrescar()

    def refrescar(self, actualizar: bool = True) -> None:
        if self.pestana == "campo":
            self.cuerpo.content = PanelCampo(self.app, self.shell).construir()
        elif self.pestana == "historial":
            self.cuerpo.content = self._historial()
        else:
            self.cuerpo.content = self._por_arbitro()
        if actualizar:
            self.page.update()

    # --- Por árbitro -----------------------------------------------------------

    def _por_arbitro(self) -> ft.Control:
        desde, hasta = self.filtro.rango
        resumenes = self.app.pagos.resumen_por_arbitro(desde, hasta, self.filtro.liga_id)
        totales = ft.Row(
            [
                tarjeta_dato("Total del periodo", formatear_monto(sum(r.total for r in resumenes)), icono=ft.Icons.PAYMENTS),
                tarjeta_dato("Pagado en campo", formatear_monto(sum(r.pagado_campo for r in resumenes)),
                             tema.EXITO_ICONO, ft.Icons.SPORTS),
                tarjeta_dato("Pagado después", formatear_monto(sum(r.liquidado for r in resumenes)),
                             tema.EXITO_ICONO, ft.Icons.MARK_EMAIL_READ),
                tarjeta_dato("Pendiente de pagar", formatear_monto(sum(r.pendiente for r in resumenes)),
                             tema.PELIGRO_TEXTO, ft.Icons.WARNING_AMBER),
            ],
            spacing=12,
        )
        if not resumenes:
            tabla = estado_vacio(ft.Icons.PAYMENTS, "Sin partidos asignados en este periodo",
                                 "Asigna árbitros en Jornadas y partidos.")
        else:
            filas = []
            for r in resumenes:
                acciones = [
                    ft.IconButton(ft.Icons.LIST_ALT, tooltip="Ver detalle", on_click=lambda _, r=r: self._detalle(r)),
                    ft.IconButton(ft.Icons.CHAT, tooltip="Enviar estado de cuenta por WhatsApp",
                                  on_click=lambda _, r=r: self._estado_cuenta(r)),
                ]
                if self.app.es_admin and r.pendiente > 0:
                    acciones.insert(0, ft.FilledButton("Pagar…", icon=ft.Icons.PAYMENTS,
                                                       on_click=lambda _, r=r: self._dialogo_pagar(r.arbitro.id)))
                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(r.arbitro.nombre, weight=ft.FontWeight.W_500)),
                    ft.DataCell(ft.Text(str(r.partidos))),
                    ft.DataCell(ft.Text(formatear_monto(r.total))),
                    ft.DataCell(ft.Text(formatear_monto(r.pagado_campo))),
                    ft.DataCell(ft.Text(formatear_monto(r.liquidado))),
                    ft.DataCell(ft.Text(formatear_monto(r.pendiente), weight=ft.FontWeight.BOLD,
                                        color=tema.PELIGRO_TEXTO if r.pendiente else tema.EXITO_TEXTO)),
                    ft.DataCell(ft.Text(formatear_monto(r.por_jugar), color=ft.Colors.ON_SURFACE_VARIANT)),
                    ft.DataCell(ft.Row(acciones, spacing=0, tight=True)),
                ]))
            tabla = tarjeta(ft.DataTable(
                columns=[ft.DataColumn(ft.Text(t), numeric=n) for t, n in (
                    ("Árbitro", False), ("Partidos", True), ("Total", True), ("En campo", True),
                    ("Pagado después", True), ("Pendiente", True), ("Por jugarse", True), ("", False))],
                rows=filas, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST, column_spacing=20,
            ))
        return ft.Column([self.filtro.control, totales, tabla], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def _tabla_lineas(self, lineas: list[LineaPago], casillas: dict | None = None) -> ft.Control:
        filas = []
        for l in lineas:
            p = l.partido
            celdas = [
                ft.DataCell(ft.Text(f"{fecha_corta(p.fecha)} {p.hora:%H:%M}")),
                ft.DataCell(ft.Text(f"{p.local.nombre} vs {p.visitante.nombre}", weight=ft.FontWeight.W_500,
                                    tooltip=f"{l.liga.nombre} · {l.jornada}")),
                ft.DataCell(ft.Text(POSICIONES[l.posicion])),
                ft.DataCell(ft.Text(formatear_monto(l.tarifa))),
                ft.DataCell(ft.Text(formatear_monto(l.pagado_campo))),
                ft.DataCell(ft.Text(formatear_monto(l.saldo), weight=ft.FontWeight.BOLD)),
                ft.DataCell(etiqueta_pago(l)),
            ]
            if casillas is not None:
                celdas.insert(0, ft.DataCell(casillas[l.asignacion_id]))
            filas.append(ft.DataRow(cells=celdas))
        columnas = ["Fecha", "Partido", "Posición", "Tarifa", "En campo", "Saldo", "Estado"]
        if casillas is not None:
            columnas.insert(0, "")
        return ft.DataTable(columns=[ft.DataColumn(ft.Text(c)) for c in columnas], rows=filas, column_spacing=16,
                            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST)

    def _detalle(self, r: ResumenArbitro) -> None:
        desde, hasta = self.filtro.rango
        lineas = self.app.pagos.lineas(desde, hasta, self.filtro.liga_id, arbitro_id=r.arbitro.id)
        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"{r.arbitro.nombre} · {self.filtro.descripcion}"),
            content=ft.Column([self._tabla_lineas(lineas)], scroll=ft.ScrollMode.AUTO, height=460,
                              width=ANCHO_DIALOGO + 420),
            actions=[ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())],
        ))

    def _estado_cuenta(self, r: ResumenArbitro) -> None:
        texto = self.app.pagos.estado_de_cuenta(r.arbitro.id)

        async def copiar(_):
            await self.app.portapapeles.set(texto)
            avisar(self.page, "Estado de cuenta copiado.")

        self.page.show_dialog(ft.AlertDialog(
            title=ft.Text(f"Estado de cuenta · {r.arbitro.nombre}"),
            content=ft.Container(ft.Text(texto, selectable=True), bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                                 border_radius=12, padding=16, width=ANCHO_DIALOGO + 100),
            actions=[
                ft.TextButton("Copiar", icon=ft.Icons.CONTENT_COPY, on_click=copiar),
                ft.FilledButton("Abrir WhatsApp", icon=ft.Icons.CHAT,
                                url=f"{enlace_whatsapp(r.arbitro.telefono)}?text={quote(texto)}"),
                ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog()),
            ],
        ))

    def _dialogo_pagar(self, arbitro_id: int) -> None:
        pendientes = self.app.pagos.pendientes_de(arbitro_id)
        if not pendientes:
            avisar(self.page, "No tiene partidos pendientes de pago.")
            return
        arbitro = pendientes[0].arbitro
        total = ft.Text(size=20, weight=ft.FontWeight.BOLD)
        casillas = {l.asignacion_id: ft.Checkbox(value=True) for l in pendientes}
        fecha = CampoFecha(self.page, "Fecha del pago", date.today(), width=200)
        nota = ft.TextField(label="Nota (opcional)", hint_text="Ej.: transferencia, efectivo…", expand=True)

        def recalcular(_=None):
            elegidos = [l for l in pendientes if casillas[l.asignacion_id].value]
            total.value = f"Total a pagar: {formatear_monto(sum(l.saldo for l in elegidos))}"
            self.page.update()

        for c in casillas.values():
            c.on_change = recalcular
        total.value = f"Total a pagar: {formatear_monto(sum(l.saldo for l in pendientes))}"

        def pagar(_):
            if not fecha.validar():
                self.page.update()
                return
            ids = [i for i, c in casillas.items() if c.value]
            try:
                pago = self.app.pagos.liquidar(arbitro_id, ids, fecha.valor, nota.value or "")
            except ErrorValidacion as e:
                avisar(self.page, e.mensaje, error=True)
                return
            self.page.pop_dialog()
            avisar(self.page, f"Pago de {formatear_monto(pago.monto_centavos)} a {arbitro.nombre} registrado.")
            self.refrescar()

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Pagar a {arbitro.nombre}"),
            content=ft.Column(
                [ft.Text("Marca los partidos que le estás pagando. Se paga el saldo completo de cada uno."),
                 ft.Container(self._tabla_lineas(pendientes, casillas), height=320),
                 ft.Row([fecha.campo, nota], spacing=12),
                 total],
                tight=True, spacing=12, width=ANCHO_DIALOGO + 460, scroll=ft.ScrollMode.AUTO,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton("Registrar pago", icon=ft.Icons.PAYMENTS, on_click=pagar),
            ],
        ))

    # --- Historial ---------------------------------------------------------

    def _historial(self) -> ft.Control:
        desde, hasta = self.filtro.rango
        pagos = [(p, n) for p, n in self.app.pagos.historial()
                 if (not desde or p.fecha >= desde) and (not hasta or p.fecha <= hasta)]
        if not pagos:
            contenido = estado_vacio(ft.Icons.HISTORY, "No hay pagos registrados en este periodo",
                                     "Los pagos se registran desde «Por árbitro» → «Pagar…».")
        else:
            filas = []
            for pago, n in pagos:
                acciones = []
                if self.app.es_admin:
                    acciones.append(ft.IconButton(ft.Icons.UNDO, tooltip="Deshacer este pago",
                                                  on_click=lambda _, p=pago: self._deshacer(p)))
                filas.append(ft.DataRow(cells=[
                    ft.DataCell(ft.Text(pago.fecha.strftime("%d/%m/%Y"))),
                    ft.DataCell(ft.Text(pago.arbitro.nombre, weight=ft.FontWeight.W_500)),
                    ft.DataCell(ft.Text(formatear_monto(pago.monto_centavos), weight=ft.FontWeight.BOLD)),
                    ft.DataCell(ft.Text(str(n))),
                    ft.DataCell(ft.Text(pago.nota or "—")),
                    ft.DataCell(ft.Row(acciones, spacing=0)),
                ]))
            contenido = tarjeta(ft.DataTable(
                columns=[ft.DataColumn(ft.Text(c)) for c in ("Fecha", "Árbitro", "Monto", "Partidos", "Nota", "")],
                rows=filas, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST))
        return ft.Column([self.filtro.control, contenido], spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    def _deshacer(self, pago) -> None:
        def aplicar():
            self.app.pagos.deshacer_pago(pago.id)
            avisar(self.page, "Pago deshecho; esos partidos vuelven a quedar pendientes.")
            self.refrescar()

        confirmar(self.page, "Deshacer pago",
                  f"Se eliminará el pago de {formatear_monto(pago.monto_centavos)} a {pago.arbitro.nombre} "
                  f"del {pago.fecha:%d/%m/%Y} y sus partidos volverán a quedar pendientes.", aplicar, "Deshacer")


class PanelCampo:
    """Captura, por jornada, de lo que se pagó a cada árbitro en el campo."""

    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.page = app.page
        self.contenido = ft.Column(spacing=12)

    def construir(self) -> ft.Control:
        ligas = self.app.ligas.listar()
        if not ligas:
            return estado_vacio(ft.Icons.EMOJI_EVENTS, "Primero registra una liga")
        ids = [r.liga.id for r in ligas]
        liga_id = self.app.seleccion.get("liga_id") if self.app.seleccion.get("liga_id") in ids else ids[0]
        self.selector_liga = ft.Dropdown(
            label="Liga o torneo", value=str(liga_id), width=300, dense=True,
            options=[ft.DropdownOption(key=str(r.liga.id), text=r.liga.nombre) for r in ligas],
            on_select=lambda e: self._cambiar_liga(int(e.control.value)),
        )
        self.selector_jornada = ft.Dropdown(label="Jornada", width=320, dense=True, on_select=self._cambiar_jornada)
        self._cambiar_liga(liga_id, actualizar=False)
        return ft.Column(
            [ft.Row([self.selector_liga, self.selector_jornada], spacing=12, wrap=True), self.contenido],
            spacing=16, scroll=ft.ScrollMode.AUTO, expand=True,
        )

    def _cambiar_liga(self, liga_id: int, actualizar: bool = True) -> None:
        if self.app.seleccion.get("liga_id") != liga_id:
            self.app.seleccion["jornada_id"] = None
        self.app.seleccion["liga_id"] = liga_id
        self.liga = self.app.ligas.obtener(liga_id)
        jornadas = self.app.jornadas.listar(liga_id)
        self.selector_jornada.options = [
            ft.DropdownOption(key=str(r.jornada.id), text=f"{etiqueta_jornada(self.liga, r.jornada)} · "
                                                          f"{rango_fechas(r.jornada.fecha_inicio, r.jornada.fecha_fin)}")
            for r in jornadas]
        ids = [r.jornada.id for r in jornadas]
        actual = self.app.seleccion.get("jornada_id")
        self.jornada_id = actual if actual in ids else (ids[-1] if ids else None)
        self.selector_jornada.value = str(self.jornada_id) if self.jornada_id else None
        self.refrescar(actualizar)

    def _cambiar_jornada(self, e) -> None:
        self.jornada_id = int(e.control.value)
        self.app.seleccion["jornada_id"] = self.jornada_id
        self.refrescar()

    def refrescar(self, actualizar: bool = True) -> None:
        if self.jornada_id is None:
            self.contenido.controls = [estado_vacio(ft.Icons.CALENDAR_MONTH, "Esta liga aún no tiene jornadas")]
        else:
            lineas = self.app.pagos.lineas(jornada_id=self.jornada_id)
            if not lineas:
                self.contenido.controls = [estado_vacio(ft.Icons.PERSON_SEARCH, "No hay árbitros asignados en esta jornada")]
            else:
                pendientes = [l for l in lineas if l.saldo and not l.liquidada]
                ayuda = ft.Text("Escribe cuánto se le pagó a cada árbitro en el campo. Se guarda al salir del "
                                "campo. Si ese partido se pagó distinto, puedes corregir la tarifa.",
                                color=ft.Colors.ON_SURFACE_VARIANT)
                acciones = []
                if self.app.es_admin and pendientes:
                    acciones.append(ft.OutlinedButton(
                        "Todo se pagó completo en campo", icon=ft.Icons.DONE_ALL,
                        on_click=lambda _: self._todo_completo([l.asignacion_id for l in pendientes])))
                resumen = ft.Text(
                    f"Total {formatear_monto(sum(l.tarifa for l in lineas))} · en campo "
                    f"{formatear_monto(sum(l.pagado_campo for l in lineas))} · pendiente "
                    f"{formatear_monto(sum(l.saldo for l in lineas if not l.liquidada))}",
                    weight=ft.FontWeight.W_600)
                self.contenido.controls = [ayuda, ft.Row([resumen, *acciones], wrap=True, spacing=16),
                                           tarjeta(self._tabla(lineas))]
        if actualizar:
            self.page.update()

    def _tabla(self, lineas: list[LineaPago]) -> ft.Control:
        filas = []
        for l in lineas:
            editable = self.app.es_admin and not l.liquidada
            p = l.partido
            tarifa = ft.TextField(value=monto_editable(l.tarifa), prefix=ft.Text("$ "), width=120, dense=True,
                                  input_filter=filtros.MONTO,
                                  text_align=ft.TextAlign.RIGHT, read_only=not editable,
                                  border_color=tema.AVISO_ICONO if l.tarifa_fija else None,
                                  tooltip="Tarifa de este partido")
            campo = ft.TextField(value=monto_editable(l.pagado_campo) if l.pagado_campo else "", prefix=ft.Text("$ "),
                                 input_filter=filtros.MONTO,
                                 width=120, dense=True, text_align=ft.TextAlign.RIGHT, read_only=not editable,
                                 hint_text="0", autofocus=False)

            def guardar(_, l=l, tarifa=tarifa, campo=campo):
                try:
                    nueva_tarifa = a_centavos(tarifa.value or "")
                    pagado = a_centavos(campo.value or "")
                except ValueError:
                    avisar(self.page, "Monto no válido (usa números, p. ej. 350 o 350.50).", error=True)
                    return
                if nueva_tarifa == l.tarifa and pagado == l.pagado_campo:
                    return
                try:
                    self.app.pagos.registrar_en_campo(l.asignacion_id, pagado, nueva_tarifa)
                except ErrorValidacion as e:
                    avisar(self.page, e.mensaje, error=True)
                    return
                self.refrescar()

            def completo(_, l=l):
                self.app.pagos.registrar_en_campo(l.asignacion_id, l.tarifa)
                self.refrescar()

            tarifa.on_blur = guardar
            tarifa.on_submit = guardar
            campo.on_blur = guardar
            campo.on_submit = guardar
            acciones = []
            if editable and l.saldo:
                acciones.append(ft.IconButton(ft.Icons.DONE, tooltip="Se le pagó completo en campo", on_click=completo))
            filas.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(f"{fecha_corta(p.fecha)} {p.hora:%H:%M}")),
                ft.DataCell(ft.Text(f"{p.local.nombre} vs {p.visitante.nombre}", weight=ft.FontWeight.W_500)),
                ft.DataCell(ft.Text(POSICIONES[l.posicion])),
                ft.DataCell(ft.Text(l.arbitro.nombre)),
                ft.DataCell(tarifa),
                ft.DataCell(campo),
                ft.DataCell(ft.Text(formatear_monto(l.saldo), weight=ft.FontWeight.BOLD)),
                ft.DataCell(etiqueta_pago(l)),
                ft.DataCell(ft.Row(acciones, spacing=0)),
            ]))
        return ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c)) for c in
                     ("Fecha", "Partido", "Posición", "Árbitro", "Tarifa", "Pagado en campo", "Saldo", "Estado", "")],
            rows=filas, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST, column_spacing=16,
        )

    def _todo_completo(self, ids: list[int]) -> None:
        def aplicar():
            n = self.app.pagos.todo_pagado_en_campo(ids)
            avisar(self.page, f"{n} pago(s) marcados como pagados completos en campo.")
            self.refrescar()

        confirmar(self.page, "Todo pagado en campo",
                  "Se registrará que a todos los árbitros de esta jornada se les pagó su tarifa completa en el campo.",
                  aplicar, "Sí, todo pagado")
