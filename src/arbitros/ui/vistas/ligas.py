"""Ligas y torneos: listado en tarjetas y detalle con equipos, campos, posiciones y tarifas."""

from datetime import timedelta

import flet as ft

from arbitros.db.models import POSICIONES, TIPO_LIGA, TIPO_TORNEO, Liga
from arbitros.services.dinero import a_centavos, formatear_monto, monto_editable
from arbitros.services.errores import ErrorValidacion
from arbitros.services.ligas import MAX_DIAS_TORNEO, Catalogo, DatosLiga, ResumenLiga
from arbitros.ui.comunes import (
    ANCHO_DIALOGO,
    CampoFecha,
    avisar,
    confirmar,
    encabezado,
    estado_vacio,
    etiqueta,
    mostrar_errores,
    tarjeta,
)

NOMBRE_TIPO = {TIPO_LIGA: "Liga", TIPO_TORNEO: "Torneo corto"}
ICONO_TIPO = {TIPO_LIGA: ft.Icons.EMOJI_EVENTS, TIPO_TORNEO: ft.Icons.BOLT}


def construir(app, shell) -> ft.Control:
    return VistaLigas(app, shell).construir()


def selector_posiciones(marcadas: list[str]) -> tuple[ft.Control, dict[str, ft.Checkbox], ft.Text]:
    """Casillas de posiciones + texto de error. Devuelve (control, casillas, error)."""
    casillas = {clave: ft.Checkbox(label=nombre, value=clave in marcadas) for clave, nombre in POSICIONES.items()}
    error = ft.Text("", color=ft.Colors.ERROR, size=12, visible=False)
    control = ft.Column(
        [ft.Row(list(casillas.values()), wrap=True, spacing=4), error],
        spacing=2,
        tight=True,
    )
    return control, casillas, error


def posiciones_marcadas(casillas: dict[str, ft.Checkbox]) -> list[str]:
    return [clave for clave, c in casillas.items() if c.value]


