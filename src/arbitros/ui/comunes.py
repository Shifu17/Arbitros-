"""Piezas de interfaz reutilizadas por todas las pantallas."""

import inspect
import io
from datetime import date, datetime, time, timedelta
from pathlib import Path

import flet as ft
from PIL import Image, ImageOps

from arbitros.ui import filtros

from arbitros.services.jornadas import texto_a_hora
from arbitros.ui import tema

ANCHO_DIALOGO = 460


def avisar(page: ft.Page, mensaje: str, error: bool = False) -> None:
    page.show_dialog(
        ft.SnackBar(
            ft.Text(mensaje, color=ft.Colors.ON_ERROR if error else None),
            bgcolor=ft.Colors.ERROR if error else None,
            show_close_icon=True,
        )
    )


def confirmar(page: ft.Page, titulo: str, mensaje: str, al_confirmar, texto_confirmar: str = "Sí, continuar") -> None:
    async def aceptar(_):
        page.pop_dialog()
        resultado = al_confirmar()
        if inspect.isawaitable(resultado):
            await resultado

    page.show_dialog(
        ft.AlertDialog(
            modal=True,
            title=ft.Text(titulo),
            content=ft.Text(mensaje, width=ANCHO_DIALOGO),
            actions=[
                ft.TextButton("Cancelar", on_click=lambda _: page.pop_dialog()),
                ft.FilledButton(texto_confirmar, on_click=aceptar),
            ],
        )
    )


def mostrar_errores(campos: dict[str, ft.TextField], errores: dict[str, str]) -> None:
    """Marca en rojo los campos con error y limpia los demás."""
    for nombre, campo in campos.items():
        campo.error = errores.get(nombre)


def encabezado(titulo: str, subtitulo: str | None = None, acciones: list[ft.Control] | None = None) -> ft.Control:
    textos = [ft.Text(titulo, size=26, weight=ft.FontWeight.BOLD)]
    if subtitulo:
        textos.append(ft.Text(subtitulo, color=ft.Colors.ON_SURFACE_VARIANT))
    return ft.Row(
        [ft.Column(textos, spacing=2, expand=True), ft.Row(acciones or [], spacing=8)],
        vertical_alignment=ft.CrossAxisAlignment.CENTER,
    )


def tarjeta(contenido: ft.Control, expand: bool | int = False, width: float | None = None) -> ft.Card:
    return ft.Card(content=ft.Container(contenido, padding=20), expand=expand, width=width)


def estado_vacio(icono, titulo: str, detalle: str = "") -> ft.Control:
    return ft.Container(
        ft.Column(
            [
                ft.Icon(icono, size=56, color=ft.Colors.OUTLINE_VARIANT),
                ft.Text(titulo, size=18, weight=ft.FontWeight.W_500, text_align=ft.TextAlign.CENTER),
                ft.Text(detalle, color=ft.Colors.ON_SURFACE_VARIANT, text_align=ft.TextAlign.CENTER),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            tight=True,
        ),
        alignment=ft.Alignment.CENTER,
        padding=40,
    )


def etiqueta(texto: str, positiva: bool) -> ft.Control:
    """Pastilla de estado (Activo / Inactivo)."""
    return ft.Container(
        ft.Text(
            texto,
            size=12,
            weight=ft.FontWeight.W_500,
            color=tema.EXITO_TEXTO if positiva else ft.Colors.ON_SURFACE_VARIANT,
        ),
        bgcolor=tema.EXITO_FONDO if positiva else ft.Colors.SURFACE_CONTAINER_HIGHEST,
        border_radius=12,
        padding=ft.Padding.symmetric(horizontal=10, vertical=4),
    )


def campo_password(etiqueta_: str, **kwargs) -> ft.TextField:
    return ft.TextField(label=etiqueta_, password=True, can_reveal_password=True, **kwargs)


def fecha_legible(fecha: datetime) -> str:
    meses = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]
    return f"{fecha.day} {meses[fecha.month - 1]} {fecha.year}, {fecha:%H:%M}"


def hace_cuanto(fecha: datetime, ahora: datetime | None = None) -> str:
    dias = ((ahora or datetime.now()).date() - fecha.date()).days
    if dias <= 0:
        return "hoy"
    if dias == 1:
        return "ayer"
    return f"hace {dias} días"


# --- Fechas ---------------------------------------------------------------

