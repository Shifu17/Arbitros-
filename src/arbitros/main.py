import logging

import flet as ft

from arbitros.config import rutas_por_defecto
from arbitros.db.database import Database
from arbitros.db.migrar import migrar, necesita_migrar
from arbitros.services.respaldos import PREFIJO_ACTUALIZACION, RespaldoService
from arbitros.ui.app import App

log = logging.getLogger("arbitros")


def _configurar_log(rutas) -> None:
    logging.basicConfig(
        filename=rutas.base / "arbitros.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def main(page: ft.Page) -> None:
    rutas = rutas_por_defecto()
    _configurar_log(rutas)
    try:
        db = Database.desde_archivo(rutas.db)
        if necesita_migrar(db):
            # Nueva versión de la app con cambios en la base de datos: respaldar antes de tocarla
            respaldo = RespaldoService(db, rutas).crear(prefijo=PREFIJO_ACTUALIZACION)
            log.info("Respaldo previo a migración: %s", respaldo)
        migrar(db)
    except Exception:
        log.exception("No se pudo abrir la base de datos")
        page.add(
            ft.Text(
                "No se pudo abrir la base de datos.\n"
                f"Revisa el archivo de registro en: {rutas.base / 'arbitros.log'}",
                color=ft.Colors.ERROR,
                size=16,
            )
        )
        return

    app = App(page, rutas, db)
    try:
        if app.auth.hay_usuarios():
            app.respaldos.respaldo_automatico_si_toca()
    except Exception:
        # Un respaldo fallido no debe impedir abrir la app
        log.exception("Falló el respaldo automático")
    app.iniciar()


def run() -> None:
    ft.run(main)


if __name__ == "__main__":
    run()
