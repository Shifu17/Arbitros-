"""Los filtros se prueban con la misma regla que aplica Flet 1.0 en cada tecla.

Flet (CustomFilteringTextInputFormatter) acepta el texto nuevo si la expresión encuentra
coincidencia en él; si no, deja el texto anterior.
"""

import re

import pytest

from arbitros.ui import filtros


def _escribir(filtro, anterior: str, nuevo: str) -> str:
    return nuevo if re.search(filtro.regex_string, nuevo) else anterior


@pytest.mark.parametrize("filtro, valido", [
    (filtros.USUARIO, "coordinador"),
    (filtros.NOMBRE_PERSONA, "José Pérez"),
    (filtros.DIGITOS, "8441234567"),
    (filtros.MONTO, "350.50"),
    (filtros.FECHA, "24/10/2026"),
    (filtros.HORA, "4:30 pm"),
])
def test_se_puede_borrar_todo(filtro, valido):
    # Escribir letra por letra y luego borrar hasta dejar el campo vacío
    texto = ""
    for i in range(1, len(valido) + 1):
        texto = _escribir(filtro, texto, valido[:i])
    assert texto == valido
    for i in range(len(valido) - 1, -1, -1):
        texto = _escribir(filtro, texto, valido[:i])
    assert texto == ""


@pytest.mark.parametrize("filtro, anterior, intento", [
    (filtros.USUARIO, "ana", "ana lopez"),
    (filtros.USUARIO, "ana", "anaé"),
    (filtros.NOMBRE_PERSONA, "Juan", "Juan2"),
    (filtros.DIGITOS, "844", "844a"),
    (filtros.MONTO, "350", "350$"),
])
def test_no_entran_caracteres_no_permitidos(filtro, anterior, intento):
    assert _escribir(filtro, anterior, intento) == anterior
