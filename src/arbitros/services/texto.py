import unicodedata


def sin_acentos(texto: str) -> str:
    """Forma para comparar y ordenar: sin acentos y sin distinguir mayúsculas."""
    descompuesto = unicodedata.normalize("NFD", (texto or "").casefold())
    return "".join(c for c in descompuesto if unicodedata.category(c) != "Mn")
