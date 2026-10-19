class ErrorValidacion(Exception):
    """Datos inválidos. `campos` mapea nombre de campo -> mensaje para mostrar en el formulario."""

    def __init__(self, mensaje: str, campos: dict[str, str] | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campos = campos or {}


class ErrorAutenticacion(Exception):
    pass