DIAS_CORTOS = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]
MESES_CORTOS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def fecha_corta(d: date) -> str:
    """sáb 24 oct"""
    return f"{DIAS_CORTOS[d.weekday()]} {d.day} {MESES_CORTOS[d.month - 1]}"


def rango_fechas(inicio: date, fin: date | None) -> str:
    return f"{fecha_corta(inicio)} – {fecha_corta(fin)}" if fin and fin != inicio else fecha_corta(inicio)


def texto_a_fecha(texto: str) -> date | None:
    """Acepta dd/mm/aaaa, dd-mm-aaaa o dd/mm/aa. None si no es válida."""
    texto = (texto or "").strip().replace("-", "/").replace(".", "/")
    for formato in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(texto, formato).date()
        except ValueError:
            pass
    return None


class SelectorImagen:
    """Vista previa con botones Elegir / Quitar para una foto o un logo.

    No guarda nada al elegir: el formulario llama a `aplicar()` después de guardar el
    registro (así también sirve al crear uno nuevo, que aún no tiene id).
    """

    LADO = 96

    def __init__(self, app, titulo: str, actual: Path | None, redonda: bool, icono, editable: bool = True):
        self.app = app
        self.titulo = titulo
        self.redonda = redonda
        self.elegida: Path | None = None
        self.quitada = False
        self.icono = icono
        self.vista = ft.Container(
            width=self.LADO, height=self.LADO, border_radius=self.LADO // 2 if redonda else 12,
            bgcolor=ft.Colors.SURFACE_CONTAINER_HIGH, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            alignment=ft.Alignment.CENTER,
        )
        self.boton_quitar = ft.TextButton("Quitar", icon=ft.Icons.DELETE_OUTLINE, on_click=self._quitar,
                                          visible=editable and actual is not None)
        self.error = ft.Text("", color=ft.Colors.ERROR, size=12, visible=False)
        self._mostrar(actual)
        botones = ft.Row([ft.OutlinedButton("Elegir imagen", icon=ft.Icons.IMAGE, on_click=self._elegir),
                          self.boton_quitar], wrap=True, spacing=4, visible=editable)
        self.control = ft.Row(
            [self.vista, ft.Column([ft.Text(titulo, weight=ft.FontWeight.W_500), botones, self.error],
                                   tight=True, spacing=6, expand=True)],
            spacing=16,
        )

    def _mostrar(self, ruta: Path | None) -> None:
        previa = _vista_previa(ruta, self.LADO * 2, recortar=self.redonda) if ruta else None
        self.vista.content = (ft.Image(src=previa, width=self.LADO, height=self.LADO, fit=ft.BoxFit.COVER)
                              if previa else ft.Icon(self.icono, size=44, color=ft.Colors.ON_SURFACE_VARIANT))

    async def _elegir(self, _) -> None:
        from arbitros.services.imagenes import EXTENSIONES

        archivos = await self.app.selector_archivos.pick_files(
            dialog_title=self.titulo, file_type=ft.FilePickerFileType.CUSTOM, allowed_extensions=EXTENSIONES)
        rutas = [Path(a.path) for a in archivos or [] if a.path]
        if not rutas:
            return
        if _vista_previa(rutas[0], 8) is None:
            self.error.value, self.error.visible = "No se pudo leer esa imagen.", True
        else:
            self.elegida, self.quitada = rutas[0], False
            self.error.visible = False
            self.boton_quitar.visible = True
            self._mostrar(rutas[0])
        self.app.page.update()

    def _quitar(self, _) -> None:
        self.elegida, self.quitada = None, True
        self.boton_quitar.visible = False
        self._mostrar(None)
        self.app.page.update()

    def aplicar(self, guardar, quitar) -> None:
        """Llama a `guardar(ruta)` o `quitar()` según lo que se haya hecho en el formulario."""
        if self.elegida:
            guardar(self.elegida)
        elif self.quitada:
            quitar()


def _vista_previa(ruta: Path, lado: int, recortar: bool = False) -> bytes | None:
    """PNG pequeño de la imagen (ya girada según su EXIF), o None si no se puede leer."""
    from arbitros.services.errores import ErrorValidacion
    from arbitros.services.imagenes import abrir_imagen

    try:
        im = abrir_imagen(ruta)
    except ErrorValidacion:
        return None
    if recortar:
        im = ImageOps.fit(im, (lado, lado), Image.LANCZOS, centering=(0.5, 0.4))
    else:
        im.thumbnail((lado, lado), Image.LANCZOS)
    salida = io.BytesIO()
    im.save(salida, format="PNG")
    return salida.getvalue()


