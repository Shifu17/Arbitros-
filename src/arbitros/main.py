import logging

import flet as ft

from arbitros.config import raiz_datos
from arbitros.ui.app import App


def _configurar_log(raiz) -> None:
    logging.basicConfig(
        filename=raiz / "arbitros.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        encoding="utf-8",
    )


def main(page: ft.Page) -> None:
    raiz = raiz_datos()
    _configurar_log(raiz)
    app = App(page, raiz)
    app.iniciar()
    app.buscar_actualizaciones()


def run() -> None:
    ft.run(main)


if __name__ == "__main__":
    run()
