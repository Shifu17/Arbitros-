"""Cobro del arbitraje a los equipos (pestaña de Pagos) y su recibo desglosado."""

import logging
from datetime import date
from pathlib import Path

import flet as ft

from arbitros.db.models import FORMAS_PAGO, POSICIONES
from arbitros.services.cobros import LineaCobro, ReciboEquipo
from arbitros.services.dinero import a_centavos, formatear_monto, monto_editable
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import etiqueta_jornada
from arbitros.services.recibo_imagen import generar_pdf, generar_png
from arbitros.ui import filtros, tema
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    CampoFecha,
    avisar,
    confirmar,
    estado_vacio,
    fecha_corta,
    mostrar_errores,
    rango_fechas,
    tarjeta,
)

log = logging.getLogger(__name__)

SIN_FORMA = "ninguna"


def etiqueta_cobro(l: LineaCobro) -> ft.Control:
    if l.saldo == 0:
        texto, fondo, color = "Pagado", tema.EXITO_FONDO, tema.EXITO_TEXTO
    elif l.pagado:
        texto, fondo, color = "Pago parcial", tema.AVISO_FONDO, tema.AVISO_TEXTO
    elif not l.jugado:
        texto, fondo, color = "Por jugarse", ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT
    else:
        texto, fondo, color = "Debe", tema.PELIGRO_FONDO, tema.PELIGRO_TEXTO
    return ft.Container(ft.Text(texto, size=12, weight=ft.FontWeight.W_500, color=color), bgcolor=fondo,
                        border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=4))


def dialogo_recibo(app, recibo: ReciboEquipo) -> None:
    """Vista previa del recibo con opciones para copiarlo o guardarlo (PNG o PDF)."""
    page = app.page
    png = generar_png(recibo)
    nombre_base = f"recibo_{recibo.equipo.nombre}_{recibo.periodo}".replace(" ", "_").replace("/", "-")

    async def copiar_texto(_):
        await app.portapapeles.set(app.cobros.recibo_texto(recibo))
        avisar(page, "Recibo copiado. Pégalo en WhatsApp.")

    async def copiar_imagen(_):
        try:
            await app.portapapeles.set_image(png)
        except Exception:
            log.exception("No se pudo copiar la imagen del recibo")
            avisar(page, "No se pudo copiar la imagen; usa «Guardar…».", error=True)
            return
        avisar(page, "Imagen copiada. Pégala en WhatsApp Web o de escritorio.")

    async def guardar(extension: str):
        ruta = await app.selector_archivos.save_file(
            dialog_title="Guardar recibo", file_name=f"{nombre_base}.{extension}",
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=[extension])
        if not ruta:
            return
        destino = Path(ruta) if ruta.lower().endswith(f".{extension}") else Path(f"{ruta}.{extension}")
        try:
            destino.write_bytes(png if extension == "png" else generar_pdf(recibo))
        except PermissionError:
            avisar(page, "No se pudo guardar: ¿el archivo está abierto? Ciérralo e inténtalo de nuevo.", error=True)
            return
        avisar(page, f"Recibo guardado en {destino}")

    async def guardar_png(_):
        await guardar("png")

    async def guardar_pdf(_):
        await guardar("pdf")

    page.show_dialog(ft.AlertDialog(
        title=ft.Text(f"Recibo · {recibo.equipo.nombre}"),
        content=ft.Column(
            [ft.Text(f"{recibo.liga.nombre} · {recibo.periodo} · total {formatear_monto(recibo.total)} · "
                     f"pagado {formatear_monto(recibo.pagado)} · saldo {formatear_monto(recibo.saldo)}",
                     weight=ft.FontWeight.W_600),
             ft.Image(src=png, fit=ft.BoxFit.FIT_WIDTH, border_radius=12)],
            scroll=ft.ScrollMode.AUTO, height=520, width=ANCHO_DIALOGO + 100, spacing=12,
        ),
        actions=[
            ft.TextButton("Copiar texto", icon=ft.Icons.CONTENT_COPY, on_click=copiar_texto),
            ft.TextButton("Copiar imagen", icon=ft.Icons.IMAGE, on_click=copiar_imagen),
            ft.TextButton("Guardar PDF…", icon=ft.Icons.PICTURE_AS_PDF, on_click=guardar_pdf),
            ft.TextButton("Guardar imagen…", icon=ft.Icons.SAVE_ALT, on_click=guardar_png),
            ft.TextButton("Cerrar", on_click=lambda _: page.pop_dialog()),
        ],
    ))


