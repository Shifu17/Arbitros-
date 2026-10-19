"""Asignación de árbitros a partidos.

Errores duros: partido cancelado, posición que el partido no lleva, árbitro
inactivo o repetido en el mismo partido. Todo lo demás son *avisos* (no ha
dicho su disponibilidad, no está disponible, fuera de su horario, se le cruza
otro partido): se lanza AvisosPendientes y la UI puede asignar con forzar=True.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import func, select

from arbitros.db.database import Database
from arbitros.db.models import (
    DISP_HORARIO,
    DISP_NO_DISPONIBLE,
    ESTADOS_SIN_JUEGO,
    POSICIONES,
    Arbitro,
    Asignacion,
    Disponibilidad,
    Partido,
)
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.errores import AvisosPendientes, ErrorValidacion
from arbitros.services.texto import sin_acentos

CLAVE_DURACION = "duracion_partido_min"
CLAVE_DESCANSO = "minutos_entre_partidos"
DURACION_DEFECTO = 60
DESCANSO_DEFECTO = 30

# Orden de los candidatos en el selector: primero los que no tienen ningún problema
LIBRE = "libre"
SIN_REGISTRAR = "sin_registrar"
CONFLICTO = "conflicto"
NO_DISPONIBLE = "no_disponible"
ORDEN_ESTADO = {LIBRE: 0, SIN_REGISTRAR: 1, CONFLICTO: 2, NO_DISPONIBLE: 3}


@dataclass
class Ajustes:
    duracion_min: int
    descanso_min: int


@dataclass
class Candidato:
    arbitro: Arbitro
    estado: str
    avisos: list[str] = field(default_factory=list)
    partidos_dia: int = 0
    posicion_en_partido: str | None = None  # si ya está en este partido, en qué posición


def _minutos(h) -> int:
    return h.hour * 60 + h.minute


def _hhmm(minutos: int) -> str:
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


class AsignacionService:
    def __init__(self, db: Database, config: ConfiguracionService):
        self.db = db
        self.config = config

    # --- Ajustes ------------------------------------------------------------

    def ajustes(self) -> Ajustes:
        return Ajustes(
            int(self.config.obtener(CLAVE_DURACION, str(DURACION_DEFECTO))),
            int(self.config.obtener(CLAVE_DESCANSO, str(DESCANSO_DEFECTO))),
        )

    def guardar_ajustes(self, duracion_min: int, descanso_min: int) -> None:
        errores = {}
        if not 15 <= duracion_min <= 240:
            errores["duracion"] = "Entre 15 y 240 minutos"
        if not 0 <= descanso_min <= 240:
            errores["descanso"] = "Entre 0 y 240 minutos"
        if errores:
            raise ErrorValidacion("Revisa los valores.", errores)
        self.config.guardar(CLAVE_DURACION, str(duracion_min))
        self.config.guardar(CLAVE_DESCANSO, str(descanso_min))

    # --- Consultas ---------------------------------------------------------

    def de_jornada(self, jornada_id: int) -> dict[int, dict[str, Asignacion]]:
        """{partido_id: {posicion: Asignacion}}"""
        consulta = select(Asignacion).join(Partido, Asignacion.partido_id == Partido.id).where(
            Partido.jornada_id == jornada_id)
        resultado: dict[int, dict[str, Asignacion]] = {}
        with self.db.sesion() as s:
            for a in s.scalars(consulta).unique():
                resultado.setdefault(a.partido_id, {})[a.posicion] = a
        return resultado

    def de_partidos(self, partido_ids: list[int]) -> dict[int, dict[str, Asignacion]]:
        """{partido_id: {posicion: Asignacion}} para varios partidos de cualquier jornada."""
        resultado: dict[int, dict[str, Asignacion]] = {}
        if not partido_ids:
            return resultado
        with self.db.sesion() as s:
            for x in s.scalars(select(Asignacion).where(Asignacion.partido_id.in_(partido_ids))).unique():
                resultado.setdefault(x.partido_id, {})[x.posicion] = x
        return resultado

    def de_partido(self, partido_id: int) -> dict[str, Asignacion]:
        with self.db.sesion() as s:
            return {a.posicion: a for a in s.scalars(select(Asignacion).where(Asignacion.partido_id == partido_id)).unique()}

    def partidos_por_arbitro(self, desde: date, hasta: date) -> dict[tuple[int, date], int]:
        """{(arbitro_id, fecha): número de partidos que se juegan} en el rango."""
        consulta = (
            select(Asignacion.arbitro_id, Partido.fecha, func.count(Asignacion.id))
            .join(Partido, Asignacion.partido_id == Partido.id)
            .where(Partido.fecha.between(desde, hasta), Partido.estado.not_in(ESTADOS_SIN_JUEGO))
            .group_by(Asignacion.arbitro_id, Partido.fecha)
        )
        with self.db.sesion() as s:
            return {(a, f): n for a, f, n in s.execute(consulta)}

    def hay_asignaciones(self) -> bool:
        with self.db.sesion() as s:
            return bool(s.scalar(select(func.count(Asignacion.id))))

    def faltantes(self, partidos: list[Partido], asignaciones: dict[int, dict[str, Asignacion]]) -> int:
        """Posiciones sin árbitro en los partidos que sí se juegan."""
        return sum(
            1 for p in partidos if p.se_juega for pos in p.lista_posiciones if pos not in asignaciones.get(p.id, {})
        )

    def candidatos(self, partido_id: int, posicion: str) -> list[Candidato]:
        """Todos los árbitros activos con su situación para este partido, mejores primero."""
        ajustes = self.ajustes()
        with self.db.sesion() as s:
            partido = s.get(Partido, partido_id)
            arbitros = list(s.scalars(select(Arbitro).where(Arbitro.activo.is_(True))))
            disponibilidad = {d.arbitro_id: d for d in s.scalars(
                select(Disponibilidad).where(Disponibilidad.fecha == partido.fecha))}
            del_dia = self._asignaciones_del_dia(s, partido.fecha)
        en_partido = {a.arbitro_id: a.posicion for a in del_dia if a.partido_id == partido_id}
        resultado = []
        for arbitro in arbitros:
            otras = [a for a in del_dia if a.arbitro_id == arbitro.id and a.partido_id != partido_id]
            estado, avisos = self._evaluar(arbitro, partido, disponibilidad.get(arbitro.id), otras, ajustes)
            resultado.append(Candidato(arbitro, estado, avisos, len(otras), en_partido.get(arbitro.id)))
        # Mejores primero; a igualdad, quien tiene menos partidos ese día (reparte la carga)
        resultado.sort(key=lambda c: (ORDEN_ESTADO[c.estado], c.partidos_dia, sin_acentos(c.arbitro.nombre)))
        return resultado

    def revisar_jornada(self, jornada_id: int) -> dict[int, list[str]]:
        """Problemas actuales de cada asignación de la jornada: {asignacion_id: avisos}.

        Sirve para detectar choques que aparecen después (se cambió la hora de un
        partido, el árbitro avisó que no puede, etc.).
        """
        ajustes = self.ajustes()
        problemas = {}
        with self.db.sesion() as s:
            asignaciones = list(s.scalars(
                select(Asignacion).join(Partido, Asignacion.partido_id == Partido.id)
                .where(Partido.jornada_id == jornada_id, Partido.estado.not_in(ESTADOS_SIN_JUEGO))).unique())
            cache_dia: dict[date, list[Asignacion]] = {}
            for a in asignaciones:
                p = a.partido
                if p.fecha not in cache_dia:
                    cache_dia[p.fecha] = self._asignaciones_del_dia(s, p.fecha)
                otras = [x for x in cache_dia[p.fecha] if x.arbitro_id == a.arbitro_id and x.partido_id != p.id]
                disp = s.scalar(select(Disponibilidad).where(
                    Disponibilidad.arbitro_id == a.arbitro_id, Disponibilidad.fecha == p.fecha))
                _, avisos = self._evaluar(a.arbitro, p, disp, otras, ajustes)
                if avisos:
                    problemas[a.id] = avisos
        return problemas

    # --- Cambios -----------------------------------------------------------

    def asignar(self, partido_id: int, posicion: str, arbitro_id: int, forzar: bool = False) -> Asignacion:
        ajustes = self.ajustes()
        with self.db.sesion() as s:
            partido = s.get(Partido, partido_id)
            arbitro = s.get(Arbitro, arbitro_id)
            if not partido:
                raise ErrorValidacion("El partido ya no existe.")
            if not partido.se_juega:
                raise ErrorValidacion("El partido está cancelado o suspendido; no lleva árbitros.")
            if posicion not in partido.lista_posiciones:
                raise ErrorValidacion(f"Este partido no lleva {POSICIONES.get(posicion, posicion)}.")
            if not arbitro or not arbitro.activo:
                raise ErrorValidacion("El árbitro no existe o está desactivado.")
            actuales = {a.posicion: a for a in s.scalars(
                select(Asignacion).where(Asignacion.partido_id == partido_id)).unique()}
            for pos, a in actuales.items():
                if a.arbitro_id == arbitro_id and pos != posicion:
                    raise ErrorValidacion(f"{arbitro.nombre} ya está como {POSICIONES[pos]} en este partido.")
            if not forzar:
                otras = [a for a in self._asignaciones_del_dia(s, partido.fecha)
                         if a.arbitro_id == arbitro_id and a.partido_id != partido_id]
                disp = s.scalar(select(Disponibilidad).where(
                    Disponibilidad.arbitro_id == arbitro_id, Disponibilidad.fecha == partido.fecha))
                _, avisos = self._evaluar(arbitro, partido, disp, otras, ajustes)
                if avisos:
                    raise AvisosPendientes(avisos)
            existente = actuales.get(posicion)
            if existente:
                existente.arbitro_id = arbitro_id
                asignacion_id = existente.id
            else:
                nueva = Asignacion(partido_id=partido_id, arbitro_id=arbitro_id, posicion=posicion)
                s.add(nueva)
                s.flush()
                asignacion_id = nueva.id
        with self.db.sesion() as s:
            return s.get(Asignacion, asignacion_id)

    def quitar(self, partido_id: int, posicion: str) -> None:
        with self.db.sesion() as s:
            a = s.scalar(select(Asignacion).where(Asignacion.partido_id == partido_id, Asignacion.posicion == posicion))
            if a:
                s.delete(a)

    # --- Internos ----------------------------------------------------------

    @staticmethod
    def _asignaciones_del_dia(s, fecha: date) -> list[Asignacion]:
        """Asignaciones de cualquier liga en partidos de ese día que sí se juegan."""
        return list(s.scalars(
            select(Asignacion).join(Partido, Asignacion.partido_id == Partido.id)
            .where(Partido.fecha == fecha, Partido.estado.not_in(ESTADOS_SIN_JUEGO))).unique())

    @staticmethod
    def _evaluar(arbitro: Arbitro, partido: Partido, disp: Disponibilidad | None,
                 otras: list[Asignacion], ajustes: Ajustes) -> tuple[str, list[str]]:
        nombre = arbitro.apodo or arbitro.nombre.split()[0]
        inicio = _minutos(partido.hora)
        fin = inicio + ajustes.duracion_min
        avisos = []
        estado = LIBRE
        if disp is None:
            estado = SIN_REGISTRAR
            avisos.append(f"{nombre} no ha registrado su disponibilidad para ese día.")
        elif disp.tipo == DISP_NO_DISPONIBLE:
            estado = NO_DISPONIBLE
            avisos.append(f"{nombre} marcó que NO está disponible ese día" + (f" ({disp.nota})." if disp.nota else "."))
        elif disp.tipo == DISP_HORARIO and (inicio < _minutos(disp.desde) or fin > _minutos(disp.hasta)):
            estado = CONFLICTO
            avisos.append(f"{nombre} solo puede de {disp.desde:%H:%M} a {disp.hasta:%H:%M} "
                          f"(el partido es de {_hhmm(inicio)} a {_hhmm(fin)}).")
        separacion = ajustes.duracion_min + ajustes.descanso_min
        for a in otras:
            otro = a.partido
            if abs(_minutos(otro.hora) - inicio) < separacion:
                if estado != NO_DISPONIBLE:
                    estado = CONFLICTO
                campo = f" en {otro.campo.nombre}" if otro.campo else ""
                avisos.append(f"{nombre} ya tiene partido a las {otro.hora:%H:%M}{campo} "
                              f"({otro.local.nombre} vs {otro.visitante.nombre}).")
        return estado, avisos

