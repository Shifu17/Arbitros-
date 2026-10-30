"""Foto de cada árbitro y logo de cada liga (para la imagen del rol).

Se guardan ya ajustadas como PNG en `documentos/fotos/` y `documentos/logos/` dentro de
la carpeta de datos, así quedan en los respaldos; en la base solo va la ruta relativa.
"""

from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from arbitros.config import Rutas
from arbitros.db.database import Database
from arbitros.db.models import Arbitro, Liga
from arbitros.services.errores import ErrorValidacion

EXTENSIONES = ["jpg", "jpeg", "png", "webp"]
TAMANO_MAXIMO = 25 * 1024 * 1024
LADO_FOTO = 400
LADO_LOGO = 400


def abrir_imagen(origen: Path) -> Image.Image:
    if origen.suffix.lower().lstrip(".") not in EXTENSIONES:
        raise ErrorValidacion("Elige una imagen JPG, PNG o WEBP.")
    if not origen.is_file():
        raise ErrorValidacion("No se encontró la imagen.")
    if origen.stat().st_size > TAMANO_MAXIMO:
        raise ErrorValidacion("La imagen pesa más de 25 MB.")
    try:
        im = Image.open(origen)
        im.load()
    except (UnidentifiedImageError, OSError):
        raise ErrorValidacion("No se pudo leer la imagen.")
    # Las fotos del celular traen la orientación aparte (EXIF)
    return ImageOps.exif_transpose(im).convert("RGBA")


class ImagenService:
    def __init__(self, db: Database, rutas: Rutas):
        self.db = db
        self.rutas = rutas

    def ruta(self, relativa: str | None) -> Path | None:
        """Ruta absoluta de una imagen guardada, o None si no hay o ya no existe."""
        if not relativa:
            return None
        ruta = self.rutas.documentos / relativa
        return ruta if ruta.is_file() else None

    # --- Árbitros ---------------------------------------------------------

    def guardar_foto(self, arbitro_id: int, origen: Path) -> None:
        """Recorta la foto al centro en cuadrado y la guarda."""
        foto = ImageOps.fit(abrir_imagen(origen), (LADO_FOTO, LADO_FOTO), Image.LANCZOS, centering=(0.5, 0.4))
        self._guardar(Arbitro, arbitro_id, "foto", foto, f"fotos/arbitro_{arbitro_id}.png")

    def quitar_foto(self, arbitro_id: int) -> None:
        self._quitar(Arbitro, arbitro_id, "foto")

    # --- Ligas ------------------------------------------------------------

    def guardar_logo(self, liga_id: int, origen: Path) -> None:
        """Ajusta el logo dentro de un cuadrado (sin recortarlo) y lo guarda."""
        logo = abrir_imagen(origen)
        logo.thumbnail((LADO_LOGO, LADO_LOGO), Image.LANCZOS)
        lienzo = Image.new("RGBA", (LADO_LOGO, LADO_LOGO))
        lienzo.paste(logo, ((LADO_LOGO - logo.width) // 2, (LADO_LOGO - logo.height) // 2), logo)
        self._guardar(Liga, liga_id, "logo", lienzo, f"logos/liga_{liga_id}.png")

    def quitar_logo(self, liga_id: int) -> None:
        self._quitar(Liga, liga_id, "logo")

    # --- Internos ---------------------------------------------------------

    def _guardar(self, modelo, id_: int, campo: str, imagen: Image.Image, relativa: str) -> None:
        with self.db.sesion() as s:
            obj = s.get(modelo, id_)
            if not obj:
                raise ErrorValidacion("El registro ya no existe.")
            destino = self.rutas.documentos / relativa
            destino.parent.mkdir(parents=True, exist_ok=True)
            imagen.save(destino, format="PNG", optimize=True)
            setattr(obj, campo, relativa)

    def _quitar(self, modelo, id_: int, campo: str) -> None:
        with self.db.sesion() as s:
            obj = s.get(modelo, id_)
            if not obj or not getattr(obj, campo):
                return
            ruta = self.rutas.documentos / getattr(obj, campo)
            setattr(obj, campo, None)
        ruta.unlink(missing_ok=True)