class CampoFecha:
    """Campo de texto dd/mm/aaaa con botón de calendario."""

    def __init__(self, page: ft.Page, etiqueta_: str, valor: date | None = None, opcional: bool = False, **kwargs):
        self.page = page
        self.opcional = opcional
        self.campo = ft.TextField(
            label=etiqueta_,
            value=valor.strftime("%d/%m/%Y") if valor else "",
            hint_text="dd/mm/aaaa",
            input_filter=filtros.FECHA,
            max_length=10, counter="",
            suffix=ft.IconButton(ft.Icons.CALENDAR_MONTH, tooltip="Elegir en el calendario", on_click=self._abrir),
            **kwargs,
        )

    @property
    def valor(self) -> date | None:
        return texto_a_fecha(self.campo.value or "")

    def validar(self) -> bool:
        """Marca error si el texto no es una fecha (o está vacío y no es opcional)."""
        texto = (self.campo.value or "").strip()
        if not texto:
            self.campo.error = None if self.opcional else "Escribe la fecha"
            return self.opcional
        if self.valor is None:
            self.campo.error = "Fecha no válida (dd/mm/aaaa)"
            return False
        self.campo.error = None
        return True

    def _abrir(self, _) -> None:
        actual = self.valor or date.today()

        def elegido(e):
            if e.control.value:
                self.campo.value = e.control.value.strftime("%d/%m/%Y")
                self.campo.error = None
                self.page.update()

        self.page.show_dialog(
            ft.DatePicker(
                value=datetime(actual.year, actual.month, actual.day),
                first_date=datetime(2020, 1, 1),
                last_date=datetime(2040, 12, 31),
                help_text=self.campo.label,
                cancel_text="Cancelar",
                confirm_text="Aceptar",
                on_change=elegido,
            )
        )


class CampoHora:
    """Hora escrita libremente (10, 1030, 10:40, 4:30 pm) o elegida con el reloj."""

    def __init__(self, page: ft.Page, etiqueta_: str, valor: time | None = None, **kwargs):
        self.page = page
        self.campo = ft.TextField(
            label=etiqueta_,
            value=valor.strftime("%H:%M") if valor else "",
            hint_text="hh:mm",
            input_filter=filtros.HORA,
            max_length=8, counter="",
            suffix=ft.IconButton(ft.Icons.SCHEDULE, tooltip="Elegir en el reloj", on_click=self._abrir),
            on_blur=self._formatear,
            **kwargs,
        )

    @property
    def valor(self) -> time | None:
        return texto_a_hora(self.campo.value or "")

    def validar(self) -> bool:
        if not (self.campo.value or "").strip():
            self.campo.error = "Escribe la hora"
            return False
        if self.valor is None:
            self.campo.error = "Hora no válida (ej. 10:30)"
            return False
        self.campo.error = None
        return True

    def _formatear(self, _) -> None:
        """Al salir del campo, muestra la hora normalizada (1030 -> 10:30)."""
        if self.valor:
            self.campo.value = self.valor.strftime("%H:%M")
            self.campo.error = None
            self.page.update()

    def _abrir(self, _) -> None:
        def elegido(e):
            if e.control.value:
                self.campo.value = e.control.value.strftime("%H:%M")
                self.campo.error = None
                if self.campo.on_change:
                    self.campo.on_change(None)
                self.page.update()

        self.page.show_dialog(
            ft.TimePicker(
                value=self.valor or time(10, 0),
                help_text=self.campo.label,
                cancel_text="Cancelar",
                confirm_text="Aceptar",
                hour_format=ft.TimePickerHourFormat.H24,
                on_change=elegido,
            )
        )


def avisos_panel() -> ft.Container:
    """Recuadro de advertencias (no bloqueantes) para formularios."""
    return ft.Container(
        visible=False,
        bgcolor=tema.AVISO_FONDO,
        border_radius=8,
        padding=12,
    )


