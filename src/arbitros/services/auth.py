"""Usuarios, contraseñas y clave de recuperación.

La clave de recuperación se genera al crear el primer administrador y se guarda
solo como hash; sirve para restablecer la contraseña de un administrador si se olvida.
"""

import secrets

import bcrypt
from sqlalchemy import func, select

from arbitros.db.database import Database
from arbitros.db.models import ROL_ADMIN, ROLES, Configuracion, Usuario
from arbitros.services.errores import ErrorAutenticacion, ErrorValidacion

CLAVE_RECUPERACION = "clave_recuperacion_hash"
MIN_PASSWORD = 6
MAX_PASSWORD = 72  # límite de bcrypt
_ALFABETO_CLAVE = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # sin 0/O/1/I para evitar confusiones


def _hash(texto: str) -> str:
    return bcrypt.hashpw(texto.encode(), bcrypt.gensalt()).decode()


def _verificar(texto: str, hash_: str) -> bool:
    try:
        return bcrypt.checkpw(texto.encode(), hash_.encode())
    except ValueError:
        return False


def _generar_clave_recuperacion() -> str:
    grupos = ("".join(secrets.choice(_ALFABETO_CLAVE) for _ in range(4)) for _ in range(4))
    return "-".join(grupos)


def _normalizar_clave(clave: str) -> str:
    return clave.strip().upper().replace(" ", "").replace("-", "")


def _validar_password(password: str) -> None:
    if len(password) < MIN_PASSWORD:
        raise ErrorValidacion(
            f"La contraseña debe tener al menos {MIN_PASSWORD} caracteres.",
            {"password": f"Mínimo {MIN_PASSWORD} caracteres"},
        )
    if len(password.encode()) > MAX_PASSWORD:
        raise ErrorValidacion("La contraseña es demasiado larga.", {"password": "Demasiado larga"})


class AuthService:
    def __init__(self, db: Database):
        self.db = db

    def hay_usuarios(self) -> bool:
        with self.db.sesion() as s:
            return s.scalar(select(func.count(Usuario.id))) > 0

    def crear_admin_inicial(self, usuario: str, nombre: str, password: str) -> str:
        """Crea el primer administrador y devuelve la clave de recuperación (mostrarla una vez)."""
        if self.hay_usuarios():
            raise ErrorValidacion("Ya existe un usuario registrado.")
        self.crear_usuario(usuario, nombre, password, ROL_ADMIN)
        return self._regenerar_clave_recuperacion()

    def crear_usuario(self, usuario: str, nombre: str, password: str, rol: str) -> Usuario:
        usuario = usuario.strip().lower()
        nombre = nombre.strip()
        errores = {}
        if not usuario:
            errores["usuario"] = "Escribe un nombre de usuario"
        elif " " in usuario:
            errores["usuario"] = "Sin espacios"
        if not nombre:
            errores["nombre"] = "Escribe el nombre"
        if rol not in ROLES:
            errores["rol"] = "Rol inválido"
        if errores:
            raise ErrorValidacion("Revisa los datos marcados.", errores)
        _validar_password(password)
        with self.db.sesion() as s:
            if s.scalar(select(Usuario).where(Usuario.usuario == usuario)):
                raise ErrorValidacion("Ese usuario ya existe.", {"usuario": "Ya existe"})
            nuevo = Usuario(usuario=usuario, nombre=nombre, password_hash=_hash(password), rol=rol)
            s.add(nuevo)
            s.flush()
            return nuevo

    def autenticar(self, usuario: str, password: str) -> Usuario:
        with self.db.sesion() as s:
            u = s.scalar(select(Usuario).where(Usuario.usuario == usuario.strip().lower()))
            if not u or not _verificar(password, u.password_hash):
                raise ErrorAutenticacion("Usuario o contraseña incorrectos.")
            if not u.activo:
                raise ErrorAutenticacion("Este usuario está desactivado.")
            return u

    def listar_usuarios(self) -> list[Usuario]:
        with self.db.sesion() as s:
            return list(s.scalars(select(Usuario).order_by(Usuario.nombre)))

    def cambiar_password(self, usuario_id: int, actual: str, nueva: str) -> None:
        _validar_password(nueva)
        with self.db.sesion() as s:
            u = s.get(Usuario, usuario_id)
            if not u or not _verificar(actual, u.password_hash):
                raise ErrorValidacion("La contraseña actual no es correcta.", {"actual": "Incorrecta"})
            u.password_hash = _hash(nueva)

    def restablecer_password(self, usuario_id: int, nueva: str) -> None:
        """Uso de administrador: fija una contraseña nueva sin pedir la actual."""
        _validar_password(nueva)
        with self.db.sesion() as s:
            u = s.get(Usuario, usuario_id)
            if not u:
                raise ErrorValidacion("El usuario no existe.")
            u.password_hash = _hash(nueva)

    def cambiar_activo(self, usuario_id: int, activo: bool) -> None:
        with self.db.sesion() as s:
            u = s.get(Usuario, usuario_id)
            if not u:
                raise ErrorValidacion("El usuario no existe.")
            if not activo and u.es_admin and self._admins_activos(s) <= 1:
                raise ErrorValidacion("Debe quedar al menos un administrador activo.")
            u.activo = activo

    def recuperar_con_clave(self, clave: str, usuario: str, nueva: str) -> str:
        """Restablece la contraseña de un administrador. Devuelve una clave de recuperación NUEVA."""
        _validar_password(nueva)
        with self.db.sesion() as s:
            guardada = s.get(Configuracion, CLAVE_RECUPERACION)
            if not guardada or not _verificar(_normalizar_clave(clave), guardada.valor):
                raise ErrorAutenticacion("La clave de recuperación no es correcta.")
            u = s.scalar(select(Usuario).where(Usuario.usuario == usuario.strip().lower()))
            if not u or not u.es_admin:
                raise ErrorAutenticacion("Ese usuario no existe o no es administrador.")
            u.password_hash = _hash(nueva)
            u.activo = True
        return self._regenerar_clave_recuperacion()

    def _regenerar_clave_recuperacion(self) -> str:
        clave = _generar_clave_recuperacion()
        with self.db.sesion() as s:
            s.merge(Configuracion(clave=CLAVE_RECUPERACION, valor=_hash(_normalizar_clave(clave))))
        return clave

    @staticmethod
    def _admins_activos(s) -> int:
        return s.scalar(
            select(func.count(Usuario.id)).where(Usuario.rol == ROL_ADMIN, Usuario.activo.is_(True))
        )
