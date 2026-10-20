"""Ligas y torneos: listado en tarjetas y detalle con equipos, campos, posiciones y tarifas."""

from datetime import timedelta

import flet as ft

from arbitros.ui import filtros

from arbitros.db.models import (
    FUTBOL_11,
    MODALIDADES,
    POSICIONES,
    TIPO_LIGA,
    TIPO_TORNEO,
    Liga,
    nombre_modalidad,
    posiciones_de_modalidad,
    posiciones_permitidas,
)
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


def selector_posiciones(marcadas: list[str], modalidad: str | None = None
                        ) -> tuple[ft.Control, dict[str, ft.Checkbox], ft.Text]:
    """Casillas de posiciones + texto de error. Devuelve (control, casillas, error).

    Si se indica `modalidad`, solo se muestran las posiciones que ese tipo de partido puede llevar.
    """
    casillas = {clave: ft.Checkbox(label=nombre, value=clave in marcadas) for clave, nombre in POSICIONES.items()}
    contenedores = []
    for c in casillas.values():
        contenedor = ft.Container(c, col={"xs": 6, "sm": 4})
        c.data = contenedor  # para poder ocultar la posición completa
        contenedores.append(contenedor)
    error = ft.Text("", color=ft.Colors.ERROR, size=12, visible=False)
    control = ft.Column(
        # Tres por renglón para que todas las posiciones quepan sin desplazarse
        [ft.ResponsiveRow(contenedores, spacing=0, run_spacing=0), error],
        spacing=2,
        tight=True,
    )
    if modalidad:
        mostrar_posiciones_de(casillas, modalidad, marcar_defecto=False)
    return control, casillas, error


def mostrar_posiciones_de(casillas: dict[str, ft.Checkbox], modalidad: str, marcar_defecto: bool) -> None:
    """Muestra solo las posiciones del tipo de partido; con `marcar_defecto` marca las que lleva normalmente."""
    permitidas = set(posiciones_permitidas(modalidad))
    por_defecto = set(posiciones_de_modalidad(modalidad))
    for clave, chk in casillas.items():
        (chk.data or chk).visible = clave in permitidas
        if clave not in permitidas:
            chk.value = False
        elif marcar_defecto:
            chk.value = clave in por_defecto


def posiciones_marcadas(casillas: dict[str, ft.Checkbox]) -> list[str]:
    return [clave for clave, c in casillas.items() if c.value]


HEREDAR = "liga"