def mostrar_avisos(panel: ft.Container, avisos: list[str]) -> None:
    panel.visible = bool(avisos)
    panel.content = ft.Column(
        [
            ft.Row(
                [
                    ft.Icon(ft.Icons.WARNING_AMBER, color=tema.AVISO_TEXTO),
                    ft.Text("Revisa antes de guardar:", weight=ft.FontWeight.BOLD, color=tema.AVISO_TEXTO),
                ]
            ),
            *[ft.Text(f"• {a}", color=tema.AVISO_TEXTO) for a in avisos],
        ],
        spacing=4,
        tight=True,
    )


# --- Filtro de periodo y liga ------------------------------------------------

PERIODOS = {
    "semana": "Esta semana",
    "mes": "Este mes",
    "mes_pasado": "Mes pasado",
    "30": "Últimos 30 días",
    "anio": "Este año",
    "todo": "Todo",
    "rango": "Elegir fechas…",
}


def rango_periodo(clave: str, hoy: date | None = None) -> tuple[date | None, date | None]:
    hoy = hoy or date.today()
    if clave == "semana":
        inicio = hoy - timedelta(days=hoy.weekday())
        return inicio, inicio + timedelta(days=6)
    if clave == "mes":
        return hoy.replace(day=1), hoy
    if clave == "mes_pasado":
        fin = hoy.replace(day=1) - timedelta(days=1)
        return fin.replace(day=1), fin
    if clave == "30":
        return hoy - timedelta(days=30), hoy
    if clave == "anio":
        return hoy.replace(month=1, day=1), hoy
    return None, None


class FiltroPeriodo:
    """Periodo + liga, compartido por Pagos, Cédulas y Reportes. Llama a `al_cambiar()` al modificarse."""

    def __init__(self, app, al_cambiar, periodo: str = "mes", con_liga: bool = True):
        self.app = app
        self.al_cambiar = al_cambiar
        self.periodo = ft.Dropdown(
            label="Periodo", value=periodo, width=200, dense=True,
            options=[ft.DropdownOption(key=k, text=v) for k, v in PERIODOS.items()],
            on_select=self._cambio_periodo,
        )
        self.desde = CampoFecha(app.page, "Desde", width=170, dense=True, opcional=True)
        self.hasta = CampoFecha(app.page, "Hasta", width=170, dense=True, opcional=True)
        for c in (self.desde.campo, self.hasta.campo):
            c.on_blur = lambda _: self.al_cambiar()
            c.visible = periodo == "rango"
        ligas = app.ligas.listar()
        self.liga = ft.Dropdown(
            label="Liga", value="todas", width=260, dense=True, visible=con_liga and bool(ligas),
            options=[ft.DropdownOption(key="todas", text="Todas las ligas")]
            + [ft.DropdownOption(key=str(r.liga.id), text=r.liga.nombre) for r in ligas],
            on_select=lambda _: self.al_cambiar(),
        )

    @property
    def control(self) -> ft.Control:
        return ft.Row([self.periodo, self.desde.campo, self.hasta.campo, self.liga], spacing=12, wrap=True)

    @property
    def rango(self) -> tuple[date | None, date | None]:
        if self.periodo.value == "rango":
            return self.desde.valor, self.hasta.valor
        return rango_periodo(self.periodo.value)

    @property
    def liga_id(self) -> int | None:
        return None if self.liga.value in (None, "todas") else int(self.liga.value)

    @property
    def descripcion(self) -> str:
        desde, hasta = self.rango
        if desde and hasta:
            return f"{fecha_corta(desde)} – {fecha_corta(hasta)} {hasta.year}"
        return "todo el historial"

    def _cambio_periodo(self, _) -> None:
        rango = self.periodo.value == "rango"
        self.desde.campo.visible = self.hasta.campo.visible = rango
        if rango and not self.desde.campo.value:
            d, h = rango_periodo("mes")
            self.desde.campo.value, self.hasta.campo.value = d.strftime("%d/%m/%Y"), h.strftime("%d/%m/%Y")
        self.al_cambiar()


def tarjeta_dato(titulo: str, valor: str, color=None, icono=None) -> ft.Control:
    contenido = [ft.Text(titulo, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                 ft.Text(valor, size=22, weight=ft.FontWeight.BOLD, color=color)]
    fila = [ft.Icon(icono, color=color or ft.Colors.PRIMARY, size=28)] if icono else []
    return ft.Card(ft.Container(ft.Row([*fila, ft.Column(contenido, spacing=2)], spacing=12),
                                padding=ft.Padding.symmetric(horizontal=20, vertical=14)), expand=True)
