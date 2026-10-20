import re
from dataclasses import dataclass

from sqlalchemy import func, select

from arbitros.config import LADA_PAIS
from arbitros.db.database import Database
from arbitros.db.models import Arbitro
from arbitros.services.errores import ErrorValidacion
from arbitros.services.texto import es_nombre_persona, sin_acentos

FILTRO_ACTIVOS = "activos"
FILTRO_INACTIVOS = "inactivos"
FILTRO_TODOS = "todos"


@dataclass
class DatosArbitro:
    nombre: str
    telefono: str
    apodo: str = ""
    categoria: str = ""
    notas: str = ""
    activo: bool = True


def normalizar_telefono(telefono: str) -> str:
    """Quita espacios, guiones y paréntesis. Conserva un '+' inicial (lada internacional)."""
    telefono = telefono.strip()
    mas = telefono.startswith("+")
    digitos = re.sub(r"\D", "", telefono)
    return ("+" if mas else "") + digitos


DIGITOS_TELEFONO = 10


def formatear_telefono(telefono: str) -> str:
    """Formato de lectura: 10 dígitos -> 844 123 4567."""
    if len(telefono) == 10 and telefono.isdigit():
        return f"{telefono[:3]} {telefono[3:6]} {telefono[6:]}"
    return telefono


def enlace_whatsapp(telefono: str) -> str:
    """Enlace wa.me; a los números de 10 dígitos se les antepone LADA_PAIS."""
    digitos = telefono.lstrip("+")
    if not telefono.startswith("+") and len(digitos) == 10:
        digitos = LADA_PAIS + digitos
    return f"https://wa.me/{digitos}"


def _limpiar(texto: str) -> str | None:
    texto = (texto or "").strip()
    return texto or None


class ArbitroService:
    def __init__(self, db: Database):
        self.db = db

    def listar(self, busqueda: str = "", filtro: str = FILTRO_ACTIVOS) -> list[Arbitro]:
        consulta = select(Arbitro)
        if filtro == FILTRO_ACTIVOS:
            consulta = consulta.where(Arbitro.activo.is_(True))
        elif filtro == FILTRO_INACTIVOS:
            consulta = consulta.where(Arbitro.activo.is_(False))
        with self.db.sesion() as s:
            arbitros = sorted(s.scalars(consulta), key=lambda a: sin_acentos(a.nombre))
        # Filtrado en Python: ignora acentos y mayúsculas ("perez" encuentra "Pérez")
        busqueda = sin_acentos(busqueda.strip())
        if not busqueda:
            return arbitros
        digitos = re.sub(r"\D", "", busqueda)
        return [
            a
            for a in arbitros
            if busqueda in sin_acentos(" ".join(filter(None, (a.nombre, a.apodo, a.categoria))))
            or (digitos and digitos in a.telefono)
        ]

    def contar_activos(self) -> int:
        with self.db.sesion() as s:
            return s.scalar(select(func.count(Arbitro.id)).where(Arbitro.activo.is_(True)))

    def obtener(self, arbitro_id: int) -> Arbitro | None:
        with self.db.sesion() as s:
            return s.get(Arbitro, arbitro_id)

    def crear(self, datos: DatosArbitro) -> Arbitro:
        with self.db.sesion() as s:
            telefono = self._validar(s, datos)
            arbitro = Arbitro(telefono=telefono)
            self._aplicar(arbitro, datos)
            s.add(arbitro)
            s.flush()
            return arbitro

    def actualizar(self, arbitro_id: int, datos: DatosArbitro) -> Arbitro:
        with self.db.sesion() as s:
            arbitro = s.get(Arbitro, arbitro_id)
            if not arbitro:
                raise ErrorValidacion("El árbitro ya no existe.")
            arbitro.telefono = self._validar(s, datos, excluir_id=arbitro_id)
            self._aplicar(arbitro, datos)
            s.flush()
            return arbitro

    def cambiar_activo(self, arbitro_id: int, activo: bool) -> None:
        with self.db.sesion() as s:
            arbitro = s.get(Arbitro, arbitro_id)
            if arbitro:
                arbitro.activo = activo

    @staticmethod
    def _aplicar(arbitro: Arbitro, datos: DatosArbitro) -> None:
        arbitro.nombre = " ".join(datos.nombre.split())
        arbitro.apodo = _limpiar(datos.apodo)
        arbitro.categoria = _limpiar(datos.categoria)
        arbitro.notas = _limpiar(datos.notas)
        arbitro.activo = datos.activo

    @staticmethod
    def _validar(s, datos: DatosArbitro, excluir_id: int | None = None) -> str:
        errores = {}
        if not datos.nombre.strip():
            errores["nombre"] = "Escribe el nombre"
        elif not es_nombre_persona(datos.nombre.strip()):
            errores["nombre"] = "Solo letras (sin números ni símbolos)"
        if datos.apodo.strip() and not es_nombre_persona(datos.apodo.strip()):
            errores["apodo"] = "Solo letras (sin números ni símbolos)"
        telefono = normalizar_telefono(datos.telefono).lstrip("+")
        digitos = telefono
        if not digitos:
            errores["telefono"] = "Escribe el teléfono"
        elif len(digitos) != DIGITOS_TELEFONO:
            errores["telefono"] = f"Debe tener exactamente {DIGITOS_TELEFONO} dígitos (tiene {len(digitos)})"
        else:
            consulta = select(Arbitro).where(Arbitro.telefono == telefono)
            if excluir_id is not None:
                consulta = consulta.where(Arbitro.id != excluir_id)
            otro = s.scalar(consulta)
            if otro:
                errores["telefono"] = f"Ya registrado para {otro.nombre}"
        if errores:
            raise ErrorValidacion("Revisa los datos marcados.", errores)
        return telefono
