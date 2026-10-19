"""Modelos de la base de datos.

Cualquier cambio aquí necesita una migración nueva en db/migrations/versions/
(ver CLAUDE.md), porque las bases de datos de los usuarios ya existen.
"""

from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

ROL_ADMIN = "admin"
ROL_CONSULTA = "consulta"
ROLES = (ROL_ADMIN, ROL_CONSULTA)

TIPO_LIGA = "liga"
TIPO_TORNEO = "torneo"  # torneo corto de pocos días; sus "jornadas" son días

# Posiciones arbitrales, en orden de presentación. Se guardan como CSV de claves.
POSICIONES = {
    "central": "Central",
    "asistente_1": "Asistente 1",
    "asistente_2": "Asistente 2",
    "cuarto": "Cuarto árbitro",
}
POSICIONES_CORTAS = {"central": "C", "asistente_1": "A1", "asistente_2": "A2", "cuarto": "4°"}

ESTADO_PROGRAMADO = "programado"
ESTADO_JUGADO = "jugado"
ESTADO_SUSPENDIDO = "suspendido"
ESTADO_CANCELADO = "cancelado"
ESTADOS_PARTIDO = {
    ESTADO_PROGRAMADO: "Programado",
    ESTADO_JUGADO: "Jugado",
    ESTADO_SUSPENDIDO: "Suspendido",
    ESTADO_CANCELADO: "Cancelado",
}
# Partidos que no se juegan: no generan choques ni llevan árbitros asignados
ESTADOS_SIN_JUEGO = (ESTADO_SUSPENDIDO, ESTADO_CANCELADO)


def posiciones_a_csv(posiciones) -> str:
    """Normaliza a CSV en el orden canónico de POSICIONES, descartando claves desconocidas."""
    elegidas = set(posiciones)
    return ",".join(p for p in POSICIONES if p in elegidas)


def csv_a_posiciones(csv: str | None) -> list[str]:
    return [p for p in (csv or "").split(",") if p in POSICIONES]


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


class Liga(Base):
    """Liga de temporada o torneo corto (ver TIPO_*)."""

    __tablename__ = "ligas"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120), unique=True)
    tipo: Mapped[str] = mapped_column(String(20), default=TIPO_LIGA)
    posiciones_defecto: Mapped[str] = mapped_column(String(100), default="central")
    activa: Mapped[bool] = mapped_column(Boolean, default=True)
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    @property
    def es_torneo(self) -> bool:
        return self.tipo == TIPO_TORNEO

    @property
    def lista_posiciones(self) -> list[str]:
        return csv_a_posiciones(self.posiciones_defecto)


