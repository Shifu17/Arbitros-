"""Imagen PNG del rol (1080 px de ancho, pensada para verse en el celular).

Se dibuja en dos pasadas: la primera solo mide la altura total y la segunda dibuja.
Sin emojis: Pillow no dibuja emojis a color de forma fiable; se usan formas y colores.
"""

import io
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from arbitros import colegios
from arbitros.db.models import POSICIONES
from arbitros.services.rol import AGRUPAR_HORA, OpcionesRol, PartidoEnRol, RolJornada
from arbitros.services.texto import fecha_larga, sin_acentos

ANCHO = 1080
MARGEN = 48
NEGRO = (18, 18, 18)
AMARILLO_SUAVE = (255, 243, 205)
TEXTO = (33, 33, 33)
GRIS = (110, 110, 110)
BORDE = (222, 222, 222)
ROJO = (198, 40, 40)
NOTA = (255, 248, 225)
BLANCO = (255, 255, 255)
FONDO = (245, 245, 245)
SIN_FOTO = (225, 228, 235)
SIN_ASIGNAR = (251, 213, 213)
TAM_FOTO = 76


def _rgb(hexa: str) -> tuple[int, int, int]:
    return tuple(int(hexa[i:i + 2], 16) for i in (1, 3, 5))


@dataclass(frozen=True)
class Marca:
    """Nombre, logo y colores del colegio activo, listos para Pillow."""
    nombre: str
    logo: Path
    fondo: tuple[int, int, int]
    acento: tuple[int, int, int]
    primario: tuple[int, int, int]
    titulo_rol: str = "Rol arbitral"
    fotos_arbitros: bool = False
    logo_liga: bool = False


def marca() -> Marca:
    c = colegios.activo()
    return Marca(c.nombre, c.ruta_logo, _rgb(c.fondo), _rgb(c.acento), _rgb(c.primario),
                 c.titulo_rol, c.fotos_arbitros, c.logo_liga)


def _foto_redonda(ruta: Path, lado: int) -> Image.Image | None:
    try:
        foto = ImageOps.fit(Image.open(ruta).convert("RGBA"), (lado, lado), Image.LANCZOS)
    except OSError:
        return None
    # Máscara dibujada al cuádruple y reducida para que el borde no se vea dentado
    mascara = Image.new("L", (lado * 4, lado * 4))
    ImageDraw.Draw(mascara).ellipse((0, 0, lado * 4 - 1, lado * 4 - 1), fill=255)
    foto.putalpha(mascara.resize((lado, lado), Image.LANCZOS))
    return foto


def _iniciales(nombre: str) -> str:
    return "".join(p[0] for p in nombre.split()[:2]).upper()


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

    def circulo_con_texto(self, x: int, y: int, lado: int, relleno, texto: str, fuente, color) -> None:
        if self.d:
            self.d.ellipse((x, y, x + lado, y + lado), fill=relleno)
            self.d.text((x + lado / 2, y + lado / 2), texto, font=fuente, fill=color, anchor="mm")


def generar_png(rol: RolJornada, opciones: OpcionesRol, documentos: Path | None = None) -> bytes:
    """`documentos` es la carpeta donde están la foto de cada árbitro y el logo de la liga."""
    medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    alto = _componer(_Lienzo(None, medidor), rol, opciones, documentos)
    imagen = Image.new("RGB", (ANCHO, alto), FONDO)
    _componer(_Lienzo(ImageDraw.Draw(imagen), medidor, imagen), rol, opciones, documentos)
    salida = io.BytesIO()
    imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def _componer(l: _Lienzo, rol: RolJornada, opciones: OpcionesRol, documentos: Path | None = None) -> int:
    f_titulo, f_sub, f_grupo = _fuente(True, 46), _fuente(False, 30), _fuente(True, 30)
    f_hora, f_equipos, f_normal, f_chico = _fuente(True, 38), _fuente(True, 32), _fuente(False, 27), _fuente(False, 22)
    util = ANCHO - 2 * MARGEN
    m = marca()

    # Encabezado: se mide primero para dibujar el fondo verde detrás del texto
    fechas = rol.fechas
    lineas_enc = [(rol.liga.nombre.upper(), f_titulo), (f"{m.titulo_rol} · {rol.titulo}", f_sub)]
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
            color = BLANCO if i == 0 else m.acento if i == 1 else BLANCO
            yy += lienzo.texto(x_texto, yy, texto, fuente, color, ANCHO - MARGEN - 32 - x_texto)
        return max(yy + 32 - y0, tam_logo + 64)

    y = MARGEN
    alto_enc = encabezado(_Lienzo(None, l.medidor), y)
    l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_enc), m.fondo)
    if l.d:
        encabezado(l, y)
        ruta_logo = m.logo
        if m.logo_liga and documentos and rol.liga.logo and (documentos / rol.liga.logo).is_file():
            ruta_logo = documentos / rol.liga.logo
        if ruta_logo.exists():
            logo = Image.open(ruta_logo).convert("RGBA").resize((tam_logo, tam_logo), Image.LANCZOS)
            l.imagen(logo, MARGEN + 32, y + (alto_enc - tam_logo) // 2)
    # Franja con los dos colores del logo
    mitad = ANCHO // 2
    l.rect((MARGEN, y + alto_enc - 10, mitad, y + alto_enc), m.acento)
    l.rect((mitad, y + alto_enc - 10, ANCHO - MARGEN, y + alto_enc), m.primario)
    y += alto_enc + 32

    activos = [p for p in rol.partidos if p.se_juega]
    varias_fechas = len({p.fecha for p in activos}) > 1
    por_hora = opciones.agrupar == AGRUPAR_HORA
    # None = sin fotos; con fotos, al medir basta un diccionario vacío (miden igual que las iniciales)
    fotos = (_cargar_fotos(activos, documentos) if l.d else {}) if m.fotos_arbitros else None
    if not rol.partidos:
        y += l.texto(MARGEN, y, "No hay partidos para mostrar.", f_normal, GRIS, util) + 24

    for fecha in sorted({p.fecha for p in activos}):
        del_dia = [p for p in activos if p.fecha == fecha]
        if varias_fechas:
            y += l.texto(MARGEN, y, fecha_larga(fecha).upper(), f_grupo, m.primario, util) + 12
        if por_hora:
            grupos = [(f"{h:%H:%M}", sorted((p for p in del_dia if p.hora == h), key=lambda p: sin_acentos(p.campo)))
                      for h in sorted({p.hora for p in del_dia})]
        else:
            grupos = [(c.upper(), sorted((p for p in del_dia if p.campo == c), key=lambda p: p.hora))
                      for c in sorted({p.campo for p in del_dia}, key=sin_acentos)]
        for titulo, partidos in grupos:
            alto_titulo = int(f_grupo.size * 1.25)
            l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_titulo + 20), AMARILLO_SUAVE, radio=12)
            l.rect((MARGEN, y + 6, MARGEN + 8, y + alto_titulo + 14), m.primario)
            l.texto(MARGEN + 24, y + 10, titulo, f_grupo, NEGRO, util - 40)
            y += alto_titulo + 20 + 14
            for p in partidos:
                y += _tarjeta(l, p, y, opciones, por_hora, f_hora, f_equipos, f_normal, f_chico, fotos) + 14
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

    y += l.texto(MARGEN, y, f"{m.nombre} · Generado el {datetime.now():%d/%m/%Y %H:%M}", f_chico, GRIS, util)
    return y + MARGEN


