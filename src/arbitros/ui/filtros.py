"""Filtros de escritura para los campos de texto: impiden teclear (o pegar) caracteres que no van.

Flet 1.0 compara el texto COMPLETO que quedaría tras cada cambio con la expresión y, si no
coincide, descarta el cambio (deja el texto anterior). Por eso cada expresión describe el campo
entero con anclas y `*`, para que el campo vacío también sea válido: con un patrón de un solo
carácter no se podía borrar la última letra y sí se colaban caracteres no permitidos.
Los servicios validan otra vez al guardar.
"""

import flet as ft

LETRAS = "a-zA-ZáéíóúÁÉÍÓÚäëïöüÄËÏÖÜñÑ"


def solo(caracteres: str) -> ft.InputFilter:
    """Filtro que solo deja escribir `caracteres` (contenido de una clase de regex, p. ej. "0-9")."""
    return ft.InputFilter(regex_string=rf"^[{caracteres}]*$", allow=True, replacement_string="")


# Nombres de personas: letras (con acentos y ñ), espacios, punto, apóstrofo y guion. Sin números.
NOMBRE_PERSONA = solo(rf"{LETRAS} .'-")
# Usuario para entrar: sin espacios ni acentos
USUARIO = solo(r"a-zA-Z0-9._-")
# Solo dígitos (teléfono, números de jornada, minutos)
DIGITOS = solo(r"0-9")
# Dinero: dígitos y punto decimal (350 · 350.50)
MONTO = solo(r"0-9.")
# Fecha dd/mm/aaaa
FECHA = solo(r"0-9/")
# Hora: 10 · 1030 · 10:30 · 4:30 pm
HORA = solo(r"0-9:. aApPmM")

DIGITOS_TELEFONO = 10


def campo_telefono(valor: str = "", **kwargs) -> ft.TextField:
    """Teléfono de 10 dígitos: solo deja escribir números y no más de 10."""
    return ft.TextField(
        label=kwargs.pop("label", "Teléfono (WhatsApp) *"),
        value=valor,
        input_filter=DIGITOS,
        max_length=DIGITOS_TELEFONO,
        keyboard_type=ft.KeyboardType.PHONE,
        prefix_icon=ft.Icons.PHONE,
        helper=kwargs.pop("helper", "10 dígitos, sin espacios"),
        **kwargs,
    )