def selector_modalidad(valor: str | None, casillas: dict[str, ft.Checkbox] | None = None, page=None,
                       heredar: bool = False, al_cambiar=None, modalidad_heredada: str | None = None,
                       **kwargs) -> ft.Dropdown:
    """Tipo de partido (Fútbol 11 / 7 / bardas).

    Al cambiarlo, en `casillas` solo quedan visibles las posiciones de ese tipo y se marcan las que lleva
    normalmente. Con `heredar`, la opción «Igual que la liga» usa `modalidad_heredada`.
    """
    opciones = [ft.DropdownOption(key=k, text=v[0]) for k, v in MODALIDADES.items()]
    if heredar:
        opciones.insert(0, ft.DropdownOption(key=HEREDAR, text="Igual que la liga"))
    dd = ft.Dropdown(label="Tipo de partido", options=opciones, value=valor or (HEREDAR if heredar else FUTBOL_11),
                     **kwargs)

    def cambiar(_):
        if casillas is not None:
            if dd.value == HEREDAR:
                mostrar_posiciones_de(casillas, modalidad_heredada or FUTBOL_11, marcar_defecto=False)
            else:
                mostrar_posiciones_de(casillas, dd.value, marcar_defecto=True)
        if al_cambiar:
            al_cambiar(dd.value)
        if page:
            page.update()

    dd.on_select = cambiar
    return dd


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
                            etiqueta(f"{NOMBRE_TIPO[liga.tipo]} · {nombre_modalidad(liga.modalidad)}", liga.activa),
                            ft.Text(
                                (f"{r.categorias} categorías · " if r.categorias else "")
                                + f"{r.equipos} equipos · {r.campos} campos · {r.jornadas} {unidad}",
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
        posiciones, casillas, error_pos = selector_posiciones(posiciones_de_modalidad(FUTBOL_11), FUTBOL_11)
        modalidad = selector_modalidad(FUTBOL_11, casillas, self.page, width=ANCHO_DIALOGO)
        notas = ft.TextField(label="Notas", multiline=True, min_lines=1, max_lines=3)
        categorias = ft.TextField(
            label="Categorías o sub-ligas (opcional)",
            hint_text="Una por renglón: Veteranos, Premier A, Oro…",
            multiline=True,
            min_lines=2,
            max_lines=6,
        )

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
                              notas=notas.value or "", modalidad=modalidad.value),
                    dias_torneo=dias,
                )
            except ErrorValidacion as e:
                mostrar_errores({"nombre": nombre}, e.campos)
                error_pos.value = e.campos.get("posiciones", "")
                error_pos.visible = "posiciones" in e.campos
                self.page.update()
                return
            self.app.ligas.categorias.crear_varios(liga.id, categorias.value or "")
            self.page.pop_dialog()
            avisar(self.page, f"{liga.nombre} creada. Ahora agrega sus equipos y campos.")
            self.mostrar_detalle(liga.id, "equipos")

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Nueva liga o torneo"),
                content=ft.Column(
                    [
                        nombre,
                        tipo,
                        bloque_torneo,
                        modalidad,
                        ft.Text("Árbitros que lleva cada partido normalmente", weight=ft.FontWeight.W_500),
                        posiciones,
                        ft.Text("Si la liga tiene fut 7 y bardas, usa categorías con su propio tipo; "
                                "y en cada partido también puedes cambiarlo.",
                                size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                        categorias,
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
            paneles = {"categorias": PanelCategorias, "equipos": PanelEquipos, "campos": PanelCampos, "tarifas": PanelTarifas}
            panel.content = paneles[clave](self.app, liga).construir()

        pestanas = ft.SegmentedButton(
            selected=[pestana],
            segments=[
                ft.Segment(value="categorias", label=ft.Text("Categorías"), icon=ft.Icon(ft.Icons.CATEGORY)),
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
    """Lista editable de elementos de una liga (equipos, campos o categorías).

    Las subclases agregan campos propios con los ganchos `_campos_extra`,
    `_valores_extra`, `_subtitulo`, `_acciones_extra` y `_filtrar`.
    """

    icono = ft.Icons.GROUPS

    def __init__(self, app, liga: Liga, catalogo: Catalogo, singular: str, plural: str, ayuda: str = ""):
        self.app = app
        self.page = app.page
        self.liga = liga
        self.catalogo = catalogo
        self.singular = singular
        self.plural = plural
        self.ayuda = ayuda
        self.lista = ft.Column(spacing=0)
        self.contador = ft.Text(color=ft.Colors.ON_SURFACE_VARIANT)
        self.nuevo = ft.TextField(
            label=f"Nombre {'de la' if catalogo.articulo == 'la' else 'del'} {singular}", on_submit=self._agregar,
            expand=True, hint_text="Escribe y pulsa Enter",
        )

    # --- Ganchos para subclases -----------------------------------------

    def _campos_extra(self, item=None) -> list[ft.Control]:
        """Controles adicionales para alta (item=None) o edición."""
        return []

    def _valores_extra(self, controles: list[ft.Control]) -> dict:
        return {}

    def _subtitulo(self, item) -> str | None:
        return None

    def _acciones_extra(self, item) -> list[ft.Control]:
        return []

    def _filtros(self) -> list[ft.Control]:
        return []

    def _filtrar(self, items: list) -> list:
        return items

    # --- Vista ------------------------------------------------------------

    def construir(self) -> ft.Control:
        self.refrescar(actualizar=False)
        controles = []
        if self.ayuda:
            controles.append(ft.Text(self.ayuda, color=ft.Colors.ON_SURFACE_VARIANT))
        if self.app.es_admin:
            self.extra_alta = self._campos_extra()
            controles.append(
                ft.Row(
                    [
                        self.nuevo,
                        *self.extra_alta,
                        ft.FilledButton("Agregar", icon=ft.Icons.ADD, on_click=self._agregar),
                        ft.OutlinedButton("Agregar varios…", icon=ft.Icons.PLAYLIST_ADD, on_click=lambda _: self._varios()),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.CENTER,
                )
            )
        controles += [ft.Row([self.contador, *self._filtros()], alignment=ft.MainAxisAlignment.SPACE_BETWEEN),
                      tarjeta(self.lista)]
        return ft.Column(controles, spacing=12, scroll=ft.ScrollMode.AUTO, expand=True)

    def refrescar(self, actualizar: bool = True) -> None:
        todos = self.catalogo.listar(self.liga.id)
        activos = sum(1 for i in todos if i.activo)
        self.contador.value = f"{activos} {self.plural} activos" + (
            f" · {len(todos) - activos} inactivos" if len(todos) > activos else ""
        )
        items = self._filtrar(todos)
        if not todos:
            self.lista.controls = [
                estado_vacio(
                    self.icono,
                    f"Sin {self.plural} todavía",
                    "Agrégalos arriba; con «Agregar varios…» puedes pegar una lista, uno por renglón."
                    if self.app.es_admin else "",
                )
            ]
        elif not items:
            self.lista.controls = [ft.Text("Nada con este filtro.", color=ft.Colors.ON_SURFACE_VARIANT)]
        else:
            self.lista.controls = [self._fila(i) for i in items]
        if actualizar:
            self.page.update()

    def _fila(self, item) -> ft.Control:
        acciones = self._acciones_extra(item)
        if self.app.es_admin:
            acciones += [
                ft.IconButton(ft.Icons.EDIT, tooltip="Editar", on_click=lambda _, i=item: self._editar(i)),
                ft.IconButton(
                    ft.Icons.TOGGLE_ON if item.activo else ft.Icons.TOGGLE_OFF,
                    tooltip="Desactivar" if item.activo else "Reactivar",
                    on_click=lambda _, i=item: self._alternar(i),
                ),
                ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Eliminar", on_click=lambda _, i=item: self._eliminar(i)),
            ]
        subtitulo = self._subtitulo(item)
        return ft.ListTile(
            title=ft.Text(item.nombre, color=None if item.activo else ft.Colors.ON_SURFACE_VARIANT),
            subtitle=ft.Text(subtitulo) if subtitulo else None,
            leading=etiqueta("Activo" if item.activo else "Inactivo", item.activo),
            trailing=ft.Row(acciones, tight=True, spacing=0) if acciones else None,
            dense=True,
        )

    # --- Acciones ---------------------------------------------------------

    def _agregar(self, _) -> None:
        try:
            self.catalogo.crear(self.liga.id, self.nuevo.value or "", **self._valores_extra(self.extra_alta))
        except ErrorValidacion as e:
            self.nuevo.error = e.campos.get("nombre", e.mensaje)
            self.page.update()
            return
        self.nuevo.value = ""
        self.nuevo.error = None
        self.refrescar()

    def _varios(self) -> None:
        texto = ft.TextField(
            label=f"{'Una' if self.catalogo.articulo == 'la' else 'Un'} {self.singular} por renglón",
            multiline=True,
            min_lines=8,
            max_lines=14,
            autofocus=True,
        )
        extra = self._campos_extra()

        def guardar(_):
            creados, omitidos = self.catalogo.crear_varios(self.liga.id, texto.value or "", **self._valores_extra(extra))
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
                    [ft.Text("Puedes copiar la lista desde WhatsApp o Excel y pegarla aquí."), *extra, texto],
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
        extra = self._campos_extra(item)

        def guardar(_):
            try:
                self.catalogo.actualizar(item.id, nombre.value or "", **self._valores_extra(extra))
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
                content=ft.Column([nombre, *extra], tight=True, spacing=12, width=ANCHO_DIALOGO),
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


SIN_CATEGORIA = "sin"
TODAS = "todas"


class PanelEquipos(PanelCatalogo):
    """Equipos; si la liga tiene categorías, cada equipo se asigna a una."""

    def __init__(self, app, liga: Liga):
        super().__init__(app, liga, app.ligas.equipos, "equipo", "equipos")
        self.categorias = app.ligas.categorias.listar(liga.id, solo_activos=True)
        self.nombres_categoria = {c.id: c.nombre for c in app.ligas.categorias.listar(liga.id)}
        self.filtro_categoria = TODAS

    def _selector_categoria(self, valor: int | None = None) -> ft.Dropdown:
        opciones = [ft.DropdownOption(key=str(c.id), text=c.nombre) for c in self.categorias]
        opciones.append(ft.DropdownOption(key=SIN_CATEGORIA, text="Sin categoría"))
        if valor is None and len(self.categorias) and self.filtro_categoria not in (TODAS, SIN_CATEGORIA):
            valor = int(self.filtro_categoria)  # al dar de alta, usar la categoría que se está viendo
        return ft.Dropdown(label="Categoría", options=opciones, value=str(valor) if valor else SIN_CATEGORIA, width=220)

    def _campos_extra(self, item=None) -> list[ft.Control]:
        if not self.categorias:
            return []
        return [self._selector_categoria(item.categoria_id if item else None)]

    def _valores_extra(self, controles) -> dict:
        if not controles:
            return {}
        valor = controles[0].value
        return {"categoria_id": None if valor in (None, SIN_CATEGORIA) else int(valor)}

    def _subtitulo(self, item) -> str | None:
        if not self.nombres_categoria:
            return None
        return self.nombres_categoria.get(item.categoria_id, "Sin categoría")

    def _filtros(self) -> list[ft.Control]:
        if not self.categorias:
            return []
        opciones = [ft.DropdownOption(key=TODAS, text="Todas las categorías")]
        opciones += [ft.DropdownOption(key=str(c.id), text=c.nombre) for c in self.categorias]
        opciones.append(ft.DropdownOption(key=SIN_CATEGORIA, text="Sin categoría"))

        def cambiar(e):
            self.filtro_categoria = e.control.value
            if self.app.es_admin and self.extra_alta and self.filtro_categoria != TODAS:
                self.extra_alta[0].value = self.filtro_categoria
            self.refrescar()

        return [ft.Dropdown(label="Ver", options=opciones, value=self.filtro_categoria, on_select=cambiar, width=240, dense=True)]

    def _filtrar(self, items: list) -> list:
        if self.filtro_categoria == TODAS:
            return items
        if self.filtro_categoria == SIN_CATEGORIA:
            return [i for i in items if i.categoria_id is None]
        return [i for i in items if i.categoria_id == int(self.filtro_categoria)]


class PanelCampos(PanelCatalogo):
    icono = ft.Icons.STADIUM

    def __init__(self, app, liga: Liga):
        super().__init__(app, liga, app.ligas.campos, "campo", "campos")

    def _campos_extra(self, item=None) -> list[ft.Control]:
        if item is None:
            return []  # la dirección se captura al editar, para que el alta sea rápida
        return [ft.TextField(label="Dirección o referencia", value=item.direccion or "")]

    def _valores_extra(self, controles) -> dict:
        return {"direccion": (controles[0].value or "").strip() or None} if controles else {}

    def _subtitulo(self, item) -> str | None:
        return item.direccion


class PanelCategorias(PanelCatalogo):
    """Sub-ligas (Veteranos, Premier A, Oro...) con posiciones y tarifas opcionales propias."""

    icono = ft.Icons.CATEGORY

    def __init__(self, app, liga: Liga):
        super().__init__(
            app, liga, app.ligas.categorias, "categoría", "categorías",
            ayuda="Si la liga se divide en sub-ligas (Veteranos, Premier A, Oro, Plata…), agrégalas aquí. "
                  "Cada equipo y cada partido pertenecerá a una. Cada categoría puede tener sus propias "
                  "posiciones y tarifas; si no, usa las de la liga.",
        )

    def _subtitulo(self, item) -> str | None:
        partes = [nombre_modalidad(item.modalidad) if item.modalidad else "Tipo de la liga"]
        posiciones = item.lista_posiciones
        partes.append(
            "Posiciones: " + ", ".join(POSICIONES[p] for p in posiciones) if posiciones else "Posiciones de la liga"
        )
        tarifas = self.app.ligas.tarifas_categoria(item.id)
        if tarifas:
            partes.append("Tarifas: " + ", ".join(f"{POSICIONES[p]} {formatear_monto(v)}" for p, v in tarifas.items() if v))
        else:
            partes.append("Tarifas de la liga")
        return " · ".join(partes)

    def _acciones_extra(self, item) -> list[ft.Control]:
        if not self.app.es_admin:
            return []
        return [ft.IconButton(ft.Icons.ATTACH_MONEY, tooltip="Tipo de partido, posiciones y tarifas",
                              on_click=lambda _, i=item: self._configurar(i))]

    def _configurar(self, categoria) -> None:
        tarifas_liga = self.app.ligas.tarifas(self.liga.id)
        propias = self.app.ligas.tarifas_categoria(categoria.id)
        usar_pos_liga = ft.Switch(label="Usar las posiciones de la liga", value=categoria.lista_posiciones is None)
        posiciones, casillas, error_pos = selector_posiciones(categoria.lista_posiciones or self.liga.lista_posiciones,
                                                              categoria.modalidad or self.liga.modalidad)
        usar_tarifas_liga = ft.Switch(label="Usar las tarifas de la liga", value=propias is None)
        montos = {
            p: ft.TextField(
                label=nombre, prefix=ft.Text("$ "), width=150, dense=True, text_align=ft.TextAlign.RIGHT,
                input_filter=filtros.MONTO, max_length=9, counter="",
                value=monto_editable((propias or tarifas_liga)[p]) if (propias or tarifas_liga)[p] else "",
            )
            for p, nombre in POSICIONES.items()
        }
        bloque_montos = ft.Row(list(montos.values()), wrap=True, spacing=8, run_spacing=8)

        def al_elegir_tipo(valor):
            # Elegir un tipo propio implica posiciones propias (las del tipo, editables)
            usar_pos_liga.value = valor == HEREDAR
            posiciones.disabled = usar_pos_liga.value

        modalidad = selector_modalidad(categoria.modalidad, casillas, self.page, heredar=True,
                                       al_cambiar=al_elegir_tipo, modalidad_heredada=self.liga.modalidad, width=320)

        def sincronizar(_=None):
            posiciones.disabled = usar_pos_liga.value
            bloque_montos.disabled = usar_tarifas_liga.value
            self.page.update()

        usar_pos_liga.on_change = sincronizar
        usar_tarifas_liga.on_change = sincronizar
        posiciones.disabled = usar_pos_liga.value
        bloque_montos.disabled = usar_tarifas_liga.value

        def guardar(_):
            tarifas = None
            if not usar_tarifas_liga.value:
                tarifas, malos = {}, False
                for p, campo in montos.items():
                    try:
                        tarifas[p] = a_centavos(campo.value or "")
                        campo.error = None
                    except ValueError:
                        campo.error = "No válido"
                        malos = True
                if malos:
                    self.page.update()
                    return
            try:
                self.app.ligas.configurar_categoria(
                    categoria.id, None if usar_pos_liga.value else posiciones_marcadas(casillas), tarifas,
                    modalidad=None if modalidad.value == HEREDAR else modalidad.value,
                )
            except ErrorValidacion as e:
                error_pos.value, error_pos.visible = e.mensaje, True
                self.page.update()
                return
            self.page.pop_dialog()
            avisar(self.page, f"{categoria.nombre} actualizada.")
            self.refrescar()

        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Tipo de partido, posiciones y tarifas · {categoria.nombre}"),
                content=ft.Column(
                    [modalidad, usar_pos_liga, posiciones, ft.Divider(), usar_tarifas_liga, bloque_montos],
                    tight=True,
                    spacing=12,
                    width=ANCHO_DIALOGO + 160,
                ),
                actions=[
                    ft.TextButton("Cancelar", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Guardar", icon=ft.Icons.SAVE, on_click=guardar),
                ],
            )
        )


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
                input_filter=filtros.MONTO,
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
        modalidad = selector_modalidad(self.liga.modalidad, casillas, self.page, width=320, disabled=not editable)
        mostrar_posiciones_de(casillas, self.liga.modalidad, marcar_defecto=False)

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
                    self.liga.id, [c for c, chk in casillas.items() if chk.value], valores, modalidad=modalidad.value
                )
            except ErrorValidacion as e:
                error.value, error.visible = e.mensaje, True
                self.page.update()
                return
            error.visible = False
            self.liga.posiciones_defecto = ",".join(c for c, chk in casillas.items() if chk.value)
            self.liga.modalidad = modalidad.value
            resumen = ", ".join(f"{POSICIONES[c]} {formatear_monto(v)}" for c, v in valores.items() if v)
            avisar(self.page, "Guardado." + (f" Tarifas: {resumen}" if resumen else ""))

        controles = [
            ft.Text(
                "Elige el tipo de partido y marca las posiciones que lleva un partido normal de esta liga. "
                "Al crear cada partido se precargan y ahí puedes cambiarlas. La tarifa es lo que se le paga "
                "al árbitro por partido.",
                color=ft.Colors.ON_SURFACE_VARIANT,
            ),
            modalidad,
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
