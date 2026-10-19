"""Jornadas (o días de torneo) de una liga y sus partidos."""

import flet as ft

from arbitros.db.models import (
    ESTADO_CANCELADO,
    ESTADO_JUGADO,
    ESTADO_PROGRAMADO,
    ESTADO_SUSPENDIDO,
    ESTADOS_PARTIDO,
    ESTADOS_SIN_JUEGO,
    POSICIONES,
    POSICIONES_CORTAS,
    Liga,
    Partido,
)
from arbitros.services.errores import AvisosPendientes, ErrorValidacion
from arbitros.services.jornadas import DatosPartido, ResumenJornada, etiqueta_jornada
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    CampoFecha,
    CampoHora,
    avisar,
    avisos_panel,
    confirmar,
    estado_vacio,
    fecha_corta,
    mostrar_avisos,
    mostrar_errores,
    rango_fechas,
    tarjeta,
)
from arbitros.ui.vistas.ligas import posiciones_marcadas, selector_posiciones

ANCHO_LISTA_JORNADAS = 290
MOTIVOS_SUGERIDOS = ["Lluvia", "Cancha en mal estado", "Equipo no se presentó", "A petición de la liga"]


def etiqueta_estado(estado: str) -> ft.Control:
    colores = {
        ESTADO_PROGRAMADO: (ft.Colors.PRIMARY_CONTAINER, ft.Colors.ON_PRIMARY_CONTAINER),
        ESTADO_JUGADO: (ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT),
        ESTADO_SUSPENDIDO: (ft.Colors.TERTIARY_CONTAINER, ft.Colors.ON_TERTIARY_CONTAINER),
        ESTADO_CANCELADO: (ft.Colors.ERROR_CONTAINER, ft.Colors.ON_ERROR_CONTAINER),
    }
    fondo, texto = colores.get(estado, colores[ESTADO_JUGADO])
    return ft.Container(
        ft.Text(ESTADOS_PARTIDO.get(estado, estado), size=12, weight=ft.FontWeight.W_500, color=texto),
        bgcolor=fondo,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )


def describir_partido(p: Partido) -> str:
    campo = p.campo.nombre if p.campo else "sin campo"
    return f"{fecha_corta(p.fecha)} {p.hora:%H:%M} · {campo} · {p.local.nombre} vs {p.visitante.nombre}"


def construir(app, shell) -> ft.Control:
    return VistaJornadas(app, shell).construir()


