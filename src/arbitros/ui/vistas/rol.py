"""Rol para WhatsApp: vista previa en texto o imagen, copiar, guardar, mensajes por árbitro y cambios."""

import logging
import re
from pathlib import Path

import flet as ft

from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import etiqueta_jornada
from arbitros.services.rol import AGRUPAR_ARBITRO, AGRUPAR_CAMPO, AGRUPAR_HORA, OpcionesRol
from arbitros.services.rol_imagen import generar_png
from arbitros.ui.comunes import ANCHO_DIALOGO, avisar, encabezado, estado_vacio, fecha_legible, rango_fechas, tarjeta
from arbitros.ui import tema

log = logging.getLogger(__name__)

CLAVE_NOTA = "rol_nota"
TODAS = "todas"
ANCHO_OPCIONES = 320


def whatsapp_a_markdown(texto: str) -> str:
    """Convierte el formato de WhatsApp (*negrita*, _cursiva_, ~tachado~) a Markdown para la vista previa."""
    lineas = []
    for linea in texto.split("\n"):
        linea = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"**\1**", linea)
        linea = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"*\1*", linea)
        linea = re.sub(r"(?<!\w)~([^~\n]+)~(?!\w)", r"~~\1~~", linea)
        lineas.append(linea + "  " if linea else "")  # dos espacios = salto de línea en Markdown
    return "\n".join(lineas)


def sin_formato(texto: str) -> str:
    return re.sub(r"[*_~]", "", texto)


def construir(app, shell) -> ft.Control:
    return VistaRol(app, shell).construir()


