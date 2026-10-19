import logging
import os
from pathlib import Path

import flet as ft

from arbitros.services.errores import ErrorValidacion
from arbitros.services.respaldos import DIAS_ENTRE_AUTOMATICOS, PREFIJO_PREVIO, InfoRespaldo
from arbitros.ui.comunes import avisar, confirmar, encabezado, estado_vacio, fecha_legible, hace_cuanto, tarjeta

log = logging.getLogger(__name__)


def _tamano(n: int) -> str:
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


def construir(app, shell) -> ft.Control:
    return VistaRespaldos(app).construir()


class VistaRespaldos:
    def __init__(self, app):
        self.app = app
        self.page = app.page
        self.resumen = ft.Column(spacing=4)
        self.lista = ft.Column(spacing=0)

    def construir(self) -> ft.Control:
        botones = [
            ft.FilledButton("Crear respaldo ahora", icon=ft.Icons.BACKUP, on_click=self._crear),
            ft.OutlinedButton("Guardar copia en USB u otra carpeta", icon=ft.Icons.SAVE_ALT, on_click=self._crear_en),
            ft.OutlinedButton("Abrir carpeta de respaldos", icon=ft.Icons.FOLDER_OPEN, on_click=self._abrir_carpeta),
        ]
        if self.app.es_admin:
            botones.append(
                ft.OutlinedButton("Restaurar desde archivo…", icon=ft.Icons.RESTORE, on_click=self._elegir_y_restaurar)
            )
        self.refrescar(actualizar=False)
        return ft.Column(
            [
                encabezado("Respaldos", "Copias de seguridad de tus datos y documentos (cédulas)."),
                tarjeta(
                    ft.Column(
                        [
                            self.resumen,
                            ft.Text(
                                f"Al abrir la app se crea un respaldo automático si el último tiene más de "
                                f"{DIAS_ENTRE_AUTOMATICOS} días. Para mayor seguridad, guarda de vez en cuando "
                                "una copia en una USB o en la nube.",
                                color=ft.Colors.ON_SURFACE_VARIANT,
                            ),
                            ft.Row(botones, wrap=True, spacing=8, run_spacing=8),
                        ],
                        spacing=12,
                    )
                ),
                ft.Text("Respaldos guardados en esta computadora", size=18, weight=ft.FontWeight.W_500),
                self.lista,
            ],
            spacing=16,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

    def refrescar(self, actualizar: bool = True) -> None:
        respaldos = self.app.respaldos.listar()
        if respaldos:
            ultimo = respaldos[0]
            self.resumen.controls = [
                ft.Text(f"Último respaldo: {hace_cuanto(ultimo.fecha)}", size=18, weight=ft.FontWeight.W_500),
                ft.Text(fecha_legible(ultimo.fecha), color=ft.Colors.ON_SURFACE_VARIANT),
            ]
            self.lista.controls = [self._fila(r) for r in respaldos]
        else:
            self.resumen.controls = [ft.Text("Todavía no hay respaldos.", size=18, weight=ft.FontWeight.W_500)]
            self.lista.controls = [estado_vacio(ft.Icons.BACKUP, "Sin respaldos", "Pulsa «Crear respaldo ahora».")]
        if actualizar:
            self.page.update()

    def _fila(self, r: InfoRespaldo) -> ft.Control:
        if r.ruta.name.startswith(PREFIJO_PREVIO):
            tipo = "Antes de restaurar"
        else:
            tipo = "Automático" if r.automatico else "Manual"
        restaurar = None
        if self.app.es_admin:
            restaurar = ft.TextButton("Restaurar", icon=ft.Icons.RESTORE, on_click=lambda _, r=r: self._confirmar(r.ruta))
        return ft.ListTile(
            leading=ft.Icon(ft.Icons.FOLDER_ZIP),
            title=ft.Text(fecha_legible(r.fecha)),
            subtitle=ft.Text(f"{tipo} · {_tamano(r.tamano_bytes)}"),
            trailing=restaurar,
        )

    def _crear(self, _=None, destino: Path | None = None) -> None:
        try:
            ruta = self.app.respaldos.crear(destino)
        except Exception:
            log.exception("Error al crear respaldo")
            avisar(self.page, "No se pudo crear el respaldo. Revisa que haya espacio y permisos.", error=True)
            return
        avisar(self.page, f"Respaldo creado: {ruta}")
        self.refrescar()

    async def _crear_en(self, _) -> None:
        carpeta = await self.app.selector_archivos.get_directory_path("Elige dónde guardar la copia")
        if carpeta:
            self._crear(destino=Path(carpeta))

    def _abrir_carpeta(self, _) -> None:
        os.startfile(self.app.rutas.respaldos)

    async def _elegir_y_restaurar(self, _) -> None:
        archivos = await self.app.selector_archivos.pick_files(
            dialog_title="Elige el respaldo (.zip)",
            initial_directory=str(self.app.rutas.respaldos),
            file_type=ft.FilePickerFileType.CUSTOM,
            allowed_extensions=["zip"],
        )
        if archivos and archivos[0].path:
            self._confirmar(Path(archivos[0].path))

    def _confirmar(self, archivo: Path) -> None:
        def restaurar():
            try:
                self.app.restaurar_respaldo(archivo)
            except ErrorValidacion as e:
                avisar(self.page, e.mensaje, error=True)
            except Exception:
                log.exception("Error al restaurar %s", archivo)
                avisar(self.page, "No se pudo restaurar el respaldo.", error=True)

        confirmar(
            self.page,
            "Restaurar respaldo",
            f"Se reemplazarán TODOS los datos actuales por los del respaldo «{archivo.name}». "
            "Antes se guardará automáticamente una copia de lo que tienes ahora, por si necesitas regresar.",
            restaurar,
            "Restaurar",
        )
