"""El dinero se guarda siempre como entero en centavos para evitar errores de redondeo."""

import re


def a_centavos(texto: str) -> int:
    """'350', '$350.50', '1,200' -> centavos. Vacío = 0. ValueError si no es un monto válido."""
    limpio = re.sub(r"[\s$,]", "", texto or "")
    if not limpio:
        return 0
    if not re.fullmatch(r"\d+(\.\d{1,2})?", limpio):
        raise ValueError(f"Monto inválido: {texto!r}")
    pesos, _, decimales = limpio.partition(".")
    return int(pesos) * 100 + int((decimales or "0").ljust(2, "0"))


def formatear_monto(centavos: int) -> str:
    pesos, resto = divmod(centavos, 100)
    texto = f"${pesos:,}"
    return f"{texto}.{resto:02d}" if resto else texto


def monto_editable(centavos: int) -> str:
    """Valor para precargar un campo de texto: '350' o '350.50'."""
    pesos, resto = divmod(centavos, 100)
    return f"{pesos}.{resto:02d}" if resto else str(pesos)
