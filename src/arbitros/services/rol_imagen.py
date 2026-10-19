"""Imagen PNG del rol (1080 px de ancho, pensada para verse en el celular).

Se dibuja en dos pasadas: la primera solo mide la altura total y la segunda dibuja.
Sin emojis: Pillow no dibuja emojis a color de forma fiable; se usan formas y colores.
"""

import io
import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from arbitros.config import ORGANIZACION
from arbitros.db.models import POSICIONES
from arbitros.services.rol import AGRUPAR_HORA, OpcionesRol, PartidoEnRol, RolJornada
from arbitros.services.texto import fecha_larga, sin_acentos

ANCHO = 1080
MARGEN = 48
# Colores del Colegio de Árbitros de Coahuila
NEGRO = (18, 18, 18)
AMARILLO_MARCA = (254, 193, 6)
ROJO_MARCA = (212, 16, 20)
AMARILLO_SUAVE = (255, 243, 205)
TEXTO = (33, 33, 33)
GRIS = (110, 110, 110)
BORDE = (222, 222, 222)
ROJO = (198, 40, 40)
NOTA = (255, 248, 225)
BLANCO = (255, 255, 255)
FONDO = (245, 245, 245)
LOGO = Path(__file__).resolve().parent.parent / "assets" / "logo.png"


def _fuente(negrita: bool, tamano: int) -> ImageFont.FreeTypeFont:
    carpeta = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
    nombres = ["segoeuib.ttf", "arialbd.ttf"] if negrita else ["segoeui.ttf", "arial.ttf"]
    for nombre in nombres:
        ruta = carpeta / nombre
        if ruta.exists():
            return ImageFont.truetype(str(ruta), tamano)
    return ImageFont.load_default(tamano)


class _Lienzo:
    """Dibuja (o solo mide, si `dibujo` es None) y lleva la posición vertical."""

    def __init__(self, dibujo: ImageDraw.ImageDraw | None, medidor: ImageDraw.ImageDraw,
                 lienzo: Image.Image | None = None):
        self.d = dibujo
        self.medidor = medidor
        self.lienzo = lienzo

    def envolver(self, texto: str, fuente, ancho_max: int) -> list[str]:
        palabras, lineas, actual = texto.split(), [], ""
        for palabra in palabras:
            prueba = f"{actual} {palabra}".strip()
            if self.medidor.textlength(prueba, font=fuente) <= ancho_max or not actual:
                actual = prueba
            else:
                lineas.append(actual)
                actual = palabra
        if actual:
            lineas.append(actual)
        return lineas or [""]

    def texto(self, x: int, y: int, texto: str, fuente, color, ancho_max: int, tachado: bool = False,
              interlineado: float = 1.25) -> int:
        """Escribe con ajuste de línea. Devuelve la altura usada."""
        alto_linea = int(fuente.size * interlineado)
        lineas = self.envolver(texto, fuente, ancho_max)
        if self.d:
            for i, linea in enumerate(lineas):
                yy = y + i * alto_linea
                self.d.text((x, yy), linea, font=fuente, fill=color)
                if tachado:
                    largo = self.medidor.textlength(linea, font=fuente)
                    medio = yy + fuente.size * 0.6
                    self.d.line((x, medio, x + largo, medio), fill=color, width=2)
        return alto_linea * len(lineas)

    def imagen(self, im: Image.Image, x: int, y: int) -> None:
        if self.d:
            self.lienzo.paste(im, (x, y), im)

    def rect(self, xy, relleno) -> None:
        if self.d:
            self.d.rectangle(xy, fill=relleno)

    def caja(self, xy, relleno, borde=None, radio: int = 16) -> None:
        if self.d:
            self.d.rounded_rectangle(xy, radius=radio, fill=relleno, outline=borde, width=2 if borde else 0)

    def punto(self, x: int, y: int, color) -> None:
        if self.d:
            self.d.ellipse((x, y, x + 12, y + 12), fill=color)


