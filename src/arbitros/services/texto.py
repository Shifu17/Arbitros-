import re
import unicodedata


def sin_acentos(texto: str) -> str:
    """Forma para comparar y ordenar: sin acentos y sin distinguir mayúsculas."""
    descompuesto = unicodedata.normalize("NFD", (texto or "").casefold())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")


DIAS = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]


def fecha_larga(d) -> str:
    """Sábado 24 de octubre"""
    return f"{DIAS[d.weekday()].capitalize()} {d.day} de {MESES[d.month - 1]}"


_NOMBRE_PERSONA = re.compile(r"[A-Za-zÁÉÍÓÚáéíóúÄËÏÖÜäëïöüÑñ .'-]+")


def es_nombre_persona(texto: str) -> bool:
    """Solo letras (con acentos y ñ), espacios, punto, apóstrofo y guion."""
    return bool(_NOMBRE_PERSONA.fullmatch(texto or ""))
