"""Dibuja el logo general de la app (silbato y tarjetas), sin marca de ningún colegio.

    .\\.venv\\Scripts\\python packaging\\generar_logo_arbitros.py

Genera `assets/logo_arbitros.png` y `assets/logo_arbitros.ico`. Se usa en la pantalla de
selección de colegio, en el ejecutable y en el instalador.
"""

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parent.parent / "src" / "arbitros" / "assets"
LIENZO = 2048  # se dibuja grande y se reduce para suavizar los bordes
ESCALA = LIENZO / 1024

VERDE_CANCHA = "#0E6B46"
VERDE_OSCURO = "#0A4A31"
BLANCO = "#F5F5F5"
AMARILLO = "#FEC106"
ROJO = "#D41014"
TINTA = "#16201C"


def _p(*valores: float) -> list[float]:
    return [v * ESCALA for v in valores]


def _tarjeta(color: str, angulo: float, centro: tuple[float, float]) -> Image.Image:
    capa = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
    ImageDraw.Draw(capa).rounded_rectangle(_p(512 - 118, 512 - 170, 512 + 118, 512 + 170), radius=30 * ESCALA,
                                           fill=color, outline=TINTA, width=int(14 * ESCALA))
    capa = capa.rotate(angulo, resample=Image.BICUBIC)
    desplazada = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
    desplazada.paste(capa, (int((centro[0] - 512) * ESCALA), int((centro[1] - 512) * ESCALA)))
    return desplazada


def _silbato(d: ImageDraw.ImageDraw, color: str, grosor: float = 0) -> None:
    """Silueta del silbato; con `grosor` se dibuja más gruesa, para el contorno."""
    g = grosor
    d.ellipse(_p(285 - g, 480 - g, 625 + g, 820 + g), fill=color)  # cámara
    d.rounded_rectangle(_p(450 - g, 480 - g, 850 + g, 615 + g), radius=(22 + g) * ESCALA, fill=color)  # boquilla
    d.ellipse(_p(150 - g, 585 - g, 300 + g, 735 + g), fill=color)  # argolla


def dibujar() -> Image.Image:
    img = Image.new("RGBA", (LIENZO, LIENZO), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse(_p(12, 12, 1012, 1012), fill=BLANCO)
    d.ellipse(_p(40, 40, 984, 984), fill=VERDE_CANCHA)
    # Línea central y círculo de la cancha, discretos
    d.ellipse(_p(232, 232, 792, 792), outline=VERDE_OSCURO, width=int(14 * ESCALA))
    d.line(_p(40, 512, 984, 512), fill=VERDE_OSCURO, width=int(14 * ESCALA))

    img.alpha_composite(_tarjeta(AMARILLO, 16, (405, 345)))
    img.alpha_composite(_tarjeta(ROJO, -14, (620, 335)))

    d = ImageDraw.Draw(img)
    _silbato(d, TINTA, grosor=16)
    _silbato(d, BLANCO)
    d.ellipse(_p(192, 627, 258, 693), fill=VERDE_CANCHA)  # hueco de la argolla
    d.ellipse(_p(390, 585, 520, 715), fill=TINTA)  # bolita
    d.polygon(_p(560, 480, 680, 480, 640, 545, 560, 545), fill=TINTA)  # ranura
    return img.resize((512, 512), Image.LANCZOS)


def main() -> None:
    logo = dibujar()
    logo.save(ASSETS / "logo_arbitros.png")
    logo.save(ASSETS / "logo_arbitros.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])


if __name__ == "__main__":
    main()