def generar_png(rol: RolJornada, opciones: OpcionesRol) -> bytes:
    medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    alto = _componer(_Lienzo(None, medidor), rol, opciones)
    imagen = Image.new("RGB", (ANCHO, alto), FONDO)
    _componer(_Lienzo(ImageDraw.Draw(imagen), medidor, imagen), rol, opciones)
    salida = io.BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def _componer(l: _Lienzo, rol: RolJornada, opciones: OpcionesRol) -> int:
    f_titulo, f_sub, f_grupo = _fuente(True, 46), _fuente(False, 30), _fuente(True, 30)
    f_hora, f_equipos, f_normal, f_chico = _fuente(True, 38), _fuente(True, 32), _fuente(False, 27), _fuente(False, 22)
    util = ANCHO - 2 * MARGEN

    # Encabezado: se mide primero para dibujar el fondo verde detrás del texto
    fechas = rol.fechas
    lineas_enc = [(rol.liga.nombre.upper(), f_titulo), (f"Rol arbitral · {rol.titulo}", f_sub)]
    if fechas:
        lineas_enc.append((fecha_larga(fechas[0]) if len(fechas) == 1
                           else f"{fecha_larga(fechas[0])} al {fecha_larga(fechas[-1]).lower()}", f_sub))
    categorias = sorted({p.categoria for p in rol.partidos if p.categoria}) if opciones.categoria_id else []
    if categorias:
        lineas_enc.append(("Categoría: " + ", ".join(categorias), f_sub))

    tam_logo = 150
    x_texto = MARGEN + 32 + tam_logo + 28

    def encabezado(lienzo: _Lienzo, y0: int) -> int:
        yy = y0 + 32
        for i, (texto, fuente) in enumerate(lineas_enc):
            color = BLANCO if i == 0 else AMARILLO_MARCA if i == 1 else BLANCO
            yy += lienzo.texto(x_texto, yy, texto, fuente, color, ANCHO - MARGEN - 32 - x_texto)
        return max(yy + 32 - y0, tam_logo + 64)

    y = MARGEN
    alto_enc = encabezado(_Lienzo(None, l.medidor), y)
    l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_enc), NEGRO)
    if l.d:
        encabezado(l, y)
        if LOGO.exists():
            logo = Image.open(LOGO).convert("RGBA").resize((tam_logo, tam_logo), Image.LANCZOS)
            l.imagen(logo, MARGEN + 32, y + (alto_enc - tam_logo) // 2)
    # Franja amarilla y roja como en el logo
    mitad = ANCHO // 2
    l.rect((MARGEN, y + alto_enc - 10, mitad, y + alto_enc), AMARILLO_MARCA)
    l.rect((mitad, y + alto_enc - 10, ANCHO - MARGEN, y + alto_enc), ROJO_MARCA)
    y += alto_enc + 32

    activos = [p for p in rol.partidos if p.se_juega]
    varias_fechas = len({p.fecha for p in activos}) > 1
    por_hora = opciones.agrupar == AGRUPAR_HORA
    if not rol.partidos:
        y += l.texto(MARGEN, y, "No hay partidos para mostrar.", f_normal, GRIS, util) + 24

    for fecha in sorted({p.fecha for p in activos}):
        del_dia = [p for p in activos if p.fecha == fecha]
        if varias_fechas:
            y += l.texto(MARGEN, y, fecha_larga(fecha).upper(), f_grupo, ROJO_MARCA, util) + 12
        if por_hora:
            grupos = [(f"{h:%H:%M}", sorted((p for p in del_dia if p.hora == h), key=lambda p: sin_acentos(p.campo)))
                      for h in sorted({p.hora for p in del_dia})]
        else:
            grupos = [(c.upper(), sorted((p for p in del_dia if p.campo == c), key=lambda p: p.hora))
                      for c in sorted({p.campo for p in del_dia}, key=sin_acentos)]
        for titulo, partidos in grupos:
            alto_titulo = int(f_grupo.size * 1.25)
            l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_titulo + 20), AMARILLO_SUAVE, radio=12)
            l.rect((MARGEN, y + 6, MARGEN + 8, y + alto_titulo + 14), ROJO_MARCA)
            l.texto(MARGEN + 24, y + 10, titulo, f_grupo, NEGRO, util - 40)
            y += alto_titulo + 20 + 14
            for p in partidos:
                y += _tarjeta(l, p, y, opciones, por_hora, f_hora, f_equipos, f_normal, f_chico) + 14
            y += 14

    cancelados = [p for p in rol.partidos if not p.se_juega]
    if cancelados:
        y += l.texto(MARGEN, y, "CANCELADOS / SUSPENDIDOS", f_grupo, ROJO, util) + 8
        for p in sorted(cancelados, key=lambda p: (p.fecha, p.hora)):
            dia = f"{fecha_larga(p.fecha)} · " if varias_fechas else ""
            y += l.texto(MARGEN, y, f"{dia}{p.hora:%H:%M} {p.campo} · {p.equipos}", f_normal, GRIS, util, tachado=True)
            motivo = p.estado.capitalize() + (f": {p.motivo}" if p.motivo else "")
            y += l.texto(MARGEN + 24, y, motivo, f_chico, ROJO, util - 24) + 10
        y += 14

    if rol.faltantes:
        y += l.texto(MARGEN, y, rol.texto_faltantes, f_normal, ROJO, util) + 16

    nota = opciones.nota.strip()
    if nota:
        alto_nota = _Lienzo(None, l.medidor).texto(0, 0, nota, f_normal, TEXTO, util - 48)
        l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_nota + 40), NOTA, radio=12)
        l.texto(MARGEN + 24, y + 20, nota, f_normal, TEXTO, util - 48)
        y += alto_nota + 40 + 20

    y += l.texto(MARGEN, y, f"{ORGANIZACION} · Generado el {datetime.now():%d/%m/%Y %H:%M}", f_chico, GRIS, util)
    return y + MARGEN


