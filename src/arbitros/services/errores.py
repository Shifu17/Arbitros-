class ErrorValidacion(Exception):
    """Datos inválidos. `campos` mapea nombre de campo -> mensaje para mostrar en el formulario."""

    def __init__(self, mensaje: str, campos: dict[str, str] | None = None):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.campos = campos or {}


class ErrorAutenticacion(Exception):
    pass


class AvisosPendientes(Exception):
    """Los datos son válidos pero hay advertencias; se puede guardar repitiendo con forzar=True."""

    def __init__(self, avisos: list[str]):
        super().__init__("; ".join(avisos))
        self.avisos = avisos
