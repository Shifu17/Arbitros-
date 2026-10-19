"""Pagos a árbitros por partido.

Por cada asignación:  saldo = tarifa − pagado en campo − pagado después.

- La tarifa sale de la liga/categoría y posición (`LigaService.tarifa_para`) mientras no se
  haya registrado dinero; en cuanto se registra algo se congela en `Asignacion.tarifa_centavos`
  para que cambiar las tarifas de la liga no altere cuentas ya hechas.
- Los partidos cancelados o suspendidos valen 0, salvo que se le ponga una tarifa a mano
  (p. ej. pagar al árbitro que se presentó).
- "Pagar" (liquidar) crea un `Pago` que cubre el saldo completo de las asignaciones elegidas.
"""

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, select

from arbitros.db.database import Database
from arbitros.db.models import POSICIONES, Arbitro, Asignacion, Jornada, Liga, Pago, Partido
from arbitros.services.dinero import formatear_monto
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import etiqueta_jornada
from arbitros.services.ligas import LigaService
from arbitros.services.texto import fecha_larga, sin_acentos


@dataclass
class LineaPago:
    asignacion_id: int
    arbitro: Arbitro
    partido: Partido
    liga: Liga
    jornada: str
    posicion: str
    tarifa: int
    tarifa_fija: bool
    pagado_campo: int
    pagado_despues: int
    pago_id: int | None

    @property
    def saldo(self) -> int:
        return max(self.tarifa - self.pagado_campo - self.pagado_despues, 0)

    @property
    def jugado(self) -> bool:
        """Ya se puede cobrar: el partido es de hoy o anterior."""
        return self.partido.fecha <= date.today()

    @property
    def liquidada(self) -> bool:
        return self.pago_id is not None


@dataclass
class ResumenArbitro:
    arbitro: Arbitro
    partidos: int
    total: int
    pagado_campo: int
    liquidado: int
    pendiente: int  # saldo de partidos ya jugados
    por_jugar: int  # tarifas de partidos futuros


