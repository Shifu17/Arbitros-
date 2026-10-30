"""Rutas de datos de la aplicación.

Los datos viven fuera de la carpeta del programa (en %APPDATA%\\Arbitros) para que
reinstalar o actualizar la app nunca toque la información del usuario. Cada colegio
tiene su propia carpeta dentro de esa raíz (ver `colegios.py`).
La variable de entorno ARBITROS_DATA_DIR permite usar otra carpeta (desarrollo/pruebas).
"""

import os
import sys
from dataclasses import dataclass
from pathlib import Path

APP_NOMBRE = "Árbitros"
# Repositorio PÚBLICO de GitHub donde se publican los instaladores (GitHub Releases).
# Puede ser un repositorio solo de instaladores, distinto del código. Ver docs/publicar.md
REPO_ACTUALIZACIONES = os.environ.get("ARBITROS_REPO_ACTUALIZACIONES", "Shifu17/arbitros-releases")


def es_instalada() -> bool:
    """True cuando corre el .exe instalado (PyInstaller), no el código fuente."""
    return bool(getattr(sys, "frozen", False))
# Lada que se antepone a teléfonos de 10 dígitos para abrir WhatsApp (México)
LADA_PAIS = "52"


@dataclass(frozen=True)
class Rutas:
    base: Path

    @property
    def db(self) -> Path:
        return self.base / "arbitros.db"

    @property
    def documentos(self) -> Path:
        return self.base / "documentos"

    @property
    def respaldos(self) -> Path:
        return self.base / "respaldos"

    def crear(self) -> "Rutas":
        for carpeta in (self.base, self.documentos, self.respaldos):
            carpeta.mkdir(parents=True, exist_ok=True)
        return self


def raiz_datos() -> Path:
    override = os.environ.get("ARBITROS_DATA_DIR")
    if override:
        raiz = Path(override)
    else:
        raiz = Path(os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")) / "Arbitros"
    raiz.mkdir(parents=True, exist_ok=True)
    return raiz
