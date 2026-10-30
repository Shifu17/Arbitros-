"""Colegios de árbitros que maneja la app.

Cada colegio tiene su propia identidad (nombre, logo, colores) y su propia carpeta de
datos, así que su información nunca se mezcla con la de otro. Al abrir la app se elige
el colegio y a partir de ahí todo (tema, imágenes, recibos, reportes) usa el *activo*.
"""

from dataclasses import dataclass
from pathlib import Path

from arbitros.config import Rutas

CARPETA_ASSETS = Path(__file__).resolve().parent / "assets"


@dataclass(frozen=True)
class Colegio:
    clave: str
    nombre: str
    titulo: str  # primera línea del encabezado del menú
    subtitulo: str  # segunda línea, resaltada
    fondo: str  # menú, login y encabezados
    acento: str  # resaltados sobre el fondo
    primario: str  # botones
    primario_oscuro: str  # botones en modo oscuro (más claro, para que contraste)
    logo: str
    icono: str
    # Subcarpeta dentro de la carpeta de datos. None = la carpeta misma (datos que ya
    # existían antes de haber varios colegios).
    carpeta: str | None

    @property
    def ruta_logo(self) -> Path:
        return CARPETA_ASSETS / self.logo

    @property
    def ruta_icono(self) -> Path:
        return CARPETA_ASSETS / self.icono

    def rutas(self, raiz: Path) -> Rutas:
        return Rutas(raiz / "colegios" / self.carpeta if self.carpeta else raiz).crear()


COAHUILA = Colegio(
    clave="coahuila",
    nombre="Colegio de Árbitros de Coahuila",
    titulo="Colegio de Árbitros",
    subtitulo="de Coahuila",
    fondo="#121212",
    acento="#FEC106",
    primario="#D41014",
    primario_oscuro="#FF5A4E",
    logo="logo.png",
    icono="logo.ico",
    carpeta=None,
)

SALTILLO = Colegio(
    clave="saltillo",
    nombre="Colegio de Formación Arbitral Saltillo",
    titulo="Colegio de Formación Arbitral",
    subtitulo="Saltillo",
    fondo="#0B1F4B",
    acento="#F2B21B",
    primario="#1F4FA8",
    primario_oscuro="#4A7BDD",
    logo="logo_saltillo.png",
    icono="logo_saltillo.ico",
    carpeta="saltillo",
)

COLEGIOS = (COAHUILA, SALTILLO)

_activo = COAHUILA


def activo() -> Colegio:
    return _activo


def activar(colegio: Colegio) -> None:
    global _activo
    _activo = colegio


def por_clave(clave: str) -> Colegio | None:
    return next((c for c in COLEGIOS if c.clave == clave), None)
