"""Filtros de escritura para los campos de texto: impiden teclear (o pegar) caracteres que no van.

Flet usa el `FilteringTextInputFormatter` de Flutter: del texto nuevo se conservan solo los
fragmentos que coinciden con la expresión. Por eso cada expresión describe UN carácter permitido
(sin ^ ni $): así un carácter no permitido simplemente no entra. Con anclas, un carácter inválido
podría vaciar el campo completo. Los servicios validan otra vez al guardar.
"""

import flet as ft

LETRAS = "a-zA-ZáéíóúÁÉÍÓÚäëïöüÄËÏÖÜñÑ"


def _permitir(caracter: str) -> ft.InputFilter:
    return ft.InputFilter(regex_string=caracter, allow=True, replacement_string="")


# Nombres de personas: letras (con acentos y ñ), espacios, punto, apóstrofo y guion. Sin números.
NOMBRE_PERSONA = _permitir(rf"[{LETRAS} .'-]")
# Usuario para entrar: sin espacios ni acentos
USUARIO = _permitir(r"[a-zA-Z0-9._-]")
# Solo dígitos (teléfono, números de jornada, minutos)
DIGITOS = _permitir(r"[0-9]")
# Dinero: dígitos y punto decimal (350 · 350.50)
MONTO = _permitir(r"[0-9.]")
# Fecha dd/mm/aaaa
FECHA = _permitir(r"[0-9/]")
# Hora: 10 · 1030 · 10:30 · 4:30 pm
HORA = _permitir(r"[0-9:. aApPmM]")

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