class PagoService:
    def __init__(self, db: Database, ligas: LigaService):
        self.db = db
        self.ligas = ligas

    # --- Consultas -------------------------------------------------------------

    def lineas(self, desde: date | None = None, hasta: date | None = None, liga_id: int | None = None,
               arbitro_id: int | None = None, jornada_id: int | None = None) -> list[LineaPago]:
        consulta = (
            select(Asignacion, Jornada, Liga)
            .join(Partido, Asignacion.partido_id == Partido.id)
            .join(Jornada, Partido.jornada_id == Jornada.id)
            .join(Liga, Jornada.liga_id == Liga.id)
        )
        if desde:
            consulta = consulta.where(Partido.fecha >= desde)
        if hasta:
            consulta = consulta.where(Partido.fecha <= hasta)
        if liga_id:
            consulta = consulta.where(Liga.id == liga_id)
        if arbitro_id:
            consulta = consulta.where(Asignacion.arbitro_id == arbitro_id)
        if jornada_id:
            consulta = consulta.where(Jornada.id == jornada_id)
        tarifas: dict[tuple, int] = {}
        resultado = []
        with self.db.sesion() as s:
            for a, jornada, liga in s.execute(consulta).unique():
                p = a.partido
                if a.tarifa_centavos is not None:
                    tarifa = a.tarifa_centavos
                elif p.se_juega:
                    clave = (liga.id, p.categoria_id, a.posicion)
                    if clave not in tarifas:
                        tarifas[clave] = self.ligas.tarifa_para(*clave)
                    tarifa = tarifas[clave]
                else:
                    tarifa = 0
                if not p.se_juega and tarifa == 0 and a.pagado_campo_centavos == 0:
                    continue  # cancelado sin nada que pagar: no estorba en las listas
                resultado.append(LineaPago(
                    a.id, a.arbitro, p, liga, etiqueta_jornada(liga, jornada), a.posicion, tarifa,
                    a.tarifa_centavos is not None, a.pagado_campo_centavos, a.pagado_despues_centavos, a.pago_id,
                ))
        resultado.sort(key=lambda l: (l.partido.fecha, l.partido.hora, sin_acentos(l.arbitro.nombre)))
        return resultado

    def resumen_por_arbitro(self, desde: date | None = None, hasta: date | None = None,
                            liga_id: int | None = None) -> list[ResumenArbitro]:
        grupos: dict[int, ResumenArbitro] = {}
        for l in self.lineas(desde, hasta, liga_id):
            r = grupos.setdefault(l.arbitro.id, ResumenArbitro(l.arbitro, 0, 0, 0, 0, 0, 0))
            r.partidos += 1
            r.total += l.tarifa
            r.pagado_campo += l.pagado_campo
            r.liquidado += l.pagado_despues
            if l.jugado:
                r.pendiente += l.saldo
            else:
                r.por_jugar += l.saldo
        return sorted(grupos.values(), key=lambda r: sin_acentos(r.arbitro.nombre))

    def pendientes_de(self, arbitro_id: int, hasta: date | None = None) -> list[LineaPago]:
        """Asignaciones ya jugadas con saldo, listas para pagar."""
        return [l for l in self.lineas(hasta=hasta or date.today(), arbitro_id=arbitro_id)
                if l.saldo > 0 and not l.liquidada]

    def historial(self, arbitro_id: int | None = None) -> list[tuple[Pago, int]]:
        """[(Pago, número de partidos que cubre)], más recientes primero."""
        consulta = select(Pago).order_by(Pago.fecha.desc(), Pago.id.desc())
        if arbitro_id:
            consulta = consulta.where(Pago.arbitro_id == arbitro_id)
        with self.db.sesion() as s:
            pagos = list(s.scalars(consulta).unique())
            conteos = {
                pid: n for pid, n in s.execute(
                    select(Asignacion.pago_id, func.count(Asignacion.id)).where(Asignacion.pago_id.is_not(None))
                    .group_by(Asignacion.pago_id))
            }
        return [(p, conteos.get(p.id, 0)) for p in pagos]

    # --- Cambios -----------------------------------------------------------

    def registrar_en_campo(self, asignacion_id: int, pagado_campo: int, tarifa: int | None = None) -> None:
        """Registra lo que se le pagó al árbitro en el campo. `tarifa` permite corregirla para este partido."""
        if pagado_campo < 0 or (tarifa is not None and tarifa < 0):
            raise ErrorValidacion("Los montos no pueden ser negativos.")
        linea = self._linea(asignacion_id)
        if linea.liquidada:
            raise ErrorValidacion("Este partido ya se le pagó en una liquidación; deshaz ese pago para modificarlo.")
        tarifa_final = linea.tarifa if tarifa is None else tarifa
        if pagado_campo > tarifa_final:
            raise ErrorValidacion(f"Lo pagado en campo no puede ser mayor que la tarifa ({formatear_monto(tarifa_final)}).",
                                  {"pagado_campo": "Mayor que la tarifa"})
        with self.db.sesion() as s:
            a = s.get(Asignacion, asignacion_id)
            a.tarifa_centavos = tarifa_final
            a.pagado_campo_centavos = pagado_campo

    def todo_pagado_en_campo(self, asignacion_ids: list[int]) -> int:
        """Marca que en el campo se pagó la tarifa completa. Devuelve cuántas cambió."""
        cambiadas = 0
        for asignacion_id in asignacion_ids:
            linea = self._linea(asignacion_id)
            if linea.liquidada or linea.saldo == 0:
                continue
            self.registrar_en_campo(asignacion_id, linea.tarifa - linea.pagado_despues)
            cambiadas += 1
        return cambiadas

    def liquidar(self, arbitro_id: int, asignacion_ids: list[int], fecha: date | None = None, nota: str = "") -> Pago:
        if not asignacion_ids:
            raise ErrorValidacion("Selecciona al menos un partido.")
        lineas = [self._linea(i) for i in asignacion_ids]
        for l in lineas:
            if l.arbitro.id != arbitro_id:
                raise ErrorValidacion("Hay partidos de otro árbitro en la selección.")
            if l.liquidada:
                raise ErrorValidacion("Uno de los partidos ya estaba pagado.")
        lineas = [l for l in lineas if l.saldo > 0]
        if not lineas:
            raise ErrorValidacion("Esos partidos no tienen saldo pendiente.")
        with self.db.sesion() as s:
            pago = Pago(arbitro_id=arbitro_id, fecha=fecha or date.today(),
                        monto_centavos=sum(l.saldo for l in lineas), nota=(nota or "").strip() or None)
            s.add(pago)
            s.flush()
            for l in lineas:
                a = s.get(Asignacion, l.asignacion_id)
                a.tarifa_centavos = l.tarifa
                a.pagado_despues_centavos = l.saldo
                a.pago_id = pago.id
            pago_id = pago.id
        with self.db.sesion() as s:
            return s.get(Pago, pago_id)

    def deshacer_pago(self, pago_id: int) -> None:
        with self.db.sesion() as s:
            for a in s.scalars(select(Asignacion).where(Asignacion.pago_id == pago_id)).unique():
                a.pagado_despues_centavos = 0
                a.pago_id = None
            pago = s.get(Pago, pago_id)
            if pago:
                s.delete(pago)

    # --- Texto para WhatsApp -------------------------------------------------

    def estado_de_cuenta(self, arbitro_id: int) -> str:
        pendientes = self.pendientes_de(arbitro_id)
        with self.db.sesion() as s:
            arbitro = s.get(Arbitro, arbitro_id)
        lineas = [f"💰 *Estado de cuenta · {arbitro.nombre}*", ""]
        if not pendientes:
            lineas.append("No tienes pagos pendientes. ¡Gracias!")
            return "\n".join(lineas)
        for l in pendientes:
            p = l.partido
            detalle = f" (en campo {formatear_monto(l.pagado_campo)})" if l.pagado_campo else ""
            lineas.append(f"• {fecha_larga(p.fecha)} · {p.local.nombre} vs {p.visitante.nombre} · "
                          f"{POSICIONES[l.posicion]}: *{formatear_monto(l.saldo)}*{detalle}")
        lineas += ["", f"*Total pendiente: {formatear_monto(sum(l.saldo for l in pendientes))}*"]
        return "\n".join(lineas)

    def _linea(self, asignacion_id: int) -> LineaPago:
        with self.db.sesion() as s:
            a = s.get(Asignacion, asignacion_id)
            if not a:
                raise ErrorValidacion("La asignación ya no existe.")
            jornada_id = a.partido.jornada_id
        for l in self.lineas(jornada_id=jornada_id, arbitro_id=a.arbitro_id):
            if l.asignacion_id == asignacion_id:
                return l
        # Cancelado sin tarifa: no aparece en las listas, pero puede recibir una tarifa a mano
        with self.db.sesion() as s:
            a = s.get(Asignacion, asignacion_id)
            jornada = s.get(Jornada, a.partido.jornada_id)
            liga = s.get(Liga, jornada.liga_id)
            return LineaPago(a.id, a.arbitro, a.partido, liga, etiqueta_jornada(liga, jornada), a.posicion,
                             a.tarifa_centavos or 0, a.tarifa_centavos is not None, a.pagado_campo_centavos,
                             a.pagado_despues_centavos, a.pago_id)