class PanelEquipos:
    """Captura, por jornada, de lo que pagó cada equipo del arbitraje."""

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
            lineas = self.app.cobros.lineas(jornada_id=self.jornada_id)
            if not lineas:
                self.contenido.controls = [estado_vacio(
                    ft.Icons.GROUPS, "No hay arbitrajes que cobrar en esta jornada",
                    "Revisa que la liga tenga tarifas y que haya partidos programados.")]
            else:
                pendientes = [l for l in lineas if l.saldo]
                ayuda = ft.Text("Cada equipo paga la mitad del arbitraje de su partido. Si un equipo pagó distinto "
                                "(p. ej. todo el arbitraje), corrige su cuota en «Registrar pago…».",
                                color=ft.Colors.ON_SURFACE_VARIANT)
                acciones = []
                if self.app.es_admin and pendientes:
                    acciones.append(ft.OutlinedButton(
                        "Todos pagaron completo", icon=ft.Icons.DONE_ALL,
                        on_click=lambda _: self._todos_completo([l.clave for l in pendientes])))
                resumen = ft.Text(
                    f"Arbitrajes {formatear_monto(sum(l.cuota for l in lineas))} · pagado "
                    f"{formatear_monto(sum(l.pagado for l in lineas))} · deben "
                    f"{formatear_monto(sum(l.saldo for l in lineas))}",
                    weight=ft.FontWeight.W_600)
                self.contenido.controls = [
                    ayuda, ft.Row([resumen, *acciones], wrap=True, spacing=16),
                    tarjeta(ft.Row([self._tabla(lineas)], scroll=ft.ScrollMode.AUTO)),
                ]
        if actualizar:
            self.page.update()

    def _tabla(self, lineas: list[LineaCobro]) -> ft.Control:
        filas = []
        for l in lineas:
            p = l.partido
            acciones = [ft.IconButton(ft.Icons.RECEIPT_LONG, tooltip="Recibo de esta jornada",
                                      on_click=lambda _, l=l: self._recibo(l))]
            if self.app.es_admin:
                if l.saldo:
                    acciones.insert(0, ft.IconButton(ft.Icons.DONE, tooltip="Pagó completo",
                                                     on_click=lambda _, l=l: self._completo(l)))
                acciones.insert(1 if l.saldo else 0, ft.IconButton(
                    ft.Icons.EDIT, tooltip="Registrar pago…", on_click=lambda _, l=l: self._dialogo_registrar(l)))
                if l.pagado or l.cuota_fija:
                    acciones.append(ft.IconButton(ft.Icons.UNDO, tooltip="Deshacer pago",
                                                  on_click=lambda _, l=l: self._deshacer(l)))
            filas.append(ft.DataRow(cells=[
                ft.DataCell(ft.Text(f"{fecha_corta(p.fecha)} {p.hora:%H:%M}")),
                ft.DataCell(ft.Column(
                    [ft.Text(l.equipo.nombre, weight=ft.FontWeight.W_500),
                     ft.Text(f"vs {l.rival.nombre} · {'Local' if l.es_local else 'Visitante'}", size=12,
                             color=ft.Colors.ON_SURFACE_VARIANT)],
                    spacing=0, alignment=ft.MainAxisAlignment.CENTER)),
                ft.DataCell(ft.Text(formatear_monto(l.cuota),
                                    tooltip=" · ".join(f"{POSICIONES[pos]} {formatear_monto(m)}"
                                                       for pos, m in l.desglose) or None)),
                ft.DataCell(ft.Text(formatear_monto(l.pagado))),
                ft.DataCell(ft.Text(formatear_monto(l.saldo), weight=ft.FontWeight.BOLD)),
                ft.DataCell(etiqueta_cobro(l)),
                ft.DataCell(ft.Row(acciones, spacing=0, tight=True)),
            ]))
        return ft.DataTable(
            columns=[ft.DataColumn(ft.Text(c), numeric=n) for c, n in (
                ("Fecha", False), ("Equipo", False), ("Cuota", True), ("Pagado", True), ("Debe", True),
                ("Estado", False), ("", False))],
            rows=filas, heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST, column_spacing=16, data_row_max_height=60,
        )

    def _recibo(self, l: LineaCobro) -> None:
        dialogo_recibo(self.app, self.app.cobros.recibo(l.equipo.id, jornada_id=self.jornada_id))

    def _completo(self, l: LineaCobro) -> None:
        self.app.cobros.pago_completo([l.clave])
        self.refrescar()

    def _todos_completo(self, claves: list[tuple[int, int]]) -> None:
        def aplicar():
            n = self.app.cobros.pago_completo(claves)
            avisar(self.page, f"{n} equipo(s) marcados como pagados.")
            self.refrescar()

        confirmar(self.page, "Todos pagaron completo",
                  "Se registrará que todos los equipos de esta jornada pagaron su arbitraje completo hoy.",
                  aplicar, "Sí, todos pagaron")

    def _deshacer(self, l: LineaCobro) -> None:
        def aplicar():
            self.app.cobros.deshacer(l.partido.id, l.equipo.id)
            avisar(self.page, f"Pago de {l.equipo.nombre} deshecho.")
            self.refrescar()

        confirmar(self.page, "Deshacer pago",
                  f"Se borrará lo registrado de {l.equipo.nombre} en este partido y volverá a deber su cuota normal.",
                  aplicar, "Deshacer")

    def _dialogo_registrar(self, l: LineaCobro) -> None:
        cuota = ft.TextField(label="Cuota del equipo", value=monto_editable(l.cuota), prefix=ft.Text("$ "),
                             input_filter=filtros.MONTO, width=200, text_align=ft.TextAlign.RIGHT)
        pagado = ft.TextField(label="Pagó", value=monto_editable(l.pagado or l.cuota), prefix=ft.Text("$ "),
                              input_filter=filtros.MONTO, width=200, text_align=ft.TextAlign.RIGHT)
        fecha = CampoFecha(self.page, "Fecha del pago", l.fecha_pago or date.today(), width=200)
        forma = ft.Dropdown(
            label="Forma de pago", value=l.forma_pago or SIN_FORMA, width=260,
            options=[ft.DropdownOption(key=SIN_FORMA, text="Sin especificar")]
            + [ft.DropdownOption(key=k, text=v) for k, v in FORMAS_PAGO.items()],
        )
        nota = ft.TextField(label="Nota (opcional)", value=l.nota or "", hint_text="Ej.: pagó el delegado")
        desglose = " · ".join(f"{POSICIONES[pos]} {formatear_monto(m)}" for pos, m in l.desglose) or "Sin tarifas"
        p = l.partido

        def guardar(_):
            try:
                nueva_cuota = a_centavos(cuota.value or "")
                monto = a_centavos(pagado.value or "")
            except ValueError:
                avisar(self.page, "Monto no válido (usa números, p. ej. 350 o 350.50).", error=True)
                return
            if not fecha.validar():
                self.page.update()
                return
            try:
                self.app.cobros.registrar(p.id, l.equipo.id, monto, nueva_cuota, fecha.valor,
                                          None if forma.value == SIN_FORMA else forma.value, nota.value or "")
            except ErrorValidacion as e:
                mostrar_errores({"pagado": pagado}, e.campos)
                avisar(self.page, e.mensaje, error=True)
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, f"Pago de {l.equipo.nombre} registrado.")
            self.refrescar()

        self.page.show_dialog(ft.AlertDialog(
            modal=True,
            title=ft.Text(f"Pago de {l.equipo.nombre}"),
            content=ft.Column(
                [ft.Text(f"{fecha_corta(p.fecha)} {p.hora:%H:%M} · vs {l.rival.nombre} · {l.jornada}",
                         weight=ft.FontWeight.W_500),
                 ft.Text(f"Le toca: {desglose}", color=ft.Colors.ON_SURFACE_VARIANT),
                 ft.Row([cuota, pagado], spacing=12, wrap=True),
                 ft.Row([fecha.campo, forma], spacing=12, wrap=True),
                 nota],
                tight=True, spacing=12, width=ANCHO_DIALOGO + 40,
            ),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
            ],
        ))
