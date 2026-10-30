"""Recibo de arbitrajes de un equipo partido por partido, como PNG o PDF (mismo estilo que la imagen del rol)."""

import io
from datetime import datetime

from PIL import Image, ImageDraw

from arbitros.db.models import FORMAS_PAGO
from arbitros.services.cobros import LineaCobro, ReciboEquipo
from arbitros.services.dinero import formatear_monto
from arbitros.services.rol_imagen import (
    AMARILLO_SUAVE, ANCHO, BLANCO, BORDE, FONDO, GRIS, MARGEN, NEGRO, ROJO, TEXTO, _fuente, _Lienzo, marca,
)
from arbitros.services.texto import fecha_larga

VERDE = (46, 125, 50)


def generar_png(recibo: ReciboEquipo) -> bytes:
    return _guardar(_imagen(recibo), "PNG")


def generar_pdf(recibo: ReciboEquipo) -> bytes:
    return _guardar(_imagen(recibo), "PDF")


def _imagen(recibo: ReciboEquipo) -> Image.Image:
    medidor = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    alto = _componer(_Lienzo(None, medidor), recibo)
    imagen = Image.new("RGB", (ANCHO, alto), FONDO)
    _componer(_Lienzo(ImageDraw.Draw(imagen), medidor, imagen), recibo)
    return imagen


def _guardar(imagen: Image.Image, formato: str) -> bytes:
    salida = io.BytesIO()
    if formato == "PDF":
        imagen.save(salida, format="PDF", resolution=150)
    else:
        imagen.save(salida, format="PNG", optimize=True)
    return salida.getvalue()


def _derecha(l: _Lienzo, x_derecho: int, y: int, texto: str, fuente, color) -> None:
    if l.d:
        l.d.text((x_derecho - l.medidor.textlength(texto, font=fuente), y), texto, font=fuente, fill=color)


def _componer(l: _Lienzo, r: ReciboEquipo) -> int:
    f_titulo, f_sub, f_grupo = _fuente(True, 46), _fuente(False, 30), _fuente(True, 30)
    f_normal, f_negrita, f_chico = _fuente(False, 27), _fuente(True, 27), _fuente(False, 22)
    util = ANCHO - 2 * MARGEN
    m = marca()

    lineas_enc = [("RECIBO DE ARBITRAJES", f_sub), (r.equipo.nombre.upper(), f_titulo),
                  (r.liga.nombre, f_sub), (r.periodo, f_sub)]
    tam_logo = 150
    x_texto = MARGEN + 32 + tam_logo + 28

    def encabezado(lienzo: _Lienzo, y0: int) -> int:
        yy = y0 + 32
        for i, (texto, fuente) in enumerate(lineas_enc):
            color = m.acento if i == 0 else BLANCO
            yy += lienzo.texto(x_texto, yy, texto, fuente, color, ANCHO - MARGEN - 32 - x_texto)
        return max(yy + 32 - y0, tam_logo + 64)

    y = MARGEN
    alto_enc = encabezado(_Lienzo(None, l.medidor), y)
    l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_enc), m.fondo)
    if l.d:
        encabezado(l, y)
        if m.logo.exists():
            logo = Image.open(m.logo).convert("RGBA").resize((tam_logo, tam_logo), Image.LANCZOS)
            l.imagen(logo, MARGEN + 32, y + (alto_enc - tam_logo) // 2)
    mitad = ANCHO // 2
    l.rect((MARGEN, y + alto_enc - 10, mitad, y + alto_enc), m.acento)
    l.rect((mitad, y + alto_enc - 10, ANCHO - MARGEN, y + alto_enc), m.primario)
    y += alto_enc + 32

    if not r.lineas:
        y += l.texto(MARGEN, y, "Sin partidos en este periodo.", f_normal, GRIS, util) + 24
    for linea in r.lineas:
        y += _tarjeta(l, linea, y, f_grupo, f_normal, f_negrita, f_chico) + 14

    if r.abonos:
        y += 10
        y += l.texto(MARGEN, y, "PAGOS ADELANTADOS", f_grupo, m.primario, util) + 8
        alto_linea = int(f_normal.size * 1.35)
        alto_caja = 20 + sum(alto_linea + (int(f_chico.size * 1.25) if a.nota else 0) for a in r.abonos) + 16
        l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_caja), BLANCO, BORDE)
        yy = y + 20
        for a in r.abonos:
            texto = f"{a.fecha:%d/%m/%Y}" + (f" · {FORMAS_PAGO.get(a.forma_pago, a.forma_pago)}" if a.forma_pago else "")
            l.texto(MARGEN + 28, yy, texto, f_normal, TEXTO, util - 260)
            _derecha(l, ANCHO - MARGEN - 28, yy, formatear_monto(a.monto_centavos), f_normal, VERDE)
            yy += alto_linea
            if a.nota:
                yy += l.texto(MARGEN + 28, yy, a.nota, f_chico, GRIS, util - 56)
        y += alto_caja + 14

    # Totales
    y += 10
    filas = [("Total de arbitrajes", r.total, TEXTO), ("Pagado", r.pagado, VERDE)]
    if r.a_favor:
        filas.append(("Saldo a favor", r.a_favor, VERDE))
    alto_fila = int(f_grupo.size * 1.5)
    alto_tot = 24 + alto_fila * (len(filas) + 1) + 24
    l.caja((MARGEN, y, ANCHO - MARGEN, y + alto_tot), AMARILLO_SUAVE, radio=12)
    l.rect((MARGEN, y + 6, MARGEN + 8, y + alto_tot - 6), m.primario)
    yy = y + 24
    for texto, monto, color in filas:
        l.texto(MARGEN + 32, yy, texto, f_normal, TEXTO, util)
        _derecha(l, ANCHO - MARGEN - 32, yy, formatear_monto(monto), f_negrita, color)
        yy += alto_fila
    saldo_txt = formatear_monto(r.saldo) if r.saldo else "PAGADO"
    l.texto(MARGEN + 32, yy, "Saldo pendiente", f_grupo, NEGRO, util)
    _derecha(l, ANCHO - MARGEN - 32, yy, saldo_txt, f_grupo, ROJO if r.saldo else VERDE)
    y += alto_tot + 24

    y += l.texto(MARGEN, y, f"{m.nombre} · Generado el {datetime.now():%d/%m/%Y %H:%M}", f_chico, GRIS, util)
    return y + MARGEN


