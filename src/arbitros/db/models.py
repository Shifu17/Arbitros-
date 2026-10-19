"""Modelos de la base de datos.

Cualquier cambio aquí necesita una migración nueva en db/migrations/versions/
(ver CLAUDE.md), porque las bases de datos de los usuarios ya existen.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

ROL_ADMIN = "admin"
ROL_CONSULTA = "consulta"
ROLES = (ROL_ADMIN, ROL_CONSULTA)


class Base(DeclarativeBase):
    pass


class Configuracion(Base):
    """Pares clave/valor para ajustes de la app (tema, clave de recuperación, etc.)."""

    __tablename__ = "configuracion"

    clave: Mapped[str] = mapped_column(String(100), primary_key=True)
    valor: Mapped[str] = mapped_column(Text)


class Usuario(Base):
    __tablename__ = "usuarios"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario: Mapped[str] = mapped_column(String(50), unique=True)
    nombre: Mapped[str] = mapped_column(String(120))
    password_hash: Mapped[str] = mapped_column(String(100))
    rol: Mapped[str] = mapped_column(String(20), default=ROL_ADMIN)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def es_admin(self) -> bool:
        return self.rol == ROL_ADMIN


class Arbitro(Base):
    __tablename__ = "arbitros"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    apodo: Mapped[str | None] = mapped_column(String(60))
    # Solo dígitos (y '+' inicial opcional); ver services.arbitros.normalizar_telefono
    telefono: Mapped[str] = mapped_column(String(20), unique=True)
    categoria: Mapped[str | None] = mapped_column(String(60))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