class VistaLigas:
    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.page = app.page
        self.ver_archivadas = False
        self.cuerpo = ft.Container(expand=True)

    def construir(self) -> ft.Control:
        liga_id = self.app.seleccion.get("liga_id")
        liga = self.app.ligas.obtener(liga_id) if liga_id else None
        if liga and self.app.seleccion.get("abrir_detalle"):
            self.mostrar_detalle(liga.id, actualizar=False)
        else:
            self.mostrar_lista(actualizar=False)
        return self.cuerpo

    # --- Lista ------------------------------------------------------------

    def mostrar_lista(self, actualizar: bool = True) -> None:
        self.app.seleccion["abrir_detalle"] = False
        resumenes = self.app.ligas.listar(activas=not self.ver_archivadas)
        acciones = []
        if self.app.es_admin:
            acciones.append(
                ft.FilledButton("Nueva liga o torneo", icon=ft.Icons.ADD, on_click=lambda _: self.dialogo_nueva())
            )
        filtro = ft.SegmentedButton(
            selected=["archivadas" if self.ver_archivadas else "activas"],
            segments=[
                ft.Segment(value="activas", label=ft.Text("Activas")),
                ft.Segment(value="archivadas", label=ft.Text("Archivadas")),
            ],
            on_change=self._cambiar_filtro,
        )
        if resumenes:
            contenido = ft.ResponsiveRow(
                [self._tarjeta_liga(r) for r in resumenes], spacing=16, run_spacing=16
            )
        elif self.ver_archivadas:
            contenido = estado_vacio(ft.Icons.ARCHIVE, "No hay ligas archivadas")
        else:
            contenido = estado_vacio(
                ft.Icons.EMOJI_EVENTS,
                "Aún no tienes ligas ni torneos",
                "Pulsa «Nueva liga o torneo» para registrar la primera." if self.app.es_admin else "",
            )
        self.cuerpo.content = ft.Column(
            [
                encabezado("Ligas y torneos", "Cada liga tiene sus equipos, campos, posiciones y tarifas.", acciones),
                filtro,
                contenido,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )
        if actualizar:
            self.page.update()

    def _cambiar_filtro(self, e) -> None:
        self.ver_archivadas = e.control.selected == ["archivadas"]
        self.mostrar_lista()

    def _tarjeta_liga(self, r: ResumenLiga) -> ft.Control:
        liga = r.liga
        unidad = "días" if liga.es_torneo else "jornadas"
        return ft.Container(
            ft.Card(
                ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.Icon(ICONO_TIPO[liga.tipo], color=ft.Colors.PRIMARY, size=32),
                                    ft.Text(
                                        liga.nombre, size=18, weight=ft.FontWeight.W_600, expand=True,
                                        max_lines=2, overflow=ft.TextOverflow.ELLIPSIS,
                                    ),
                                ]
                            ),
                            etiqueta(NOMBRE_TIPO[liga.tipo], liga.activa),
                            ft.Text(
                                f"{r.equipos} equipos · {r.campos} campos · {r.jornadas} {unidad}",
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                        ],
                        spacing=10,
                    ),
                    padding=20,
                    ink=True,
                    border_radius=12,
                    on_click=lambda _, i=liga.id: self.mostrar_detalle(i),
                ),
            ),
            col={"sm": 12, "md": 6, "xl": 4},
        )

    def dialogo_nueva(self) -> None:
        nombre = ft.TextField(label="Nombre *", autofocus=True, hint_text="Ej.: Liga Municipal Sabatina")
        tipo = ft.RadioGroup(
            value=TIPO_LIGA,
            content=ft.Column(
                [
                    ft.Radio(value=TIPO_LIGA, label="Liga de temporada (por jornadas)"),
                    ft.Radio(value=TIPO_TORNEO, label="Torneo corto (1 a 3 días)"),
                ],
                tight=True,
            ),
        )
        fecha = CampoFecha(self.page, "Fecha del primer día *")
        n_dias = ft.Dropdown(
            label="Número de días",
            value="1",
            options=[ft.DropdownOption(key=str(i), text=str(i)) for i in range(1, MAX_DIAS_TORNEO + 1)],
            width=160,
        )
        nota_dias = ft.Text(
            "Se crean días seguidos; después podrás cambiar la fecha de cada uno.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
        )
        bloque_torneo = ft.Column([ft.Row([fecha.campo, n_dias], spacing=12), nota_dias], visible=False, tight=True)
        fecha.campo.expand = True
        posiciones, casillas, error_pos = selector_posiciones(["central"])
        notas = ft.TextField(label="Notas", multiline=True, min_lines=1, max_lines=3)

        def cambiar_tipo(_):
            bloque_torneo.visible = tipo.value == TIPO_TORNEO
            self.page.update()

        tipo.on_change = cambiar_tipo

        def crear(_):
            es_torneo = tipo.value == TIPO_TORNEO
            dias = None
            if es_torneo:
                if not fecha.validar():
                    self.page.update()
                    return
                dias = [fecha.valor + timedelta(days=i) for i in range(int(n_dias.value or 1))]
            try:
                liga = self.app.ligas.crear(
                    DatosLiga(nombre=nombre.value or "", tipo=tipo.value, posiciones=posiciones_marcadas(casillas),
                              notas=notas.value or ""),
                    dias_torneo=dias,
                )
            except ErrorValidacion as e:
                mostrar_errores({"nombre": nombre}, e.campos)
                error_pos.value = e.campos.get("posiciones", "")
                error_pos.visible = "posiciones" in e.campos
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, f"{liga.nombre} creada. Ahora agrega sus equipos y campos.")
            self.mostrar_detalle(liga.id)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Nueva liga o torneo"),
                content=ft.Column(
                    [
                        nombre,
                        tipo,
                        bloque_torneo,
                        ft.Text("Árbitros que lleva cada partido normalmente", weight=ft.FontWeight.W_500),
                        posiciones,
                        ft.Text("En cada partido podrás cambiarlo (p. ej. agregar cuarto árbitro).",
                                size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        notas,
                    ],
                    tight=True,
                    spacing=12,
                    width=ANCHO_DIALOGO + 60,
                    scroll=ft.ScrollMode.AUTO,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Crear", icon=ft.Icons.CHECK, on_click=crear),
                ],
            )
        )

    # --- Detalle ----------------------------------------------------------

    def mostrar_detalle(self, liga_id: int, pestana: str = "equipos", actualizar: bool = True) -> None:
        liga = self.app.ligas.obtener(liga_id)
        if not liga:
            self.mostrar_lista(actualizar)
            return
        self.app.seleccion["liga_id"] = liga.id
        self.app.seleccion["abrir_detalle"] = True
        panel = ft.Container(expand=True)

        def cambiar_pestana(e):
            mostrar_pestana(e.control.selected[0])
            self.page.update()

        def mostrar_pestana(clave: str):
            if clave == "equipos":
                panel.content = PanelCatalogo(self.app, liga, self.app.ligas.equipos, "equipo", "equipos").construir()
            elif clave == "campos":
                panel.content = PanelCatalogo(
                    self.app, liga, self.app.ligas.campos, "campo", "campos", con_direccion=True
                ).construir()
            else:
                panel.content = PanelTarifas(self.app, liga).construir()

        pestanas = ft.SegmentedButton(
            selected=[pestana],
            segments=[
                ft.Segment(value="equipos", label=ft.Text("Equipos"), icon=ft.Icon(ft.Icons.GROUPS)),
                ft.Segment(value="campos", label=ft.Text("Campos"), icon=ft.Icon(ft.Icons.STADIUM)),
                ft.Segment(value="tarifas", label=ft.Text("Posiciones y tarifas"), icon=ft.Icon(ft.Icons.ATTACH_MONEY)),
            ],
            on_change=cambiar_pestana,
        )
        mostrar_pestana(pestana)

        acciones = [
            ft.FilledTonalButton(
                "Ver días" if liga.es_torneo else "Ver jornadas",
                icon=ft.Icons.CALENDAR_MONTH,
                on_click=lambda _: self._ir_a_jornadas(liga.id),
            )
        ]
        if self.app.es_admin:
            acciones += [
                ft.IconButton(ft.Icons.EDIT, tooltip="Editar nombre y notas", on_click=lambda _: self.dialogo_editar(liga)),
                ft.IconButton(
                    ft.Icons.ARCHIVE if liga.activa else ft.Icons.UNARCHIVE,
                    tooltip="Archivar" if liga.activa else "Reactivar",
                    on_click=lambda _: self._alternar_activa(liga),
                ),
            ]
        subtitulo = NOMBRE_TIPO[liga.tipo] + ("" if liga.activa else " · Archivada")
        if liga.notas:
            subtitulo += f" · {liga.notas}"
        self.cuerpo.content = ft.Column(
            [
                ft.Row(
                    [
                        ft.IconButton(ft.Icons.ARROW_BACK, tooltip="Volver a ligas", on_click=lambda _: self.mostrar_lista()),
                        ft.Container(encabezado(liga.nombre, subtitulo, acciones), expand=True),
                    ]
                ),
                pestanas,
                panel,
            ],
            spacing=16,
            expand=True,
        )
        if actualizar:
            self.page.update()

    def _ir_a_jornadas(self, liga_id: int) -> None:
        self.app.seleccion["liga_id"] = liga_id
        self.app.seleccion["jornada_id"] = None
        self.shell.ir_a("jornadas")

    def _alternar_activa(self, liga: Liga) -> None:
        def aplicar():
            self.app.ligas.cambiar_activa(liga.id, not liga.activa)
            avisar(self.page, f"{liga.nombre} {'archivada' if liga.activa else 'reactivada'}.")
            self.mostrar_lista()

        if liga.activa:
            confirmar(
                self.page,
                "Archivar",
                f"«{liga.nombre}» dejará de aparecer al cargar jornadas. Su información se conserva "
                "y puedes reactivarla en «Archivadas».",
                aplicar,
                "Archivar",
            )
        else:
            aplicar()

    def dialogo_editar(self, liga: Liga) -> None:
        nombre = ft.TextField(label="Nombre *", value=liga.nombre, autofocus=True)
        notas = ft.TextField(label="Notas", value=liga.notas or "", multiline=True, min_lines=1, max_lines=3)

        def guardar(_):
            try:
                self.app.ligas.actualizar(liga.id, nombre.value or "", notas.value or "")
            except ErrorValidacion as e:
                mostrar_errores({"nombre": nombre}, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            self.mostrar_detalle(liga.id)

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Editar"),
                content=ft.Column([nombre, notas], tight=True, spacing=12, width=ANCHO_DIALOGO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )


class PanelCatalogo:
    """Lista editable de equipos o campos de una liga."""

    def __init__(self, app, liga: Liga, catalogo: Catalogo, singular: str, plural: str, con_direccion: bool = False):
        self.app = app
        self.page = app.page
        self.liga = liga
        self.catalogo = catalogo
        self.singular = singular
        self.plural = plural
        self.con_direccion = con_direccion
        self.lista = ft.Column(spacing=0)
        self.contador = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
        self.nuevo = ft.TextField(
            label=f"Nombre del {singular}", on_submit=self._agregar, expand=True,
            hint_text="Escribe y pulsa Enter",
        )

    def construir(self) -> ft.Control:
        self.refrescar(actualizar=False)
        controles = []
        if self.app.es_admin:
            controles.append(
                ft.Row(
                    [
                        self.nuevo,
                        ft.FilledButton("Agregar", icon=ft.Icons.ADD, on_click=self._agregar),
                        ft.OutlinedButton("Agregar varios…", icon=ft.Icons.PLAYLIST_ADD, on_click=lambda _: self._varios()),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        controles += [self.contador, tarjeta(self.lista)]
        return ft.Column(controles, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    def refrescar(self, actualizar: bool = True) -> None:
        items = self.catalogo.listar(self.liga.id)
        activos = sum(1 for i in items if i.activo)
        self.contador.value = f"{activos} {self.plural} activos" + (
            f" · {len(items) - activos} inactivos" if len(items) > activos else ""
        )
        if not items:
            self.lista.controls = [
                estado_vacio(
                    ft.Icons.GROUPS if self.singular == "equipo" else ft.Icons.STADIUM,
                    f"Sin {self.plural} todavía",
                    f"Agrégalos arriba; con «Agregar varios…» puedes pegar una lista, uno por renglón.",
                )
            ]
        else:
            self.lista.controls = [self._fila(i) for i in items]
        if actualizar:
            self.page.update()

    def _fila(self, item) -> ft.Control:
        acciones = []
        if self.app.es_admin:
            acciones = [
                ft.IconButton(ft.Icons.EDIT, tooltip="Editar", on_click=lambda _, i=item: self._editar(i)),
                ft.IconButton(
                    ft.Icons.TOGGLE_ON if item.activo else ft.Icons.TOGGLE_OFF,
                    tooltip="Desactivar" if item.activo else "Reactivar",
                    on_click=lambda _, i=item: self._alternar(i),
                ),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Eliminar", on_click=lambda _, i=item: self._eliminar(i)),
            ]
        subtitulo = getattr(item, "direccion", None) if self.con_direccion else None
        return ft.ListTile(
            title=ft.Text(item.nombre, color=None if item.activo else ft.Colors.ON_SURFACE_VARIANT),
            subtitle=ft.Text(subtitulo) if subtitulo else None,
            leading=etiqueta("Activo" if item.activo else "Inactivo", item.activo),
            trailing=ft.Row(acciones, tight=True, spacing=0) if acciones else None,
            dense=True,
        )

    def _agregar(self, _) -> None:
        try:
            self.catalogo.crear(self.liga.id, self.nuevo.value or "")
        except ErrorValidacion as e:
            self.nuevo.error = e.campos.get("nombre", e.mensaje)
            self.page.update()
            return
        self.nuevo.value = ""
        self.nuevo.error = None
        self.refrescar()

    def _varios(self) -> None:
        texto = ft.TextField(
            label=f"Un {self.singular} por renglón",
            multiline=True,
            min_lines=8,
            max_lines=14,
            autofocus=True,
            hint_text="Tigres\nPumas\nÁguilas",
        )

        def guardar(_):
            creados, omitidos = self.catalogo.crear_varios(self.liga.id, texto.value or "")
            self.page.pop_dialog()
            mensaje = f"{len(creados)} {self.plural} agregados."
            if omitidos:
                mensaje += f" {len(omitidos)} ya existían: {', '.join(omitidos)}."
            avisar(self.page, mensaje)
            self.refrescar()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Agregar varios {self.plural}"),
                content=ft.Column(
                    [ft.Text("Puedes copiar la lista desde WhatsApp o Excel y pegarla aquí."), texto],
                    tight=True,
                    spacing=12,
                    width=ANCHO_DIALOGO,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Agregar", icon=ft.Icons.PLAYLIST_ADD, on_click=guardar),
                ],
            )
        )

    def _editar(self, item) -> None:
        nombre = ft.TextField(label="Nombre *", value=item.nombre, autofocus=True)
        direccion = ft.TextField(
            label="Dirección o referencia", value=getattr(item, "direccion", "") or "", visible=self.con_direccion
        )

        def guardar(_):
            extra = {"direccion": (direccion.value or "").strip() or None} if self.con_direccion else {}
            try:
                self.catalogo.actualizar(item.id, nombre.value or "", **extra)
            except ErrorValidacion as e:
                mostrar_errores({"nombre": nombre}, e.campos)
                self.page.update()
                return
            self.page.pop_dialog()
            self.refrescar()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Editar {self.singular}"),
                content=ft.Column([nombre, direccion], tight=True, spacing=12, width=ANCHO_DIALOGO),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )

    def _alternar(self, item) -> None:
        self.catalogo.cambiar_activo(item.id, not item.activo)
        self.refrescar()

    def _eliminar(self, item) -> None:
        def aplicar():
            try:
                self.catalogo.eliminar(item.id)
            except ErrorValidacion as e:
                avisar(self.page, e.mensaje, error=True)
                return
            avisar(self.page, f"{item.nombre} eliminado.")
            self.refrescar()

        confirmar(self.page, f"Eliminar {self.singular}", f"¿Eliminar «{item.nombre}»?", aplicar, "Eliminar")


class PanelTarifas:
    """Posiciones por defecto y pago por partido de cada posición."""

    def __init__(self, app, liga: Liga):
        self.app = app
        self.page = app.page
        self.liga = liga

    def construir(self) -> ft.Control:
        tarifas = self.app.ligas.tarifas(self.liga.id)
        marcadas = self.liga.lista_posiciones
        editable = self.app.es_admin
        filas, casillas, montos = [], {}, {}
        for clave, nombre in POSICIONES.items():
            casillas[clave] = ft.Checkbox(value=clave in marcadas, disabled=not editable)
            montos[clave] = ft.TextField(
                value=monto_editable(tarifas[clave]) if tarifas[clave] else "",
                prefix=ft.Text("$ "),
                hint_text="0",
                width=160,
                dense=True,
                text_align=ft.TextAlign.RIGHT,
                keyboard_type=ft.KeyboardType.NUMBER,
                read_only=not editable,
            )
            filas.append(
                ft.DataRow(
                    cells=[
                        ft.DataCell(ft.Text(nombre, weight=ft.FontWeight.W_500)),
                        ft.DataCell(casillas[clave]),
                        ft.DataCell(montos[clave]),
                    ]
                )
            )
        error = ft.Text("", color=ft.Colors.ERROR, visible=False)

        def guardar(_):
            valores, errores = {}, False
            for clave, campo in montos.items():
                try:
                    valores[clave] = a_centavos(campo.value or "")
                    campo.error = None
                except ValueError:
                    campo.error = "Monto no válido"
                    errores = True
            if errores:
                self.page.update()
                return
            try:
                self.app.ligas.configurar_posiciones_y_tarifas(
                    self.liga.id, [c for c, chk in casillas.items() if chk.value], valores
                )
            except ErrorValidacion as e:
                error.value, error.visible = e.mensaje, True
                self.page.update()
                return
            error.visible = False
            self.liga.posiciones_defecto = ",".join(c for c, chk in casillas.items() if chk.value)
            resumen = ", ".join(f"{POSICIONES[c]} {formatear_monto(v)}" for c, v in valores.items() if v)
            avisar(self.page, "Guardado." + (f" Tarifas: {resumen}" if resumen else ""))

        controles = [
            ft.Text(
                "Marca las posiciones que lleva un partido normal de esta liga. Al crear cada partido se "
                "precargan y ahí puedes cambiarlas. La tarifa es lo que se le paga al árbitro por partido.",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            tarjeta(
                ft.DataTable(
                    columns=[
                        ft.DataColumn(ft.Text("Posición")),
                        ft.DataColumn(ft.Text("Va por defecto")),
                        ft.DataColumn(ft.Text("Pago por partido")),
                    ],
                    rows=filas,
                )
            ),
            error,
        ]
        if editable:
            controles.append(ft.Row([ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar)]))
        return ft.Column(controles, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)