def _tarjeta(l: _Lienzo, linea: LineaCobro, y: int, f_grupo, f_normal, f_negrita, f_chico) -> int:
    """Un partido: arbitraje, lo pagado y lo que debe. Devuelve su altura."""
    x0, x1 = MARGEN, ANCHO - MARGEN
    xi, xd = x0 + 28, x1 - 28
    ancho = xd - xi
    p = linea.partido

    def contenido(lienzo: _Lienzo) -> int:
        yy = y + 20
        yy += lienzo.texto(xi, yy, f"vs {linea.rival.nombre}", f_grupo, TEXTO, ancho)
        detalle = " · ".join(x for x in (f"{fecha_larga(p.fecha)} {p.hora:%H:%M}", linea.jornada,
                                         p.categoria.nombre if p.categoria else None,
                                         "Local" if linea.es_local else "Visitante") if x)
        yy += lienzo.texto(xi, yy, detalle, f_chico, GRIS, ancho) + 6
        lienzo.rect((xi, yy, xd, yy + 2), BORDE)
        yy += 12
        lienzo.texto(xi, yy, "Arbitraje", f_negrita, TEXTO, ancho)
        _derecha(lienzo, xd, yy, formatear_monto(linea.cuota), f_negrita, TEXTO)
        yy += int(f_negrita.size * 1.35)
        if linea.pagado:
            pago = "Pagado" + (f" el {linea.fecha_pago:%d/%m/%Y}" if linea.fecha_pago else "")
            if linea.forma_pago:
                pago += f" · {FORMAS_PAGO.get(linea.forma_pago, linea.forma_pago)}"
            lienzo.texto(xi, yy, pago, f_normal, VERDE, ancho - 200)
            _derecha(lienzo, xd, yy, formatear_monto(linea.pagado), f_normal, VERDE)
            yy += int(f_normal.size * 1.35)
        if linea.abonado:
            lienzo.texto(xi, yy, "Cubierto con pago adelantado", f_normal, VERDE, ancho - 200)
            _derecha(lienzo, xd, yy, formatear_monto(linea.abonado), f_normal, VERDE)
            yy += int(f_normal.size * 1.35)
        if linea.saldo:
            lienzo.texto(xi, yy, "Debe", f_negrita, ROJO, ancho)
            _derecha(lienzo, xd, yy, formatear_monto(linea.saldo), f_negrita, ROJO)
            yy += int(f_negrita.size * 1.35)
        if linea.nota:
            yy += lienzo.texto(xi, yy, linea.nota, f_chico, GRIS, ancho)
        return yy + 16 - y

    alto = contenido(_Lienzo(None, l.medidor))
    l.caja((x0, y, x1, y + alto), BLANCO, BORDE)
    if l.d:
        contenido(l)
    return alto