class VistaJornadas:
    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.page = app.page
        self.liga: Liga | None = None
        self.jornadas: list[ResumenJornada] = []
        self.cuerpo = ft.Container(expand=True)
        self.lista_jornadas = ft.Column(spacing=2, scroll=ft.ScrollMode.AUTO, expand=True)
        self.detalle = ft.Container(expand=True)

    def construir(self) -> ft.Control:
        ligas = self.app.ligas.listar()
        if not ligas:
            accion = ft.FilledButton("Ir a Ligas y torneos", icon=ft.Icons.EMOJI_EVENTS, on_click=lambda _: self.shell.ir_a("ligas"))
            self.cuerpo.content = ft.Column(
                [
                    ft.Text("Jornadas y partidos", size=26, weight=ft.FontWeight.BOLD),
                    estado_vacio(ft.Icons.CALENDAR_MONTH, "Primero registra una liga o torneo", "Con sus equipos y campos."),
                    ft.Row([accion], alignment=ft.MainAxisAlignment.CENTER),
                ],
                expand=True,
            )
            return self.cuerpo

        ids = [r.liga.id for r in ligas]
        liga_id = self.app.seleccion.get("liga_id")
        if liga_id not in ids:
            liga_id = ids[0]
        selector_liga = ft.Dropdown(
            label="Liga o torneo",
            value=str(liga_id),
            options=[ft.DropdownOption(key=str(r.liga.id), text=r.liga.nombre) for r in ligas],
            on_select=lambda e: self.cambiar_liga(int(e.control.value)),
            width=360,
        )
        self.titulo_lista = ft.Text(weight=ft.FontWeight.W_600, size=16, expand=True)
        self.boton_nueva = ft.IconButton(
            ft.Icons.ADD, tooltip="Nueva jornada", on_click=lambda _: self.dialogo_jornada(), visible=self.app.es_admin
        )
        columna_izquierda = ft.Container(
            ft.Column([ft.Row([self.titulo_lista, self.boton_nueva]), self.lista_jornadas], expand=True),
            width=ANCHO_LISTA_JORNADAS,
        )
        self.cambiar_liga(liga_id, actualizar=False)
        self.cuerpo.content = ft.Column(
            [
                ft.Row(
                    [ft.Text("Jornadas y partidos", size=26, weight=ft.FontWeight.BOLD, expand=True), selector_liga],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                ),
                ft.Row(
                    [columna_izquierda, ft.VerticalDivider(width=1), self.detalle],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ],
            spacing=16,
            expand=True,
        )
        return self.cuerpo

    # --- Liga y lista de jornadas ----------------------------------------

    def cambiar_liga(self, liga_id: int, actualizar: bool = True) -> None:
        if self.app.seleccion.get("liga_id") != liga_id:
            self.app.seleccion["jornada_id"] = None
        self.app.seleccion["liga_id"] = liga_id
        self.liga = self.app.ligas.obtener(liga_id)
        self.titulo_lista.value = "Días del torneo" if self.liga.es_torneo else "Jornadas"
        self.boton_nueva.tooltip = "Agregar día" if self.liga.es_torneo else "Nueva jornada"
        self.refrescar(actualizar=actualizar)

    def refrescar(self, actualizar: bool = True) -> None:
        self.jornadas = self.app.jornadas.listar(self.liga.id)
        ids = [r.jornada.id for r in self.jornadas]
        seleccionada = self.app.seleccion.get("jornada_id")
        if seleccionada not in ids:
            # Por defecto, la última jornada (la más reciente)
            seleccionada = ids[-1] if ids else None
        self.app.seleccion["jornada_id"] = seleccionada
        self.lista_jornadas.controls = [self._item_jornada(r, r.jornada.id == seleccionada) for r in self.jornadas]
        if not self.jornadas:
            unidad = "días" if self.liga.es_torneo else "jornadas"
            self.lista_jornadas.controls = [ft.Text(f"Sin {unidad} todavía.", color=ft.Colors.ON_SURFACE_VARIANT)]
        self._mostrar_detalle(seleccionada)
        if actualizar:
            self.page.update()

    def _item_jornada(self, r: ResumenJornada, seleccionada: bool) -> ft.Control:
        j = r.jornada
        return ft.ListTile(
            title=ft.Text(etiqueta_jornada(self.liga, j), weight=ft.FontWeight.W_500),
            subtitle=ft.Text(f"{rango_fechas(j.fecha_inicio, j.fecha_fin)} · {r.partidos} partidos"),
            selected=seleccionada,
            selected_tile_color=ft.Colors.PRIMARY_CONTAINER,
            dense=True,
            on_click=lambda _, i=j.id: self.seleccionar(i),
        )

    def seleccionar(self, jornada_id: int) -> None:
        self.app.seleccion["jornada_id"] = jornada_id
        self.refrescar()

    # --- Detalle de jornada ----------------------------------------------

    def _mostrar_detalle(self, jornada_id: int | None) -> None:
        if jornada_id is None:
            unidad = "el primer día" if self.liga.es_torneo else "la primera jornada"
            boton = ft.FilledButton(
                "Agregar día" if self.liga.es_torneo else "Nueva jornada",
                icon=ft.Icons.ADD,
                on_click=lambda _: self.dialogo_jornada(),
                visible=self.app.es_admin,
            )
            self.detalle.content = ft.Column(
                [estado_vacio(ft.Icons.CALENDAR_MONTH, f"Crea {unidad}"), ft.Row([boton], alignment=ft.MainAxisAlignment.CENTER)],
                expand=True,
            )
            return
        resumen = next(r for r in self.jornadas if r.jornada.id == jornada_id)
        j = resumen.jornada
        partidos = self.app.jornadas.listar_partidos(j.id)
        acciones = []
        if self.app.es_admin:
            acciones = [
                ft.FilledButton("Agregar partido", icon=ft.Icons.ADD, on_click=lambda _: self.dialogo_partido(j.id)),
                ft.OutlinedButton(
                    "Cancelar partidos…",
                    icon=ft.Icons.EVENT_BUSY,
                    on_click=lambda _: self.dialogo_cancelar_varios(partidos),
                    visible=any(p.se_juega for p in partidos),
                ),
                ft.IconButton(ft.Icons.EDIT_CALENDAR, tooltip="Editar fechas", on_click=lambda _: self.dialogo_jornada(resumen)),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Eliminar", on_click=lambda _: self._eliminar_jornada(resumen)),
            ]
        textos = [
            ft.Text(etiqueta_jornada(self.liga, j), size=22, weight=ft.FontWeight.BOLD),
            ft.Text(rango_fechas(j.fecha_inicio, j.fecha_fin) + (f" · {j.notas}" if j.notas else ""),
                    color=ft.Colors.ON_SURFACE_VARIANT),
        ]
        if partidos:
            tabla = tarjeta(self._tabla_partidos(partidos))
        else:
            tabla = estado_vacio(
                ft.Icons.SPORTS_SOCCER,
                "Sin partidos en esta jornada",
                "Pulsa «Agregar partido» y elige equipos y campo de la lista." if self.app.es_admin else "",
            )
        self.detalle.content = ft.Column(
            [
                ft.Row([ft.Column(textos, spacing=2, expand=True), *acciones]),
                ft.Text(self._resumen_partidos(partidos), color=ft.Colors.ON_SURFACE_VARIANT),
                tabla,
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    @staticmethod
    def _resumen_partidos(partidos: list[Partido]) -> str:
        texto = f"{len(partidos)} partido{'s' if len(partidos) != 1 else ''}"
        for estado in (ESTADO_CANCELADO, ESTADO_SUSPENDIDO):
            n = sum(1 for p in partidos if p.estado == estado)
            if n:
                texto += f" · {n} {ESTADOS_PARTIDO[estado].lower()}{'s' if n != 1 else ''}"
        return texto

    def _menu_partido(self, p: Partido) -> ft.Control:
        if not self.app.es_admin:
            return ft.IconButton(ft.Icons.VISIBILITY, tooltip="Ver", on_click=lambda _: self.dialogo_partido(p.jornada_id, p))
        items = [ft.PopupMenuItem("Editar", icon=ft.Icons.EDIT, on_click=lambda _: self.dialogo_partido(p.jornada_id, p))]
        if p.se_juega:
            items += [
                ft.PopupMenuItem("Cancelar partido…", icon=ft.Icons.EVENT_BUSY,
                                 on_click=lambda _: self.dialogo_cancelar_varios([p], ESTADO_CANCELADO)),
                ft.PopupMenuItem("Suspender partido…", icon=ft.Icons.PAUSE_CIRCLE_OUTLINE,
                                 on_click=lambda _: self.dialogo_cancelar_varios([p], ESTADO_SUSPENDIDO)),
            ]
            if p.estado != ESTADO_JUGADO:
                items.append(ft.PopupMenuItem("Marcar como jugado", icon=ft.Icons.CHECK_CIRCLE_OUTLINE,
                                              on_click=lambda _: self._cambiar_estado([p], ESTADO_JUGADO)))
        if p.estado != ESTADO_PROGRAMADO:
            items.append(ft.PopupMenuItem("Volver a programado", icon=ft.Icons.UNDO,
                                          on_click=lambda _: self._cambiar_estado([p], ESTADO_PROGRAMADO)))
        items += [
            ft.PopupMenuItem(),
            ft.PopupMenuItem("Eliminar", icon=ft.Icons.DELETE_OUTLINE, on_click=lambda _: self._eliminar_partido(p)),
        ]
        return ft.PopupMenuButton(items=items, icon=ft.Icons.MORE_VERT, tooltip="Acciones")

    def _tabla_partidos(self, partidos: list[Partido]) -> ft.Control:
        filas = []
        for p in partidos:
            # Los partidos que no se juegan se ven tachados y atenuados
            estilo = None if p.se_juega else ft.TextStyle(decoration=ft.TextDecoration.LINE_THROUGH)
            color = None if p.se_juega else ft.Colors.ON_SURFACE_VARIANT
            textos = [ft.Text(f"{p.local.nombre}  vs  {p.visitante.nombre}", weight=ft.FontWeight.W_500,
                              style=estilo, color=color)]
            if p.motivo_estado:
                textos.append(ft.Text(f"Motivo: {p.motivo_estado}", size=12, italic=True, color=ft.Colors.ERROR))
            filas.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(fecha_corta(p.fecha), style=estilo, color=color)),
                        ft.DataCell(ft.Text(p.hora.strftime("%H:%M"), weight=ft.FontWeight.W_500, style=estilo, color=color)),
                        ft.DataCell(ft.Text(p.campo.nombre if p.campo else "—", style=estilo, color=color)),
                        ft.DataCell(ft.Column(textos, spacing=0, tight=True, alignment=ft.MainAxisAlignment.CENTER)),
                        ft.DataCell(
                            ft.Text(
                                " · ".join(POSICIONES_CORTAS[x] for x in p.lista_posiciones) if p.se_juega else "—",
                                tooltip=", ".join(POSICIONES[x] for x in p.lista_posiciones),
                            )
                        ),
                        ft.DataCell(etiqueta_estado(p.estado)),
                        ft.DataCell(self._menu_partido(p)),
                    ]
                )
            )
        return ft.DataTable(
            columns=[
                ft.DataColumn(ft.Text("Fecha")),
                ft.DataColumn(ft.Text("Hora")),
                ft.DataColumn(ft.Text("Campo")),
                ft.DataColumn(ft.Text("Partido")),
                ft.DataColumn(ft.Text("Árbitros"), tooltip="C = Central, A1/A2 = Asistentes, 4° = Cuarto árbitro"),
                ft.DataColumn(ft.Text("Estado")),
                ft.DataColumn(ft.Text("")),
            ],
            rows=filas,
            heading_row_color=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            column_spacing=24,
            data_row_max_height=64,
        )

    # --- Diálogos de jornada --------------------------------------------

    def dialogo_jornada(self, resumen: ResumenJornada | None = None) -> None:
        j = resumen.jornada if resumen else None
        es_torneo = self.liga.es_torneo
        numero = ft.TextField(
            label="Número *",
            value=str(j.numero if j else self.app.jornadas.siguiente_numero(self.liga.id)),
            width=120,
            keyboard_type=ft.KeyboardType.NUMBER,
            visible=not es_torneo,
        )
        inicio = CampoFecha(self.page, "Fecha *" if es_torneo else "Fecha de inicio *", j.fecha_inicio if j else None, autofocus=True)
        fin = CampoFecha(self.page, "Fecha de fin (opcional)", j.fecha_fin if j else None, opcional=True, visible=not es_torneo)
        notas = ft.TextField(label="Notas", value=(j.notas or "") if j else "", multiline=True, min_lines=1, max_lines=3)
        ayuda = ft.Text(
            "Los días se numeran solos por fecha." if es_torneo
            else "Si la jornada dura el fin de semana, pon el sábado como inicio y el domingo como fin.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )

        def guardar(_):
            ok = inicio.validar() & fin.validar()
            try:
                n = int(numero.value or "0")
                numero.error = None
            except ValueError:
                numero.error = "Solo números"
                ok = False
            if not ok:
                self.page.update()
                return
            try:
                if j:
                    guardada = self.app.jornadas.actualizar(j.id, inicio.valor, fin.valor, n, notas.value or "")
                else:
                    guardada = self.app.jornadas.crear(self.liga.id, inicio.valor, fin.valor, n, notas.value or "")
            except ErrorValidacion as e:
                mostrar_errores({"numero": numero, "fecha_inicio": inicio.campo, "fecha_fin": fin.campo}, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            self.seleccionar(guardada.id)

        if es_torneo:
            titulo = "Editar día" if j else "Agregar día al torneo"
        else:
            titulo = f"Editar jornada {j.numero}" if j else "Nueva jornada"
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(titulo),
                content=ft.Column([numero, inicio.campo, fin.campo, ayuda, notas], tight=True, spacing=12, width=ANCHO_DIALOGO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )

    def _eliminar_jornada(self, r: ResumenJornada) -> None:
        nombre = etiqueta_jornada(self.liga, r.jornada)
        detalle = f" y sus {r.partidos} partidos" if r.partidos else ""

        def aplicar():
            self.app.jornadas.eliminar(r.jornada.id)
            avisar(self.page, f"{nombre} eliminada.")
            self.app.seleccion["jornada_id"] = None
            self.refrescar()

        confirmar(self.page, f"Eliminar {nombre}", f"Se eliminará {nombre}{detalle}. Esta acción no se puede deshacer.",
                  aplicar, "Eliminar")

    # --- Diálogo de partido ----------------------------------------------

    def dialogo_partido(self, jornada_id: int, partido: Partido | None = None, previo: DatosPartido | None = None) -> None:
        """`previo` precarga fecha, hora y campo al usar «Guardar y agregar otro»."""
        editable = self.app.es_admin
        jornada = self.app.jornadas.obtener(jornada_id)
        equipos = self.app.ligas.equipos.listar(self.liga.id, solo_activos=True)
        campos_liga = self.app.ligas.campos.listar(self.liga.id, solo_activos=True)
        if partido:
            # Si el partido usa un equipo/campo ya desactivado, debe seguir apareciendo
            for item, lista in ((partido.local, equipos), (partido.visitante, equipos), (partido.campo, campos_liga)):
                if item and all(x.id != item.id for x in lista):
                    lista.append(item)

        if editable and (len(equipos) < 2 or not campos_liga):
            self._falta_catalogo(len(equipos) < 2, not campos_liga)
            return

        def opciones(items):
            return [ft.DropdownOption(key=str(i.id), text=i.nombre) for i in items]

        base = partido or previo
        local = ft.Dropdown(label="Equipo local *", options=opciones(equipos), enable_filter=True, editable=True,
                            value=str(partido.local_id) if partido else None, expand=True)
        visitante = ft.Dropdown(label="Equipo visitante *", options=opciones(equipos), enable_filter=True, editable=True,
                                value=str(partido.visitante_id) if partido else None, expand=True)
        campo = ft.Dropdown(label="Campo *", options=opciones(campos_liga),
                            value=str(base.campo_id) if base and base.campo_id else (str(campos_liga[0].id) if len(campos_liga) == 1 else None),
                            expand=True)
        fecha = CampoFecha(self.page, "Fecha *", base.fecha if base else jornada.fecha_inicio, expand=True)
        hora = CampoHora(self.page, "Hora *", base.hora if base else None, width=170)
        posiciones, casillas, error_pos = selector_posiciones(
            partido.lista_posiciones if partido else self.liga.lista_posiciones
        )
        estado = ft.Dropdown(
            label="Estado",
            value=partido.estado if partido else ESTADO_PROGRAMADO,
            options=[ft.DropdownOption(key=k, text=v) for k, v in ESTADOS_PARTIDO.items()],
            width=200,
            visible=partido is not None,
        )
        motivo = ft.TextField(
            label="Motivo de la cancelación o suspensión",
            value=(partido.motivo_estado or "") if partido else "",
            hint_text="Ej.: Lluvia",
            visible=bool(partido and not partido.se_juega),
            expand=True,
        )
        notas = ft.TextField(label="Notas", value=(partido.notas or "") if partido else "", multiline=True,
                             min_lines=1, max_lines=3)
        panel_avisos = avisos_panel()
        errores_dd = {"local": local, "visitante": visitante, "campo": campo}
        boton_guardar = ft.FilledButton("Guardar", icon=ft.Icons.SAVE)
        boton_otro = ft.OutlinedButton("Guardar y agregar otro", visible=partido is None)
        forzar = {"activo": False}

        for c in (local, visitante, campo, fecha.campo, hora.campo, estado, motivo, notas, *casillas.values()):
            c.disabled = not editable

        def datos() -> DatosPartido:
            return DatosPartido(
                fecha=fecha.valor,
                hora=hora.valor,
                local_id=int(local.value) if local.value else None,
                visitante_id=int(visitante.value) if visitante.value else None,
                campo_id=int(campo.value) if campo.value else None,
                posiciones=posiciones_marcadas(casillas),
                estado=estado.value or ESTADO_PROGRAMADO,
                notas=notas.value or "",
                motivo_estado=motivo.value or "",
            )

        def al_cambiar(_=None):
            # Cualquier cambio invalida la confirmación de avisos
            if forzar["activo"]:
                forzar["activo"] = False
                boton_guardar.content = "Guardar"
                mostrar_avisos(panel_avisos, [])
                self.page.update()

        for c in (local, visitante, campo):
            c.on_select = al_cambiar
        fecha.campo.on_change = al_cambiar
        hora.campo.on_change = al_cambiar

        def cambiar_estado(_):
            motivo.visible = estado.value in ESTADOS_SIN_JUEGO
            al_cambiar()
            self.page.update()

        estado.on_select = cambiar_estado

        def guardar(otro: bool):
            if not (fecha.validar() & hora.validar()):
                self.page.update()
                return
            d = datos()
            try:
                if partido:
                    guardado = self.app.jornadas.actualizar_partido(partido.id, d, forzar=forzar["activo"])
                else:
                    guardado = self.app.jornadas.crear_partido(jornada_id, d, forzar=forzar["activo"])
            except ErrorValidacion as e:
                for clave, dd in errores_dd.items():
                    dd.error_text = e.campos.get(clave)
                fecha.campo.error = e.campos.get("fecha")
                hora.campo.error = e.campos.get("hora")
                error_pos.value = e.campos.get("posiciones", "")
                error_pos.visible = "posiciones" in e.campos
                self.page.update()
                return
            except AvisosPendientes as e:
                for dd in errores_dd.values():
                    dd.error_text = None
                error_pos.visible = False
                mostrar_avisos(panel_avisos, e.avisos)
                forzar["activo"] = True
                boton_guardar.content = "Guardar de todas formas"
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, f"Partido guardado: {guardado.local.nombre} vs {guardado.visitante.nombre}.")
            self.refrescar()
            if otro:
                self.dialogo_partido(jornada_id, previo=d)

        boton_guardar.on_click = lambda _: guardar(False)
        boton_otro.on_click = lambda _: guardar(True)
        if editable:
            acciones = [ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()), boton_otro, boton_guardar]
        else:
            acciones = [ft.TextButton("Cerrar", on_click=lambda _: self.page.pop_dialog())]

        titulo = ("Editar partido" if editable else "Detalle del partido") if partido else "Nuevo partido"
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"{titulo} · {etiqueta_jornada(self.liga, jornada)}"),
                content=ft.Column(
                    [
                        ft.Row([local, ft.Text("vs", weight=ft.FontWeight.BOLD), visitante],
                               vertical_alignment=ft.CrossAxisAlignment.CENTER),
                        ft.Row([fecha.campo, hora.campo], spacing=12),
                        campo,
                        ft.Text("Árbitros que lleva este partido", weight=ft.FontWeight.W_500),
                        posiciones,
                        ft.Row([estado, motivo], spacing=12),
                        notas,
                        panel_avisos,
                    ],
                    tight=True,
                    spacing=12,
                    width=ANCHO_DIALOGO + 160,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=acciones,
            )
        )

    def _falta_catalogo(self, faltan_equipos: bool, faltan_campos: bool) -> None:
        faltan = []
        if faltan_equipos:
            faltan.append("al menos 2 equipos")
        if faltan_campos:
            faltan.append("al menos 1 campo")

        def ir(_):
            self.page.pop_dialog()
            self.app.seleccion["abrir_detalle"] = True
            self.shell.ir_a("ligas")

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Faltan datos de la liga"),
                content=ft.Text(f"Para crear partidos, «{self.liga.nombre}» necesita {' y '.join(faltan)}.",
                                width=ANCHO_DIALOGO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Agregarlos ahora", on_click=ir),
                ],
            )
        )

    def _cambiar_estado(self, partidos: list[Partido], estado: str, motivo: str = "") -> None:
        n = self.app.jornadas.cambiar_estado([p.id for p in partidos], estado, motivo)
        nombre = ESTADOS_PARTIDO[estado].lower()
        avisar(self.page, f"{n} partido{'s' if n != 1 else ''} marcado{'s' if n != 1 else ''} como {nombre}.")
        self.refrescar()

    def dialogo_cancelar_varios(self, partidos: list[Partido], estado_inicial: str = ESTADO_CANCELADO) -> None:
        """Cancela o suspende uno o varios partidos con un motivo (p. ej. lluvia en un campo)."""
        candidatos = [p for p in partidos if p.se_juega]
        if not candidatos:
            return
        unico = len(candidatos) == 1
        casillas = {p.id: ft.Checkbox(label=describir_partido(p), value=unico) for p in candidatos}
        estado = ft.RadioGroup(
            value=estado_inicial,
            content=ft.Row(
                [
                    ft.Radio(value=ESTADO_CANCELADO, label="Cancelado (no se jugará)"),
                    ft.Radio(value=ESTADO_SUSPENDIDO, label="Suspendido (se reprogramará)"),
                ]
            ),
        )
        motivo = ft.TextField(label="Motivo", hint_text="Ej.: Lluvia", autofocus=True)
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)

        def sugerir(texto):
            motivo.value = texto
            self.page.update()

        def marcar_todos(valor: bool):
            for c in casillas.values():
                c.value = valor
            self.page.update()

        def marcar_campo(campo_id: int):
            for p in candidatos:
                if p.campo_id == campo_id:
                    casillas[p.id].value = True
            self.page.update()

        def aplicar(_):
            elegidos = [p for p in candidatos if casillas[p.id].value]
            if not elegidos:
                error.value, error.visible = "Marca al menos un partido.", True
                self.page.update()
                return
            self.page.pop_dialog()
            self._cambiar_estado(elegidos, estado.value, motivo.value or "")

        controles = [estado, motivo,
                     ft.Row([ft.TextButton(m, on_click=lambda _, m=m: sugerir(m)) for m in MOTIVOS_SUGERIDOS], wrap=True)]
        if unico:
            controles.insert(0, ft.Text(describir_partido(candidatos[0]), weight=ft.FontWeight.W_500))
        else:
            campos = {p.campo_id: p.campo.nombre for p in candidatos if p.campo}
            atajos = [ft.TextButton("Todos", on_click=lambda _: marcar_todos(True)),
                      ft.TextButton("Ninguno", on_click=lambda _: marcar_todos(False))]
            if len(campos) > 1:
                atajos += [ft.TextButton(f"Todos en {nombre}", on_click=lambda _, c=cid: marcar_campo(c))
                           for cid, nombre in campos.items()]
            controles = [
                ft.Text("¿Qué partidos?", weight=ft.FontWeight.W_500),
                ft.Row(atajos, wrap=True, spacing=0),
                ft.Column(list(casillas.values()), spacing=0, tight=True),
                ft.Divider(),
                *controles,
            ]
        controles.append(error)
        titulo = "Cancelar o suspender partido" if unico else "Cancelar o suspender partidos"
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(titulo),
                content=ft.Column(controles, tight=True, spacing=8, width=ANCHO_DIALOGO + 160, scroll=ft.ScrollMode.AUTO),
                actions=[
                    ft.TextButton("Volver", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Aplicar", icon=ft.Icons.EVENT_BUSY, on_click=aplicar),
                ],
            )
        )

    def _eliminar_partido(self, p: Partido) -> None:
        def aplicar():
            self.app.jornadas.eliminar_partido(p.id)
            avisar(self.page, "Partido eliminado.")
            self.refrescar()

        confirmar(
            self.page,
            "Eliminar partido",
            f"¿Eliminar {p.local.nombre} vs {p.visitante.nombre} ({fecha_corta(p.fecha)} {p.hora:%H:%M})?",
            aplicar,
            "Eliminar",
        )
