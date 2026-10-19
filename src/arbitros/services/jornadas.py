"""Jornadas (o días de torneo) y sus partidos.

Los partidos validan errores duros (equipos de otra liga, local = visitante...)
y además generan *avisos* (choques de campo, equipo repetido, fecha fuera de la
jornada). Los avisos no bloquean: se lanza AvisosPendientes y la UI puede volver
a llamar con forzar=True.
"""

from dataclasses import dataclass, field
from datetime import date, time

from sqlalchemy import delete, func, select

from arbitros.db.database import Database
from arbitros.db.models import (
    ESTADO_PROGRAMADO,
    ESTADOS_PARTIDO,
    ESTADOS_SIN_JUEGO,
    FUTBOL_11,
    MODALIDADES,
    Asignacion,
    Campo,
    Categoria,
    Equipo,
    Jornada,
    Liga,
    Partido,
    posiciones_a_csv,
)
from arbitros.services.errores import AvisosPendientes, ErrorValidacion

# Dos partidos en el mismo campo con menos de esto entre sus horas de inicio generan aviso
MINUTOS_MINIMOS_ENTRE_PARTIDOS_CAMPO = 60


@dataclass
class ResumenJornada:
    jornada: Jornada
    partidos: int


@dataclass
class DatosPartido:
    fecha: date | None
    hora: time | None
    local_id: int | None
    visitante_id: int | None
    campo_id: int | None
    posiciones: list[str] = field(default_factory=list)
    estado: str = ESTADO_PROGRAMADO
    notas: str = ""
    motivo_estado: str = ""
    categoria_id: int | None = None
    modalidad: str | None = None  # None = la de la categoría o la de la liga


def etiqueta_jornada(liga: Liga, jornada: Jornada) -> str:
    return f"{'Día' if liga.es_torneo else 'Jornada'} {jornada.numero}"


def _motivo(estado: str, motivo: str) -> str | None:
    return ((motivo or "").strip() or None) if estado in ESTADOS_SIN_JUEGO else None


def texto_a_hora(texto: str) -> time | None:
    """Interpreta lo que el usuario escribe: '10', '1030', '10:30', '10.30', '4:30 pm', '16h'."""
    t = (texto or "").strip().lower().replace(" ", "").replace(".", ":").replace("h", "")
    pm = t.endswith(("pm", "p:m:"))
    am = t.endswith(("am", "a:m:"))
    t = t.removesuffix("p:m:").removesuffix("a:m:").removesuffix("pm").removesuffix("am")
    if ":" in t:
        horas, _, minutos = t.partition(":")
    elif t.isdigit() and len(t) in (3, 4):
        horas, minutos = t[:-2], t[-2:]
    else:
        horas, minutos = t, "0"
    if not (horas.isdigit() and minutos.isdigit()):
        return None
    h, m = int(horas), int(minutos)
    if pm and h < 12:
        h += 12
    if am and h == 12:
        h = 0
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return time(h, m)


def _minutos(h: time) -> int:
    return h.hour * 60 + h.minute