class VistaRol:
    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.page = app.page
        self.opciones: OpcionesRol = app.seleccion.get("rol_opciones") or OpcionesRol(
            nota=app.config.obtener(CLAVE_NOTA, "") or "")
        app.seleccion["rol_opciones"] = self.opciones
        self.modo = "texto"
        self.texto_actual = ""
        self.liga = None
        self.jornada_id: int | None = None
        self.selector_jornada = ft.Dropdown(label="Jornada", width=320, on_select=self._cambiar_jornada)
        self.selector_categoria = ft.Dropdown(label="Categoría", width=ANCHO_OPCIONES, on_select=self._cambiar_categoria)
        self.estado = ft.Column(spacing=8)
        self.vista_previa = ft.Container(expand=True)
        self.cuerpo = ft.Container(expand=True)

    def construir(self) -> ft.Control:
        ligas = self.app.ligas.listar()
        if not ligas:
            self.cuerpo.content = ft.Column(
                [encabezado("Rol para WhatsApp"),
                 estado_vacio(ft.Icons.SEND, "Primero registra una liga y carga una jornada")],
                expand=True,
            )
            return self.cuerpo
        ids = [r.liga.id for r in ligas]
        liga_id = self.app.seleccion.get("liga_id") if self.app.seleccion.get("liga_id") in ids else ids[0]
        selector_liga = ft.Dropdown(
            label="Liga o torneo", value=str(liga_id), width=320,
            options=[ft.DropdownOption(key=str(r.liga.id), text=r.liga.nombre) for r in ligas],
            on_select=lambda e: self._cambiar_liga(int(e.control.value)),
        )
        self._cambiar_liga(liga_id, actualizar=False)
        self.cuerpo.content = ft.Column(
            [
                encabezado("Rol para WhatsApp", "Revisa la vista previa, cópiala y pégala en tu grupo."),
                ft.Row([selector_liga, self.selector_jornada], spacing=16, wrap=True),
                self.estado,
                ft.Row(
                    [ft.Container(self._panel_opciones(), width=ANCHO_OPCIONES), self.vista_previa],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=24,
                ),
            ],
            spacing=16,
            expand=True,
        )
        return self.cuerpo

    # --- Selección -----------------------------------------------------------

    def _cambiar_liga(self, liga_id: int, actualizar: bool = True) -> None:
        if self.app.seleccion.get("liga_id") != liga_id:
            self.app.seleccion["jornada_id"] = None
        self.app.seleccion["liga_id"] = liga_id
        self.liga = self.app.ligas.obtener(liga_id)
        jornadas = self.app.jornadas.listar(liga_id)
        self.selector_jornada.label = "Día" if self.liga.es_torneo else "Jornada"
        self.selector_jornada.options = [
            ft.DropdownOption(key=str(r.jornada.id),
                              text=f"{etiqueta_jornada(self.liga, r.jornada)} · {rango_fechas(r.jornada.fecha_inicio, r.jornada.fecha_fin)}")
            for r in jornadas
        ]
        ids = [r.jornada.id for r in jornadas]
        actual = self.app.seleccion.get("jornada_id")
        self.jornada_id = actual if actual in ids else (ids[-1] if ids else None)
        self.app.seleccion["jornada_id"] = self.jornada_id
        self.selector_jornada.value = str(self.jornada_id) if self.jornada_id else None
        categorias = self.app.ligas.categorias.listar(liga_id)
        self.selector_categoria.options = [ft.DropdownOption(key=TODAS, text="Todas")] + [
            ft.DropdownOption(key=str(c.id), text=c.nombre) for c in categorias]
        self.selector_categoria.visible = bool(categorias)
        if self.opciones.categoria_id not in {c.id for c in categorias}:
            self.opciones.categoria_id = None
        self.selector_categoria.value = str(self.opciones.categoria_id) if self.opciones.categoria_id else TODAS
        self.refrescar(actualizar)

    def _cambiar_jornada(self, e) -> None:
        self.jornada_id = int(e.control.value)
        self.app.seleccion["jornada_id"] = self.jornada_id
        self.refrescar()

    def _cambiar_categoria(self, e) -> None:
        self.opciones.categoria_id = None if e.control.value == TODAS else int(e.control.value)
        self.refrescar()

    # --- Opciones -------------------------------------------------------------

    def _panel_opciones(self) -> ft.Control:
        agrupar = ft.SegmentedButton(
            selected=[self.opciones.agrupar],
            segments=[
                ft.Segment(value=AGRUPAR_CAMPO, label=ft.Text("Campo")),
                ft.Segment(value=AGRUPAR_HORA, label=ft.Text("Hora")),
                ft.Segment(value=AGRUPAR_ARBITRO, label=ft.Text("Árbitro")),
            ],
        )

        def cambiar_agrupar(e):
            self.opciones.agrupar = e.control.selected[0]
            self.refrescar()

        agrupar.on_change = cambiar_agrupar

        def interruptor(etiqueta_, atributo):
            def cambiar(e):
                setattr(self.opciones, atributo, e.control.value)
                self.refrescar()

            return ft.Switch(label=etiqueta_, value=getattr(self.opciones, atributo), on_change=cambiar)

        nota = ft.TextField(
            label="Nota al final (opcional)",
            value=self.opciones.nota,
            hint_text="Ej.: Llegar 20 minutos antes con uniforme completo.",
            multiline=True,
            min_lines=2,
            max_lines=5,
        )

        def guardar_nota(_):
            self.opciones.nota = nota.value or ""
            self.app.config.guardar(CLAVE_NOTA, self.opciones.nota)
            self.refrescar()

        nota.on_blur = guardar_nota
        botones = [
            ft.FilledButton("Copiar texto", icon=ft.Icons.CONTENT_COPY, on_click=self._copiar_texto, width=ANCHO_OPCIONES),
            ft.OutlinedButton("Copiar imagen", icon=ft.Icons.IMAGE, on_click=self._copiar_imagen, width=ANCHO_OPCIONES),
            ft.OutlinedButton("Guardar imagen…", icon=ft.Icons.SAVE_ALT, on_click=self._guardar_imagen, width=ANCHO_OPCIONES),
            ft.OutlinedButton("Enviar a cada árbitro…", icon=ft.Icons.CHAT, on_click=lambda _: self._dialogo_individual(),
                              width=ANCHO_OPCIONES),
        ]
        if self.app.es_admin:
            botones.append(ft.TextButton("Marcar como enviado", icon=ft.Icons.MARK_EMAIL_READ,
                                         on_click=lambda _: self._publicar(), width=ANCHO_OPCIONES))
        return ft.Column(
            [
                ft.Text("Organizar por", weight=ft.FontWeight.W_500),
                agrupar,
                self.selector_categoria,
                interruptor("Usar apodos de los árbitros", "usar_apodos"),
                interruptor("Incluir cancelados y suspendidos", "incluir_cancelados"),
                nota,
                ft.Divider(),
                *botones,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
        )

    # --- Vista previa ---------------------------------------------------------

    def refrescar(self, actualizar: bool = True) -> None:
        if self.jornada_id is None:
            unidad = "días" if self.liga and self.liga.es_torneo else "jornadas"
            self.estado.controls = []
            self.vista_previa.content = estado_vacio(
                ft.Icons.CALENDAR_MONTH, f"Esta liga aún no tiene {unidad}",
                "Créalas en «Jornadas y partidos».")
            if actualizar:
                self.page.update()
            return
        try:
            self.texto_actual = self.app.rol.texto(self.jornada_id, self.opciones)
            datos = self.app.rol.datos(self.jornada_id, self.opciones)
        except ErrorValidacion as e:
            avisar(self.page, e.mensaje, error=True)
            return
        self.estado.controls = self._avisos_estado(datos)
        selector_modo = ft.SegmentedButton(
            selected=[self.modo],
            segments=[
                ft.Segment(value="texto", label=ft.Text("Texto"), icon=ft.Icon(ft.Icons.NOTES)),
                ft.Segment(value="imagen", label=ft.Text("Imagen"), icon=ft.Icon(ft.Icons.IMAGE)),
            ],
            on_change=self._cambiar_modo,
        )
        if self.modo == "imagen":
            contenido = ft.Image(src=self._png(), fit=ft.BoxFit.FIT_WIDTH, border_radius=12)
            pie = "Así se verá la imagen. «Copiar imagen» y pégala en WhatsApp Web o de escritorio."
        else:
            contenido = ft.Container(
                ft.Markdown(whatsapp_a_markdown(self.texto_actual), selectable=True,
                            extension_set=ft.MarkdownExtensionSet.GITHUB_FLAVORED),
                bgcolor=ft.Colors.SURFACE_CONTAINER_LOW,
                border_radius=12,
                padding=20,
            )
            pie = "Vista aproximada. Al pegarlo en WhatsApp, los textos entre * se ven en negritas."
        self.vista_previa.content = ft.Column(
            [
                ft.Row([selector_modo, ft.Text(pie, size=12, color=ft.Colors.ON_SURFACE_VARIANT, expand=True)],
                       spacing=16),
                ft.Container(ft.Column([contenido], scroll=ft.ScrollMode.AUTO, expand=True), expand=True, width=640),
            ],
            spacing=12,
            expand=True,
        )
        if actualizar:
            self.page.update()

    def _cambiar_modo(self, e) -> None:
        self.modo = e.control.selected[0]
        self.refrescar()

    def _png(self) -> bytes:
        opciones = self.opciones
        if opciones.agrupar == AGRUPAR_ARBITRO:
            # La imagen se organiza por campo aunque el texto esté por árbitro
            opciones = OpcionesRol(AGRUPAR_CAMPO, opciones.categoria_id, opciones.usar_apodos,
                                   opciones.incluir_cancelados, opciones.nota)
        return generar_png(self.app.rol.datos(self.jornada_id, opciones), opciones)

    def _avisos_estado(self, datos) -> list[ft.Control]:
        controles = []
        if datos.faltantes:
            controles.append(self._aviso(
                ft.Icons.PERSON_SEARCH, datos.texto_faltantes, tema.PELIGRO_FONDO, tema.PELIGRO_TEXTO,
                ft.TextButton("Ir a asignar", on_click=lambda _: self.shell.ir_a("jornadas"))))
        cambios = self.app.rol.cambios(self.jornada_id)
        jornada = self.app.jornadas.obtener(self.jornada_id)
        if cambios is None:
            controles.append(self._aviso(
                ft.Icons.INFO_OUTLINE,
                "Cuando envíes el rol, pulsa «Marcar como enviado»: si después cambias algo, la app te dirá "
                "qué cambió y te armará un mensaje solo con los cambios.",
                ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT))
        elif not cambios:
            controles.append(self._aviso(
                ft.Icons.MARK_EMAIL_READ, f"Enviado el {fecha_legible(jornada.rol_publicado_en)}. Sin cambios desde entonces.",
                tema.EXITO_FONDO, tema.EXITO_TEXTO))
        else:
            detalle = ft.Column([ft.Text(sin_formato(c), size=13) for c in cambios], spacing=2)
            controles.append(tarjeta(ft.Column(
                [
                    ft.Row([ft.Icon(ft.Icons.SYNC_PROBLEM, color=tema.AVISO_ICONO),
                            ft.Text(f"{len(cambios)} cambio(s) desde que enviaste el rol "
                                    f"({fecha_legible(jornada.rol_publicado_en)})", weight=ft.FontWeight.W_600)]),
                    detalle,
                    ft.Row([
                        ft.FilledButton("Copiar mensaje de cambios", icon=ft.Icons.CONTENT_COPY,
                                        on_click=self._copiar_cambios),
                        ft.TextButton("Marcar como enviado", on_click=lambda _: self._publicar(),
                                      visible=self.app.es_admin),
                    ], wrap=True),
                ],
                spacing=8,
            )))
        return controles

    @staticmethod
    def _aviso(icono, texto: str, fondo, color, accion: ft.Control | None = None) -> ft.Control:
        return ft.Container(
            ft.Row([ft.Icon(icono, color=color), ft.Text(texto, color=color, expand=True), accion or ft.Container()],
                   vertical_alignment=ft.CrossAxisAlignment.CENTER),
            bgcolor=fondo, border_radius=8, padding=ft.Padding.symmetric(horizontal=16, vertical=8),
        )

    # --- Acciones -------------------------------------------------------------

    async def _copiar_texto(self, _) -> None:
        if not self.texto_actual:
            return
        await self.app.portapapeles.set(self.texto_actual)
        avisar(self.page, "Rol copiado. Pégalo en WhatsApp.")

    async def _copiar_cambios(self, _) -> None:
        await self.app.portapapeles.set(self.app.rol.texto_cambios(self.jornada_id))
        avisar(self.page, "Mensaje de cambios copiado.")

    async def _copiar_imagen(self, _) -> None:
        if self.jornada_id is None:
            return
        try:
            await self.app.portapapeles.set_image(self._png())
        except Exception:
            log.exception("No se pudo copiar la imagen")
            avisar(self.page, "No se pudo copiar la imagen; usa «Guardar imagen…».", error=True)
            return
        avisar(self.page, "Imagen copiada. Pégala en WhatsApp Web o de escritorio.")

    async def _guardar_imagen(self, _) -> None:
        if self.jornada_id is None:
            return
        jornada = self.app.jornadas.obtener(self.jornada_id)
        nombre = f"rol_{self.liga.nombre}_{etiqueta_jornada(self.liga, jornada)}.png".replace(" ", "_")
        ruta = await self.app.selector_archivos.save_file(
            dialog_title="Guardar imagen del rol", file_name=nombre,
            file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=["png"])
        if not ruta:
            return
        destino = Path(ruta) if ruta.lower().endswith(".png") else Path(ruta + ".png")
        destino.write_bytes(self._png())
        avisar(self.page, f"Imagen guardada en {destino}")

    def _publicar(self) -> None:
        if self.jornada_id is None:
            return
        self.app.rol.publicar(self.jornada_id)
        avisar(self.page, "Rol marcado como enviado. Te avisaré si algo cambia.")
        self.refrescar()

    def _dialogo_individual(self) -> None:
        if self.jornada_id is None:
            return
        mensajes = self.app.rol.mensajes_individuales(self.jornada_id)

        def fila(arbitro, texto, enlace) -> ft.Control:
            enviado = ft.Icon(ft.Icons.CHECK_CIRCLE, color=tema.EXITO_ICONO, visible=False)

            def marcar(_):
                enviado.visible = True
                self.page.update()

            async def copiar(_):
                await self.app.portapapeles.set(texto)
                avisar(self.page, f"Mensaje para {arbitro.nombre} copiado.")

            partidos = texto.count("🏟️")
            return ft.ListTile(
                leading=enviado,
                title=ft.Text(arbitro.nombre, weight=ft.FontWeight.W_500),
                subtitle=ft.Text(f"{partidos} partido{'s' if partidos != 1 else ''}"),
                trailing=ft.Row(
                    [
                        ft.IconButton(ft.Icons.CONTENT_COPY, tooltip="Copiar su mensaje", on_click=copiar),
                        ft.FilledButton("Abrir WhatsApp", icon=ft.Icons.CHAT, url=enlace, on_click=marcar),
                    ],
                    tight=True,
                ),
            )

        contenido = [fila(*m) for m in mensajes] or [
            ft.Text("Todavía no hay árbitros asignados en esta jornada.", color=ft.Colors.ON_SURFACE_VARIANT)]
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Enviar a cada árbitro"),
                content=ft.Column(
                    [ft.Text("Cada botón abre WhatsApp con el mensaje personal del árbitro ya escrito; "
                             "solo pulsa enviar."),
                     ft.ListView(contenido, height=420, spacing=2)],
                    tight=True,
                    spacing=12,
                    width=ANCHO_DIALOGO + 160,
                ),
                actions=[ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())],
            )
        )
