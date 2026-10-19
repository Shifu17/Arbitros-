from arbitros.db.database import Database
from arbitros.db.models import Configuracion


class ConfiguracionService:
    def __init__(self, db: Database):
        self.db = db

    def obtener(self, clave: str, defecto: str | None = None) -> str | None:
        with self.db.sesion() as s:
            fila = s.get(Configuracion, clave)
            return fila.valor if fila else defecto

    def guardar(self, clave: str, valor: str) -> None:
        with self.db.sesion() as s:
            s.merge(Configuracion(clave=clave, valor=valor))