class JornadaService:
    def __init__(self, db: Database):
        self.db = db

    # --- Jornadas ---------------------------------------------------------

    def listar(self, liga_id: int) -> list[ResumenJornada]:
        n_partidos = select(func.count(Partido.id)).where(Partido.jornada_id == Jornada.id).scalar_subquery()
        consulta = select(Jornada, n_partidos).where(Jornada.liga_id == liga_id).order_by(Jornada.numero)
        with self.db.sesion() as s:
            return [ResumenJornada(*fila) for fila in s.execute(consulta)]

    def obtener(self, jornada_id: int) -> Jornada | None:
        with self.db.sesion() as s:
            return s.get(Jornada, jornada_id)

    def siguiente_numero(self, liga_id: int) -> int:
        with self.db.sesion() as s:
            return (s.scalar(select(func.max(Jornada.numero)).where(Jornada.liga_id == liga_id)) or 0) + 1

    def crear(
        self, liga_id: int, fecha_inicio: date | None, fecha_fin: date | None = None,
        numero: int | None = None, notas: str = "",
    ) -> Jornada:
        with self.db.sesion() as s:
            liga = s.get(Liga, liga_id)
            if not liga:
                raise ErrorValidacion("La liga ya no existe.")
            if numero is None or liga.es_torneo:
                numero = (s.scalar(select(func.max(Jornada.numero)).where(Jornada.liga_id == liga_id)) or 0) + 1
            self._validar(s, liga, numero, fecha_inicio, fecha_fin)
            jornada = Jornada(
                liga_id=liga_id, numero=numero, fecha_inicio=fecha_inicio,
                fecha_fin=None if liga.es_torneo else fecha_fin, notas=(notas or "").strip() or None,
            )
            s.add(jornada)
            s.flush()
            if liga.es_torneo:
                self._renumerar_dias(s, liga_id)
            return jornada

    def actualizar(
        self, jornada_id: int, fecha_inicio: date | None, fecha_fin: date | None = None,
        numero: int | None = None, notas: str = "",
    ) -> Jornada:
        with self.db.sesion() as s:
            jornada = s.get(Jornada, jornada_id)
            if not jornada:
                raise ErrorValidacion("La jornada ya no existe.")
            liga = s.get(Liga, jornada.liga_id)
            if numero is None or liga.es_torneo:
                numero = jornada.numero
            self._validar(s, liga, numero, fecha_inicio, fecha_fin, excluir_id=jornada_id)
            jornada.numero = numero
            jornada.fecha_inicio = fecha_inicio
            jornada.fecha_fin = None if liga.es_torneo else fecha_fin
            jornada.notas = (notas or "").strip() or None
            s.flush()
            if liga.es_torneo:
                self._renumerar_dias(s, liga.id)
            return jornada

    def eliminar(self, jornada_id: int) -> None:
        """Elimina la jornada y TODOS sus partidos."""
        with self.db.sesion() as s:
            jornada = s.get(Jornada, jornada_id)
            if not jornada:
                return
            liga = s.get(Liga, jornada.liga_id)
            s.execute(delete(Partido).where(Partido.jornada_id == jornada_id))
            s.delete(jornada)
            s.flush()
            if liga.es_torneo:
                self._renumerar_dias(s, liga.id)

    @staticmethod
    def _validar(s, liga, numero, fecha_inicio, fecha_fin, excluir_id=None) -> None:
        errores = {}
        if not fecha_inicio:
            errores["fecha_inicio"] = "Escribe la fecha"
        elif fecha_fin and fecha_fin < fecha_inicio:
            errores["fecha_fin"] = "No puede ser antes del inicio"
        if numero < 1:
            errores["numero"] = "Debe ser 1 o mayor"
        elif not liga.es_torneo:
            consulta = select(Jornada).where(Jornada.liga_id == liga.id, Jornada.numero == numero)
            if excluir_id is not None:
                consulta = consulta.where(Jornada.id != excluir_id)
            if s.scalar(consulta):
                errores["numero"] = f"Ya existe la jornada {numero}"
        if errores:
            raise ErrorValidacion("Revisa los datos marcados.", errores)

    @staticmethod
    def _renumerar_dias(s, liga_id: int) -> None:
        """En torneos, los días se numeran por fecha: Día 1, Día 2..."""
        dias = list(s.scalars(select(Jornada).where(Jornada.liga_id == liga_id).order_by(Jornada.fecha_inicio, Jornada.id)))
        # Dos pasos para no chocar con la restricción única (liga_id, numero)
        for i, d in enumerate(dias, start=1):
            d.numero = -i
        s.flush()
        for d in dias:
            d.numero = -d.numero
        s.flush()

    # --- Partidos ---------------------------------------------------------

    def listar_partidos(self, jornada_id: int) -> list[Partido]:
        consulta = (
            select(Partido)
            .outerjoin(Campo, Partido.campo_id == Campo.id)
            .where(Partido.jornada_id == jornada_id)
            .order_by(Partido.fecha, Partido.hora, func.lower(Campo.nombre))
        )
        with self.db.sesion() as s:
            return list(s.scalars(consulta).unique())

    def partidos_entre(self, desde: date, hasta: date) -> list[tuple[Partido, Liga, Jornada]]:
        """Partidos de todas las ligas activas en el rango, en orden cronológico."""
        consulta = (
            select(Partido, Liga, Jornada)
            .join(Jornada, Partido.jornada_id == Jornada.id)
            .join(Liga, Jornada.liga_id == Liga.id)
            .where(Partido.fecha.between(desde, hasta), Liga.activa.is_(True))
            .order_by(Partido.fecha, Partido.hora)
        )
        with self.db.sesion() as s:
            return [tuple(fila) for fila in s.execute(consulta).unique()]

    def obtener_partido(self, partido_id: int) -> Partido | None:
        with self.db.sesion() as s:
            return s.get(Partido, partido_id)

    def crear_partido(self, jornada_id: int, datos: DatosPartido, forzar: bool = False) -> Partido:
        with self.db.sesion() as s:
            jornada = s.get(Jornada, jornada_id)
            if not jornada:
                raise ErrorValidacion("La jornada ya no existe.")
            self._validar_partido(s, jornada, datos, None, forzar)
            partido = Partido(jornada_id=jornada_id)
            self._aplicar(partido, datos)
            partido.modalidad = self._modalidad(s, jornada, datos)
            s.add(partido)
            s.flush()
            partido_id = partido.id
        return self.obtener_partido(partido_id)

    def actualizar_partido(self, partido_id: int, datos: DatosPartido, forzar: bool = False) -> Partido:
        with self.db.sesion() as s:
            partido = s.get(Partido, partido_id)
            if not partido:
                raise ErrorValidacion("El partido ya no existe.")
            jornada = s.get(Jornada, partido.jornada_id)
            self._validar_partido(s, jornada, datos, partido_id, forzar)
            self._aplicar(partido, datos)
            partido.modalidad = self._modalidad(s, jornada, datos)
            # Si se quitó una posición (p. ej. ya no lleva cuarto árbitro), se libera su asignación
            s.execute(delete(Asignacion).where(
                Asignacion.partido_id == partido_id, Asignacion.posicion.not_in(partido.lista_posiciones)))
        return self.obtener_partido(partido_id)

    def cambiar_estado(self, partido_ids: list[int], estado: str, motivo: str = "") -> int:
        """Cambia el estado de varios partidos a la vez (p. ej. cancelar por lluvia). Devuelve cuántos."""
        if estado not in ESTADOS_PARTIDO:
            raise ErrorValidacion("Estado inválido.")
        if not partido_ids:
            raise ErrorValidacion("Selecciona al menos un partido.")
        with self.db.sesion() as s:
            partidos = list(s.scalars(select(Partido).where(Partido.id.in_(partido_ids))).unique())
            for p in partidos:
                p.estado = estado
                p.motivo_estado = _motivo(estado, motivo)
            return len(partidos)

    def eliminar_partido(self, partido_id: int) -> None:
        with self.db.sesion() as s:
            partido = s.get(Partido, partido_id)
            if partido:
                s.delete(partido)

    @staticmethod
    def _modalidad(s, jornada: Jornada, d: DatosPartido) -> str:
        if d.modalidad:
            return d.modalidad
        categoria = s.get(Categoria, d.categoria_id) if d.categoria_id else None
        liga = s.get(Liga, jornada.liga_id)
        return (categoria.modalidad if categoria else None) or liga.modalidad or FUTBOL_11

    @staticmethod
    def _aplicar(partido: Partido, d: DatosPartido) -> None:
        partido.categoria_id = d.categoria_id
        partido.fecha = d.fecha
        partido.hora = d.hora
        partido.local_id = d.local_id
        partido.visitante_id = d.visitante_id
        partido.campo_id = d.campo_id
        partido.posiciones = posiciones_a_csv(d.posiciones)
        partido.estado = d.estado
        partido.motivo_estado = _motivo(d.estado, d.motivo_estado)
        partido.notas = (d.notas or "").strip() or None

    def _validar_partido(self, s, jornada: Jornada, d: DatosPartido, excluir_id: int | None, forzar: bool) -> None:
        errores = {}
        if not d.fecha:
            errores["fecha"] = "Escribe la fecha"
        if not d.hora:
            errores["hora"] = "Elige la hora"
        if not d.local_id:
            errores["local"] = "Elige el equipo local"
        if not d.visitante_id:
            errores["visitante"] = "Elige el equipo visitante"
        if d.local_id and d.local_id == d.visitante_id:
            errores["visitante"] = "Debe ser distinto al local"
        if not d.campo_id:
            errores["campo"] = "Elige el campo"
        if not posiciones_a_csv(d.posiciones):
            errores["posiciones"] = "Marca al menos una posición"
        if d.estado not in ESTADOS_PARTIDO:
            errores["estado"] = "Estado inválido"
        if d.modalidad and d.modalidad not in MODALIDADES:
            errores["modalidad"] = "Tipo de partido inválido"
        categorias_liga = s.scalar(
            select(func.count(Categoria.id)).where(Categoria.liga_id == jornada.liga_id, Categoria.activo.is_(True))
        )
        if categorias_liga and not d.categoria_id:
            errores["categoria"] = "Elige la categoría"
        for clave, modelo, item_id in (
            ("local", Equipo, d.local_id), ("visitante", Equipo, d.visitante_id), ("campo", Campo, d.campo_id),
            ("categoria", Categoria, d.categoria_id),
        ):
            if item_id and clave not in errores:
                item = s.get(modelo, item_id)
                if not item or item.liga_id != jornada.liga_id:
                    errores[clave] = "No pertenece a esta liga"
        if errores:
            raise ErrorValidacion("Revisa los datos marcados.", errores)
        if not forzar and d.estado not in ESTADOS_SIN_JUEGO:
            avisos = self._avisos(s, jornada, d, excluir_id)
            if avisos:
                raise AvisosPendientes(avisos)

    @staticmethod
    def _avisos(s, jornada: Jornada, d: DatosPartido, excluir_id: int | None) -> list[str]:
        avisos = []
        if jornada.fecha_fin:
            if not jornada.fecha_inicio <= d.fecha <= jornada.fecha_fin:
                avisos.append("La fecha está fuera de las fechas de la jornada.")
        elif abs((d.fecha - jornada.fecha_inicio).days) > 6:
            avisos.append("La fecha está a más de una semana de la fecha de la jornada.")

        # Los partidos cancelados o suspendidos no cuentan para choques
        otros = select(Partido).where(Partido.jornada_id == jornada.id, Partido.estado.not_in(ESTADOS_SIN_JUEGO))
        if excluir_id is not None:
            otros = otros.where(Partido.id != excluir_id)
        otros = list(s.scalars(otros).unique())

        for equipo_id in (d.local_id, d.visitante_id):
            equipo = s.get(Equipo, equipo_id)
            if any(equipo_id in (p.local_id, p.visitante_id) for p in otros):
                avisos.append(f"{equipo.nombre} ya tiene otro partido en esta jornada.")
            if d.categoria_id and equipo.categoria_id and equipo.categoria_id != d.categoria_id:
                otra = s.get(Categoria, equipo.categoria_id).nombre
                avisos.append(f"{equipo.nombre} es de la categoría {otra}.")

        # Choques de campo: se revisan todos los partidos de esa fecha en el campo, de cualquier jornada
        mismo_campo = select(Partido).where(
            Partido.campo_id == d.campo_id, Partido.fecha == d.fecha, Partido.estado.not_in(ESTADOS_SIN_JUEGO)
        )
        if excluir_id is not None:
            mismo_campo = mismo_campo.where(Partido.id != excluir_id)
        inicio = _minutos(d.hora)
        for p in s.scalars(mismo_campo).unique():
            if abs(_minutos(p.hora) - inicio) < MINUTOS_MINIMOS_ENTRE_PARTIDOS_CAMPO:
                avisos.append(
                    f"En {p.campo.nombre} ya hay un partido a las {p.hora:%H:%M} "
                    f"({p.local.nombre} vs {p.visitante.nombre})."
                )
        return avisos