class Equipo(Base):
    __tablename__ = "equipos"
    __table_args__ = (UniqueConstraint("liga_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    liga_id: Mapped[int] = mapped_column(ForeignKey("ligas.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Campo(Base):
    __tablename__ = "campos"
    __table_args__ = (UniqueConstraint("liga_id", "nombre"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    liga_id: Mapped[int] = mapped_column(ForeignKey("ligas.id", ondelete="CASCADE"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    direccion: Mapped[str | None] = mapped_column(String(250))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Tarifa(Base):
    """Pago por partido para una posición en una liga. Dinero siempre en centavos."""

    __tablename__ = "tarifas"

    liga_id: Mapped[int] = mapped_column(ForeignKey("ligas.id", ondelete="CASCADE"), primary_key=True)
    posicion: Mapped[str] = mapped_column(String(20), primary_key=True)
    monto_centavos: Mapped[int] = mapped_column(Integer, default=0)


class Jornada(Base):
    """Jornada de una liga, o día de un torneo corto."""

    __tablename__ = "jornadas"
    __table_args__ = (UniqueConstraint("liga_id", "numero"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    liga_id: Mapped[int] = mapped_column(ForeignKey("ligas.id", ondelete="CASCADE"), index=True)
    numero: Mapped[int] = mapped_column(Integer)
    fecha_inicio: Mapped[date] = mapped_column(Date)
    fecha_fin: Mapped[date | None] = mapped_column(Date)
    notas: Mapped[str | None] = mapped_column(Text)


class Partido(Base):
    __tablename__ = "partidos"

    id: Mapped[int] = mapped_column(primary_key=True)
    jornada_id: Mapped[int] = mapped_column(ForeignKey("jornadas.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date)
    hora: Mapped[time] = mapped_column(Time)
    campo_id: Mapped[int | None] = mapped_column(ForeignKey("campos.id", ondelete="RESTRICT"))
    local_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="RESTRICT"))
    visitante_id: Mapped[int] = mapped_column(ForeignKey("equipos.id", ondelete="RESTRICT"))
    # Posiciones requeridas en ESTE partido (se copian de la liga y se pueden cambiar)
    posiciones: Mapped[str] = mapped_column(String(100))
    estado: Mapped[str] = mapped_column(String(20), default=ESTADO_PROGRAMADO)
    # Motivo de cancelación/suspensión (p. ej. "Lluvia"); solo aplica en ESTADOS_SIN_JUEGO
    motivo_estado: Mapped[str | None] = mapped_column(String(200))
    notas: Mapped[str | None] = mapped_column(Text)
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # lazy="joined": los servicios devuelven objetos desacoplados de la sesión
    # y la UI lee estos nombres directamente.
    campo: Mapped["Campo | None"] = relationship(lazy="joined")
    local: Mapped["Equipo"] = relationship(foreign_keys=[local_id], lazy="joined")
    visitante: Mapped["Equipo"] = relationship(foreign_keys=[visitante_id], lazy="joined")

    @property
    def lista_posiciones(self) -> list[str]:
        return csv_a_posiciones(self.posiciones)

    @property
    def se_juega(self) -> bool:
        return self.estado not in ESTADOS_SIN_JUEGO


DISP_TODO_EL_DIA = "todo_el_dia"
DISP_HORARIO = "horario"
DISP_NO_DISPONIBLE = "no_disponible"
TIPOS_DISPONIBILIDAD = {
    DISP_TODO_EL_DIA: "Todo el día",
    DISP_HORARIO: "Solo de cierta hora",
    DISP_NO_DISPONIBLE: "No disponible",
}


class Disponibilidad(Base):
    """Lo que un árbitro dijo para un día. Sin fila = no ha dicho nada (sin registrar)."""

    __tablename__ = "disponibilidad"
    __table_args__ = (UniqueConstraint("arbitro_id", "fecha"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    arbitro_id: Mapped[int] = mapped_column(ForeignKey("arbitros.id", ondelete="CASCADE"), index=True)
    fecha: Mapped[date] = mapped_column(Date, index=True)
    tipo: Mapped[str] = mapped_column(String(20))
    desde: Mapped[time | None] = mapped_column(Time)  # solo con DISP_HORARIO
    hasta: Mapped[time | None] = mapped_column(Time)
    nota: Mapped[str | None] = mapped_column(String(200))


class Asignacion(Base):
    """Árbitro asignado a una posición de un partido. Aquí se colgarán los pagos (fase 5)."""

    __tablename__ = "asignaciones"
    __table_args__ = (
        UniqueConstraint("partido_id", "posicion"),
        UniqueConstraint("partido_id", "arbitro_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    partido_id: Mapped[int] = mapped_column(ForeignKey("partidos.id", ondelete="CASCADE"), index=True)
    arbitro_id: Mapped[int] = mapped_column(ForeignKey("arbitros.id", ondelete="RESTRICT"), index=True)
    posicion: Mapped[str] = mapped_column(String(20))
    creado_en: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    arbitro: Mapped["Arbitro"] = relationship(lazy="joined")
    partido: Mapped["Partido"] = relationship(lazy="joined")