def _tarjeta(l: _Lienzo, p: PartidoEnRol, y: int, opciones: OpcionesRol, por_hora: bool,
             f_hora, f_equipos, f_normal, f_chico) -> int:
    """Tarjeta de un partido. Devuelve su altura."""
    x0, x1 = MARGEN, ANCHO - MARGEN
    col_izq = 150
    ancho_der = x1 - x0 - col_izq - 48

    def contenido(lienzo: _Lienzo) -> int:
        yy = y + 20
        izquierda = p.campo if por_hora else f"{p.hora:%H:%M}"
        fuente_izq = f_normal if por_hora else f_hora
        lienzo.texto(x0 + 24, yy, izquierda, fuente_izq, ROJO_MARCA, col_izq - 16)
        xd = x0 + 24 + col_izq
        yy += lienzo.texto(xd, yy, p.equipos, f_equipos, TEXTO, ancho_der)
        subtitulo = " · ".join(x for x in (p.categoria, p.modalidad) if x)
        if subtitulo:
            yy += lienzo.texto(xd, yy, subtitulo, f_chico, GRIS, ancho_der)
        yy += 6
        for a in p.arbitros:
            falta = a.arbitro is None
            lienzo.punto(xd, yy + 14, ROJO if falta else NEGRO)
            yy += lienzo.texto(xd + 22, yy, f"{POSICIONES[a.posicion]}: {a.nombre(opciones.usar_apodos)}",
                               f_normal, ROJO if falta else TEXTO, ancho_der - 22)
        return yy + 20 - y

    alto = contenido(_Lienzo(None, l.medidor))
    l.caja((x0, y, x1, y + alto), BLANCO, BORDE)
    if l.d:
        contenido(l)
    return alto
