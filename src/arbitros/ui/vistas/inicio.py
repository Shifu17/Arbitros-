"""Inicio: tablero con lo que viene (próximos partidos) y lo que falta por hacer (pendientes)."""

from datetime import date, timedelta

import flet as ft

from arbitros import __version__
from arbitros.services.dinero import formatear_monto
from arbitros.services.jornadas import etiqueta_jornada
from arbitros.services.texto import DIAS, MESES, fecha_larga
from arbitros.ui import tema
from arbitros.ui.comunes import hace_cuanto

DIAS_PROXIMOS = 7
DIAS_RESPALDO_VIEJO = 14


def construir(app, shell) -> ft.Control:
    return VistaInicio(app, shell).construir()


def _titulo_seccion(texto: str, accion: ft.Control | None = None) -> ft.Control:
    return ft.Row([ft.Text(texto, size=18, weight=ft.FontWeight.W_600, expand=True), accion or ft.Container()],
                  vertical_alignment=ft.CrossAxisAlignment.CENTER)


def _panel(contenido: ft.Control, col: dict) -> ft.Control:
    return ft.Container(ft.Card(ft.Container(contenido, padding=20)), col=col)


class VistaInicio:
    def __init__(self, app, shell):
        self.app = app
        self.shell = shell
        self.hoy = date.today()
        self.proximos = app.jornadas.partidos_entre(self.hoy, self.hoy + timedelta(days=DIAS_PROXIMOS))
        self.asignaciones = app.asignaciones.de_partidos([p.id for p, _, _ in self.proximos])

    def construir(self) -> ft.Control:
        controles = [self._bienvenida(), self._indicadores()]
        pasos = self._primeros_pasos()
        columna_derecha = [self._pendientes()] + ([pasos] if pasos else [])
        controles.append(ft.ResponsiveRow(
            [
                _panel(self._agenda(), {"sm": 12, "lg": 7}),
                ft.Column(columna_derecha, col={"sm": 12, "lg": 5}, spacing=12),
            ],
            spacing=12,
            run_spacing=12,
            vertical_alignment=ft.CrossAxisAlignment.START,
        ))
        controles.append(self._pie())
        return ft.Column(controles, spacing=16, scroll=ft.ScrollMode.AUTO, expand=True)

    # --- Bienvenida ---------------------------------------------------------

    def _bienvenida(self) -> ft.Control:
        nombre = self.app.usuario.nombre.split()[0]
        hoy = f"{DIAS[self.hoy.weekday()]} {self.hoy.day} de {MESES[self.hoy.month - 1]}"
        m = tema.marca()
        acciones = []
        if self.app.es_admin:
            acciones = [
                ft.FilledButton("Asignar árbitros", icon=ft.Icons.PERSON_ADD_ALT_1,
                                style=ft.ButtonStyle(bgcolor=m.acento, color=m.fondo),
                                on_click=lambda _: self.shell.ir_a("jornadas")),
                ft.OutlinedButton("Generar rol", icon=ft.Icons.SEND,
                                  style=ft.ButtonStyle(color="#FFFFFF", side=ft.BorderSide(1, "#FFFFFF")),
                                  on_click=lambda _: self.shell.ir_a("rol")),
            ]
        return ft.Container(
            ft.Column(
                [
                    ft.Row(
                        [
                            tema.logo(72),
                            ft.Column(
                                [
                                    ft.Text(f"Hola, {nombre}", size=28, weight=ft.FontWeight.BOLD, color="#FFFFFF"),
                                    ft.Text(f"{m.nombre} · {hoy}", color=m.acento),
                                ],
                                spacing=2,
                                expand=True,
                            ),
                            ft.Row(acciones, spacing=8),
                        ],
                        spacing=20,
                        vertical_alignment=ft.CrossAxisAlignment.CENTER,
                    ),
                    tema.franja(6, border_radius=3),
                ],
                spacing=16,
            ),
            bgcolor=m.fondo,
            border_radius=16,
            padding=ft.Padding.only(left=24, right=24, top=20, bottom=16),
        )

    # --- Indicadores --------------------------------------------------------

    def _indicadores(self) -> ft.Control:
        semana = [p for p, _, _ in self.proximos if p.se_juega]
        pendiente_pagos = sum(r.pendiente for r in self.app.pagos.resumen_por_arbitro())
        cedulas = self.app.cedulas.contar_pendientes()

        def indicador(icono, titulo, valor, detalle, destino, alerta=False):
            color = tema.PELIGRO_TEXTO if alerta else ft.Colors.PRIMARY
            return ft.Container(
                ft.Card(ft.Container(
                    ft.Row(
                        [
                            ft.Container(ft.Icon(icono, color=color, size=26), padding=10, border_radius=12,
                                         bgcolor=tema.PELIGRO_FONDO if alerta else ft.Colors.SURFACE_CONTAINER_HIGH),
                            ft.Column(
                                [ft.Text(titulo, size=12, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1,
                                         overflow=ft.TextOverflow.ELLIPSIS),
                                 ft.Text(valor, size=24, weight=ft.FontWeight.BOLD,
                                         color=tema.PELIGRO_TEXTO if alerta else None),
                                 ft.Text(detalle, size=11, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1,
                                         overflow=ft.TextOverflow.ELLIPSIS)],
                                spacing=0, expand=True,
                            ),
                        ],
                        spacing=14,
                    ),
                    padding=16, height=104, ink=True, border_radius=12,
                    on_click=lambda _: self.shell.ir_a(destino),
                )),
                col={"xs": 6, "lg": 3},
            )

        return ft.ResponsiveRow(
            [
                indicador(ft.Icons.PEOPLE, "Árbitros activos", str(self.app.arbitros.contar_activos()),
                          "Ver lista", "arbitros"),
                indicador(ft.Icons.SPORTS_SOCCER, "Próximos 7 días", str(len(semana)),
                          f"partidos · {len({l.id for _, l, _ in self.proximos})} liga(s)", "jornadas"),
                indicador(ft.Icons.PAYMENTS, "Pagos pendientes", formatear_monto(pendiente_pagos),
                          "Partidos ya jugados", "pagos", alerta=pendiente_pagos > 0),
                indicador(ft.Icons.DESCRIPTION, "Cédulas pendientes", str(cedulas),
                          "De partidos jugados", "cedulas", alerta=cedulas > 0),
            ],
            spacing=12,
            run_spacing=12,
        )

    # --- Próximos partidos ----------------------------------------------------

    def _agenda(self) -> ft.Control:
        encabezado = _titulo_seccion(
            "Próximos partidos",
            ft.TextButton("Ver jornadas", icon=ft.Icons.CALENDAR_MONTH, on_click=lambda _: self.shell.ir_a("jornadas")),
        )
        if not self.proximos:
            return ft.Column([
                encabezado,
                ft.Container(
                    ft.Column([
                        ft.Icon(ft.Icons.EVENT_AVAILABLE, size=48, color=ft.Colors.OUTLINE_VARIANT),
                        ft.Text("No hay partidos en los próximos 7 días", weight=ft.FontWeight.W_500),
                        ft.Text("Carga la siguiente jornada para empezar a asignar.", size=12,
                                color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.FilledButton("Cargar jornada", icon=ft.Icons.ADD, on_click=lambda _: self.shell.ir_a("jornadas"),
                                        visible=self.app.es_admin),
                    ], horizontal_alignment=ft.CrossAxisAlignment.CENTER, spacing=8),
                    padding=30, alignment=ft.Alignment.CENTER,
                ),
            ], spacing=8)

        filas = [encabezado]
        fecha_actual = None
        for p, liga, jornada in self.proximos[:14]:
            if p.fecha != fecha_actual:
                fecha_actual = p.fecha
                etiqueta = "Hoy" if p.fecha == self.hoy else "Mañana" if p.fecha == self.hoy + timedelta(days=1) \
                    else fecha_larga(p.fecha)
                filas.append(ft.Container(ft.Text(etiqueta.upper(), size=12, weight=ft.FontWeight.BOLD,
                                                  color=ft.Colors.PRIMARY), padding=ft.Padding.only(top=8)))
            filas.append(self._fila_partido(p, liga, jornada))
        if len(self.proximos) > 14:
            filas.append(ft.Text(f"… y {len(self.proximos) - 14} partido(s) más", size=12,
                                 color=ft.Colors.ON_SURFACE_VARIANT))
        return ft.Column(filas, spacing=4)

    def _fila_partido(self, p, liga, jornada) -> ft.Control:
        asignadas = self.asignaciones.get(p.id, {})
        faltan = sum(1 for pos in p.lista_posiciones if pos not in asignadas)
        if not p.se_juega:
            estado, fondo, color = p.estado.capitalize(), ft.Colors.SURFACE_CONTAINER_HIGHEST, ft.Colors.ON_SURFACE_VARIANT
        elif faltan:
            estado, fondo, color = (f"Falta{'n' if faltan > 1 else ''} {faltan}", tema.PELIGRO_FONDO, tema.PELIGRO_TEXTO)
        else:
            estado, fondo, color = "Completo", tema.EXITO_FONDO, tema.EXITO_TEXTO
        detalle = " · ".join(x for x in (liga.nombre, etiqueta_jornada(liga, jornada),
                                          p.campo.nombre if p.campo else "", p.categoria.nombre if p.categoria else "") if x)

        def ir(_):
            self.app.seleccion["liga_id"] = liga.id
            self.app.seleccion["jornada_id"] = jornada.id
            self.shell.ir_a("jornadas")

        return ft.Container(
            ft.Row(
                [
                    ft.Text(f"{p.hora:%H:%M}", size=16, weight=ft.FontWeight.BOLD, width=56),
                    ft.Column(
                        [ft.Text(f"{p.local.nombre} vs {p.visitante.nombre}", weight=ft.FontWeight.W_600,
                                 max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                         ft.Text(detalle, size=12, color=ft.Colors.ON_SURFACE_VARIANT, max_lines=1,
                                 overflow=ft.TextOverflow.ELLIPSIS)],
                        spacing=0, expand=True,
                    ),
                    ft.Container(ft.Text(estado, size=12, weight=ft.FontWeight.W_500, color=color), bgcolor=fondo,
                                 border_radius=12, padding=ft.Padding.symmetric(horizontal=10, vertical=4)),
                ],
                spacing=12,
            ),
            padding=ft.Padding.symmetric(horizontal=8, vertical=6),
            border_radius=8,
            ink=True,
            on_click=ir,
        )

    # --- Pendientes -------------------------------------------------------------

    def _pendientes(self) -> ft.Control:
        items = []

        def item(icono, color, texto, boton, destino, al_ir=None):
            def ir(_):
                if al_ir:
                    al_ir()
                self.shell.ir_a(destino)

            items.append(ft.Row(
                [ft.Icon(icono, color=color), ft.Text(texto, expand=True),
                 ft.TextButton(boton, on_click=ir)],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ))

        faltan = sum(1 for p, _, _ in self.proximos if p.se_juega
                     for pos in p.lista_posiciones if pos not in self.asignaciones.get(p.id, {}))
        if faltan:
            item(ft.Icons.PERSON_SEARCH, tema.PELIGRO_TEXTO,
                 f"Falta{'n' if faltan > 1 else ''} {faltan} árbitro{'s' if faltan > 1 else ''} por asignar esta semana",
                 "Asignar", "jornadas")

        # Roles de las jornadas próximas: sin enviar o con cambios desde que se enviaron
        jornadas = {j.id: (l, j) for _, l, j in self.proximos}
        for jornada_id, (liga, jornada) in jornadas.items():
            nombre = f"{liga.nombre} · {etiqueta_jornada(liga, jornada)}"

            def seleccionar(liga_id=liga.id, jid=jornada_id):
                self.app.seleccion["liga_id"] = liga_id
                self.app.seleccion["jornada_id"] = jid

            cambios = self.app.rol.cambios(jornada_id)
            if cambios is None:
                item(ft.Icons.SEND, tema.AVISO_ICONO, f"Rol sin enviar: {nombre}", "Abrir", "rol", seleccionar)
            elif cambios:
                item(ft.Icons.SYNC_PROBLEM, tema.AVISO_ICONO,
                     f"{len(cambios)} cambio(s) sin avisar: {nombre}", "Avisar", "rol", seleccionar)

        cedulas = self.app.cedulas.contar_pendientes()
        if cedulas:
            item(ft.Icons.DESCRIPTION, tema.PELIGRO_TEXTO, f"{cedulas} cédula(s) por subir", "Subir", "cedulas")
        pendiente = sum(r.pendiente for r in self.app.pagos.resumen_por_arbitro())
        if pendiente:
            item(ft.Icons.PAYMENTS, tema.PELIGRO_TEXTO, f"{formatear_monto(pendiente)} por pagar a árbitros",
                 "Pagar", "pagos")
        ultimo = self.app.respaldos.ultimo()
        if not ultimo or (self.hoy - ultimo.fecha.date()).days > DIAS_RESPALDO_VIEJO:
            item(ft.Icons.BACKUP, tema.AVISO_ICONO,
                 "Aún no hay respaldos" if not ultimo else f"Último respaldo {hace_cuanto(ultimo.fecha)}",
                 "Respaldar", "respaldos")

        if not items:
            items.append(ft.Row([ft.Icon(ft.Icons.CHECK_CIRCLE, color=tema.EXITO_ICONO, size=28),
                                 ft.Text("¡Todo al día! No hay pendientes.", weight=ft.FontWeight.W_500)]))
        return ft.Card(ft.Container(ft.Column([_titulo_seccion("Pendientes"), *items], spacing=6), padding=20))

    # --- Primeros pasos (solo mientras falten) -----------------------------------

    def _primeros_pasos(self) -> ft.Control | None:
        ligas = self.app.ligas.listar()
        pasos = [
            ("Registra a tus árbitros", self.app.arbitros.contar_activos() > 0, "arbitros"),
            ("Da de alta ligas, equipos y campos", any(r.equipos and r.campos for r in ligas), "ligas"),
            ("Carga una jornada con sus partidos",
             any(j.partidos for r in ligas for j in self.app.jornadas.listar(r.liga.id)), "jornadas"),
            ("Asigna árbitros a los partidos", self.app.asignaciones.hay_asignaciones(), "jornadas"),
        ]
        hechos = sum(1 for _, ok, _ in pasos if ok)
        if hechos == len(pasos):
            return None
        filas = [
            _titulo_seccion("Primeros pasos"),
            ft.ProgressBar(value=hechos / len(pasos), color=ft.Colors.PRIMARY,
                           bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST, border_radius=4),
            ft.Text(f"{hechos} de {len(pasos)} completados", size=12, color=ft.Colors.ON_SURFACE_VARIANT),
        ]
        for i, (texto, ok, destino) in enumerate(pasos, start=1):
            filas.append(ft.Row(
                [ft.Icon(ft.Icons.CHECK_CIRCLE if ok else ft.Icons.RADIO_BUTTON_UNCHECKED,
                         color=tema.EXITO_ICONO if ok else ft.Colors.OUTLINE, size=20),
                 ft.Text(f"{i}. {texto}", expand=True,
                         color=ft.Colors.ON_SURFACE_VARIANT if ok else None),
                 ft.TextButton("Ir", on_click=lambda _, d=destino: self.shell.ir_a(d), visible=not ok)],
            ))
        return ft.Card(ft.Container(ft.Column(filas, spacing=6), padding=20))

    # --- Pie ----------------------------------------------------------------

    def _pie(self) -> ft.Control:
        ultimo = self.app.respaldos.ultimo()
        respaldo = f"Último respaldo: {hace_cuanto(ultimo.fecha)}" if ultimo else "Sin respaldos todavía"
        controles = [ft.Text(f"{respaldo} · Versión {__version__}", size=12, color=ft.Colors.ON_SURFACE_VARIANT)]
        buscar = getattr(self.app, "buscar_actualizaciones", None)
        if buscar:
            controles.append(ft.TextButton("Buscar actualizaciones", icon=ft.Icons.SYSTEM_UPDATE,
                                           on_click=lambda _: buscar(manual=True)))
        return ft.Row(controles, alignment=ft.MainAxisAlignment.CENTER, spacing=8)
