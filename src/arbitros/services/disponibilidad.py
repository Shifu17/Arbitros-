"""Disponibilidad diaria de los árbitros (todo el día, en un horario o no disponible)."""

from dataclasses import dataclass
from datetime import date, time, timedelta

from sqlalchemy import delete, select

from arbitros.db.database import Database
from arbitros.db.models import (
    DISP_HORARIO,
    TIPOS_DISPONIBILIDAD,
    Arbitro,
    Disponibilidad,
)
from arbitros.services.errores import ErrorValidacion


def lunes_de(d: date) -> date:
    return d - timedelta(days=d.weekday())


def dias_de_semana(lunes: date) -> list[date]:
    return [lunes + timedelta(days=i) for i in range(7)]


@dataclass
class DatosDisponibilidad:
    tipo: str | None  # None = borrar (sin registrar)
    desde: time | None = None
    hasta: time | None = None
    nota: str = ""


class DisponibilidadService:
    def __init__(self, db: Database):
        self.db = db

    def de_semana(self, lunes: date) -> dict[tuple[int, date], Disponibilidad]:
        """{(arbitro_id, fecha): Disponibilidad} de la semana que empieza en `lunes`."""
        return self.de_rango(lunes, lunes + timedelta(days=6))

    def de_rango(self, desde: date, hasta: date) -> dict[tuple[int, date], Disponibilidad]:
        consulta = select(Disponibilidad).where(Disponibilidad.fecha.between(desde, hasta))
        with self.db.sesion() as s:
            return {(d.arbitro_id, d.fecha): d for d in s.scalars(consulta)}

    def de_dia(self, arbitro_id: int, fecha: date) -> Disponibilidad | None:
        with self.db.sesion() as s:
            return s.scalar(
                select(Disponibilidad).where(Disponibilidad.arbitro_id == arbitro_id, Disponibilidad.fecha == fecha)
            )

    def guardar(self, arbitro_id: int, fechas: list[date], datos: DatosDisponibilidad) -> None:
        """Aplica lo mismo a uno o varios días del árbitro."""
        self._validar(datos)
        with self.db.sesion() as s:
            for fecha in fechas:
                existente = s.scalar(
                    select(Disponibilidad).where(Disponibilidad.arbitro_id == arbitro_id, Disponibilidad.fecha == fecha)
                )
                if datos.tipo is None:
                    if existente:
                        s.delete(existente)
                    continue
                fila = existente or Disponibilidad(arbitro_id=arbitro_id, fecha=fecha)
                fila.tipo = datos.tipo
                fila.desde = datos.desde if datos.tipo == DISP_HORARIO else None
                fila.hasta = datos.hasta if datos.tipo == DISP_HORARIO else None
                fila.nota = (datos.nota or "").strip() or None
                if not existente:
                    s.add(fila)

    def marcar_dia_para_todos(self, fecha: date, datos: DatosDisponibilidad, solo_sin_registrar: bool = True) -> int:
        """Atajo: aplica una disponibilidad a todos los árbitros activos en un día. Devuelve cuántos cambió."""
        self._validar(datos)
        with self.db.sesion() as s:
            ids = list(s.scalars(select(Arbitro.id).where(Arbitro.activo.is_(True))))
            ya = set(s.scalars(select(Disponibilidad.arbitro_id).where(Disponibilidad.fecha == fecha)))
        objetivo = [i for i in ids if not (solo_sin_registrar and i in ya)]
        for arbitro_id in objetivo:
            self.guardar(arbitro_id, [fecha], datos)
        return len(objetivo)

    def copiar_semana(self, lunes_origen: date, lunes_destino: date, sobrescribir: bool = False) -> int:
        """Copia la disponibilidad de una semana a otra (mismo día de la semana). Devuelve cuántos días copió."""
        delta = lunes_destino - lunes_origen
        origen = self.de_semana(lunes_origen)
        copiados = 0
        with self.db.sesion() as s:
            destino = {
                (d.arbitro_id, d.fecha): d
                for d in s.scalars(select(Disponibilidad).where(
                    Disponibilidad.fecha.between(lunes_destino, lunes_destino + timedelta(days=6))))
            }
            for (arbitro_id, fecha), d in origen.items():
                clave = (arbitro_id, fecha + delta)
                if clave in destino:
                    if not sobrescribir:
                        continue
                    s.delete(destino[clave])
                    s.flush()
                s.add(Disponibilidad(arbitro_id=arbitro_id, fecha=fecha + delta, tipo=d.tipo,
                                     desde=d.desde, hasta=d.hasta, nota=d.nota))
                copiados += 1
        return copiados

    def limpiar_dia(self, fecha: date) -> None:
        with self.db.sesion() as s:
            s.execute(delete(Disponibilidad).where(Disponibilidad.fecha == fecha))

    @staticmethod
    def _validar(d: DatosDisponibilidad) -> None:
        if d.tipo is not None and d.tipo not in TIPOS_DISPONIBILIDAD:
            raise ErrorValidacion("Tipo de disponibilidad inválido.")
        if d.tipo == DISP_HORARIO:
            errores = {}
            if not d.desde:
                errores["desde"] = "Escribe desde qué hora"
            if not d.hasta:
                errores["hasta"] = "Escribe hasta qué hora"
            if d.desde and d.hasta and d.hasta <= d.desde:
                errores["hasta"] = "Debe ser después de «desde»"
            if errores:
                raise ErrorValidacion("Revisa el horario.", errores)


def describir(d: Disponibilidad | None) -> str:
    if d is None:
        return "Sin registrar"
    if d.tipo == DISP_HORARIO:
        return f"De {d.desde:%H:%M} a {d.hasta:%H:%M}"
    return TIPOS_DISPONIBILIDAD[d.tipo]