def _cargar_fotos(partidos: list[PartidoEnRol], documentos: Path | None) -> dict[int, Image.Image]:
    """Foto redonda de cada árbitro del rol que tenga foto guardada (por id)."""
    fotos = {}
    for p in partidos:
        for a in p.arbitros:
            arb = a.arbitro
            if arb and arb.id not in fotos and arb.foto and documentos and (documentos / arb.foto).is_file():
                foto = _foto_redonda(documentos / arb.foto, TAM_FOTO)
                if foto:
                    fotos[arb.id] = foto
    return fotos


def _tarjeta(l: _Lienzo, p: PartidoEnRol, y: int, opciones: OpcionesRol, por_hora: bool,
             f_hora, f_equipos, f_normal, f_chico, fotos: dict[int, Image.Image] | None = None) -> int:
    """Tarjeta de un partido. Devuelve su altura. Con `fotos` (no None) cada árbitro lleva su foto."""
    x0, x1 = MARGEN, ANCHO - MARGEN
    col_izq = 150
    ancho_der = x1 - x0 - col_izq - 48
    primario = marca().primario

    def contenido(lienzo: _Lienzo) -> int:
        yy = y + 20
        izquierda = p.campo if por_hora else f"{p.hora:%H:%M}"
        fuente_izq = f_normal if por_hora else f_hora
        lienzo.texto(x0 + 24, yy, izquierda, fuente_izq, primario, col_izq - 16)
        xd = x0 + 24 + col_izq
        yy += lienzo.texto(xd, yy, p.equipos, f_equipos, TEXTO, ancho_der)
        subtitulo = " · ".join(x for x in (p.categoria, p.modalidad) if x)
        if subtitulo:
            yy += lienzo.texto(xd, yy, subtitulo, f_chico, GRIS, ancho_der)
        yy += 6
        if fotos is not None:
            return _arbitros_con_foto(lienzo, p, xd, yy, ancho_der, opciones, fotos, f_normal, f_chico) + 20 - y
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


def _arbitros_con_foto(l: _Lienzo, p: PartidoEnRol, x: int, y: int, ancho: int, opciones: OpcionesRol,
                       fotos: dict[int, Image.Image], f_normal, f_chico) -> int:
    """Un renglón por árbitro: foto redonda (o sus iniciales), nombre y posición. Devuelve la nueva y."""
    f_iniciales = _fuente(True, 28)
    x_texto = x + TAM_FOTO + 18
    ancho_texto = ancho - TAM_FOTO - 18
    for a in p.arbitros:
        falta = a.arbitro is None
        foto = None if falta else fotos.get(a.arbitro.id)
        if foto:
            l.imagen(foto, x, y)
        elif falta:
            l.circulo_con_texto(x, y, TAM_FOTO, SIN_ASIGNAR, "?", f_iniciales, ROJO)
        else:
            l.circulo_con_texto(x, y, TAM_FOTO, SIN_FOTO, _iniciales(a.arbitro.nombre), f_iniciales, GRIS)
        nombre = a.nombre(opciones.usar_apodos)
        alto_texto = (_Lienzo(None, l.medidor).texto(0, 0, nombre, f_normal, TEXTO, ancho_texto)
                      + int(f_chico.size * 1.25))
        yy = y + max(0, (TAM_FOTO - alto_texto) // 2)
        yy += l.texto(x_texto, yy, nombre, f_normal, ROJO if falta else TEXTO, ancho_texto)
        l.texto(x_texto, yy, POSICIONES[a.posicion], f_chico, GRIS, ancho_texto)
        y += max(TAM_FOTO, alto_texto) + 12
    return y
