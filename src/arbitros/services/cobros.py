"""Cobro del arbitraje a los equipos: quién pagó, cuánto debe y su recibo.

- Cada equipo paga por partido el arbitraje establecido en la liga para ese tipo de partido,
  o el de su categoría si tiene uno propio (`LigaService.cuota_equipo_para`). P. ej. Intecy y
  UNAM pagan $450 cada uno.
- Sin arbitraje establecido no hay nada que cobrar.
- La cuota se puede corregir por partido (p. ej. un equipo paga todo); al registrar un pago se
  congela en `CobroEquipo.cuota_centavos`.
- Los partidos cancelados o suspendidos no cobran, salvo que ya se haya registrado un cobro.
- Pagos adelantados (`AbonoEquipo`): dinero que un equipo dejó antes (o de antes de usar la app).
  No se guarda a qué partido se aplicó: se calcula cada vez, cubriendo lo que debe en sus partidos
  en orden de fecha; lo que sobra es saldo a favor. Así, borrar o cancelar algo lo reacomoda solo.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select

from arbitros import colegios
from arbitros.db.database import Database
from arbitros.db.models import FORMAS_PAGO, AbonoEquipo, CobroEquipo, Equipo, Jornada, Liga, Partido
from arbitros.services.dinero import formatear_monto
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import etiqueta_jornada
from arbitros.services.ligas import LigaService
from arbitros.services.texto import fecha_larga, sin_acentos


@dataclass
class LineaCobro:
    partido: Partido
    liga: Liga
    jornada: str
    equipo: Equipo
    rival: Equipo
    es_local: bool
    cuota: int
    cuota_fija: bool
    pagado: int
    fecha_pago: date | None = None
    forma_pago: str | None = None
    nota: str | None = None
    abonado: int = 0  # cubierto con pagos adelantados

    @property
    def saldo(self) -> int:
        return max(self.cuota - self.pagado - self.abonado, 0)

    @property
    def pagado_total(self) -> int:
        return self.pagado + self.abonado

    @property
    def jugado(self) -> bool:
        return self.partido.fecha <= date.today()

    @property
    def clave(self) -> tuple[int, int]:
        return self.partido.id, self.equipo.id


@dataclass
class ResumenEquipo:
    equipo: Equipo
    liga: Liga
    partidos: int = 0
    total: int = 0
    pagado: int = 0
    pendiente: int = 0  # saldo de partidos ya jugados
    por_jugar: int = 0
    a_favor: int = 0  # pagos adelantados que aún no se usan


@dataclass
class ReciboEquipo:
    equipo: Equipo
    liga: Liga
    periodo: str
    lineas: list[LineaCobro] = field(default_factory=list)
    abonos: list[AbonoEquipo] = field(default_factory=list)
    a_favor: int = 0

    @property
    def total(self) -> int:
        return sum(l.cuota for l in self.lineas)

    @property
    def pagado(self) -> int:
        return sum(l.pagado_total for l in self.lineas)

    @property
    def saldo(self) -> int:
        return sum(l.saldo for l in self.lineas)


class CobroService:
    def __init__(self, db: Database, ligas: LigaService):
        self.db = db
        self.ligas = ligas

    # --- Consultas -------------------------------------------------------------

    def lineas(self, desde: date | None = None, hasta: date | None = None, liga_id: int | None = None,
               jornada_id: int | None = None, equipo_id: int | None = None) -> list[LineaCobro]:
        resultado = self._lineas(desde, hasta, liga_id, jornada_id, {equipo_id} if equipo_id else None)
        aplicado, _ = self._repartir_abonos({l.equipo.id for l in resultado})
        for l in resultado:
            l.abonado = aplicado.get(l.clave, 0)
        return resultado

    def _repartir_abonos(self, equipo_ids: set[int]) -> tuple[dict[tuple[int, int], int], dict[int, int]]:
        """Aplica los pagos adelantados a lo que deben esos equipos, partido por partido en orden de fecha.

        Devuelve ({(partido_id, equipo_id): cubierto}, {equipo_id: saldo a favor}).
        """
        restante = {e: t for e, t in self._totales_abonos(equipo_ids).items() if t > 0}
        aplicado: dict[tuple[int, int], int] = {}
        if not restante:
            return aplicado, restante
        for l in self._lineas(equipo_ids=set(restante)):
            usar = min(restante[l.equipo.id], max(l.cuota - l.pagado, 0))
            if usar:
                aplicado[l.clave] = usar
                restante[l.equipo.id] -= usar
        return aplicado, restante

    def _totales_abonos(self, equipo_ids: set[int]) -> dict[int, int]:
        if not equipo_ids:
            return {}
        with self.db.sesion() as s:
            totales: dict[int, int] = {}
            for a in s.scalars(select(AbonoEquipo).where(AbonoEquipo.equipo_id.in_(equipo_ids))).unique():
                totales[a.equipo_id] = totales.get(a.equipo_id, 0) + a.monto_centavos
        return totales

    def _lineas(self, desde: date | None = None, hasta: date | None = None, liga_id: int | None = None,
                jornada_id: int | None = None, equipo_ids: set[int] | None = None) -> list[LineaCobro]:
        consulta = (
            select(Partido, Jornada, Liga)
            .join(Jornada, Partido.jornada_id == Jornada.id)
            .join(Liga, Jornada.liga_id == Liga.id)
        )
        if desde:
            consulta = consulta.where(Partido.fecha >= desde)
        if hasta:
            consulta = consulta.where(Partido.fecha <= hasta)
        if liga_id:
            consulta = consulta.where(Liga.id == liga_id)
        if jornada_id:
            consulta = consulta.where(Jornada.id == jornada_id)
        if equipo_ids:
            consulta = consulta.where(Partido.local_id.in_(equipo_ids) | Partido.visitante_id.in_(equipo_ids))
        establecidas: dict[tuple, int] = {}
        resultado = []
        with self.db.sesion() as s:
            filas = list(s.execute(consulta).unique())
            ids = [p.id for p, _, _ in filas]
            cobros = {(c.partido_id, c.equipo_id): c
                      for c in s.scalars(select(CobroEquipo).where(CobroEquipo.partido_id.in_(ids)))}
        for p, jornada, liga in filas:
            if p.se_juega:
                clave = (liga.id, p.categoria_id, p.modalidad)
                if clave not in establecidas:
                    establecidas[clave] = self.ligas.cuota_equipo_para(*clave)
                cuota_normal = establecidas[clave]
            else:
                cuota_normal = 0
            for equipo, rival, es_local in ((p.local, p.visitante, True), (p.visitante, p.local, False)):
                if equipo_ids and equipo.id not in equipo_ids:
                    continue
                c = cobros.get((p.id, equipo.id))
                fija = c is not None and c.cuota_centavos is not None
                cuota = c.cuota_centavos if fija else cuota_normal
                if not c and cuota == 0:
                    continue  # nada que cobrar: no estorba en las listas
                resultado.append(LineaCobro(
                    p, liga, etiqueta_jornada(liga, jornada), equipo, rival, es_local, cuota, fija,
                    c.pagado_centavos if c else 0, c.fecha_pago if c else None,
                    c.forma_pago if c else None, c.nota if c else None,
                ))
        resultado.sort(key=lambda l: (l.partido.fecha, l.partido.hora, not l.es_local))
        return resultado

    def resumen_por_equipo(self, desde: date | None = None, hasta: date | None = None,
                           liga_id: int | None = None) -> list[ResumenEquipo]:
        grupos: dict[int, ResumenEquipo] = {}
        for l in self.lineas(desde, hasta, liga_id):
            r = grupos.setdefault(l.equipo.id, ResumenEquipo(l.equipo, l.liga))
            r.partidos += 1
            r.total += l.cuota
            r.pagado += l.pagado_total
            if l.jugado:
                r.pendiente += l.saldo
            else:
                r.por_jugar += l.saldo
        # Equipos con saldo a favor aparecen aunque no hayan jugado en el periodo
        for a in self.abonos(liga_id=liga_id):
            if a.equipo_id not in grupos:
                with self.db.sesion() as s:
                    grupos[a.equipo_id] = ResumenEquipo(a.equipo, s.get(Liga, a.equipo.liga_id))
        _, a_favor = self._repartir_abonos(set(grupos))
        for equipo_id, r in grupos.items():
            r.a_favor = a_favor.get(equipo_id, 0)
        grupos = {e: r for e, r in grupos.items() if r.partidos or r.a_favor}
        return sorted(grupos.values(), key=lambda r: (sin_acentos(r.liga.nombre), sin_acentos(r.equipo.nombre)))

    def recibo(self, equipo_id: int, desde: date | None = None, hasta: date | None = None,
               jornada_id: int | None = None) -> ReciboEquipo:
        with self.db.sesion() as s:
            equipo = s.get(Equipo, equipo_id)
            if not equipo:
                raise ErrorValidacion("El equipo ya no existe.")
            liga = s.get(Liga, equipo.liga_id)
            jornada = s.get(Jornada, jornada_id) if jornada_id else None
        if jornada:
            periodo = etiqueta_jornada(liga, jornada)
        elif desde and hasta:
            periodo = f"Del {desde:%d/%m/%Y} al {hasta:%d/%m/%Y}"
        else:
            periodo = "Todo el historial"
        abonos = [a for a in self.abonos(equipo_id=equipo_id)
                  if not jornada and (not desde or a.fecha >= desde) and (not hasta or a.fecha <= hasta)]
        _, a_favor = self._repartir_abonos({equipo_id})
        return ReciboEquipo(equipo, liga, periodo, self.lineas(desde, hasta, jornada_id=jornada_id, equipo_id=equipo_id),
                            abonos, a_favor.get(equipo_id, 0))

    def abonos(self, liga_id: int | None = None, equipo_id: int | None = None) -> list[AbonoEquipo]:
        """Pagos adelantados, más recientes primero."""
        consulta = select(AbonoEquipo).join(Equipo, AbonoEquipo.equipo_id == Equipo.id).order_by(
            AbonoEquipo.fecha.desc(), AbonoEquipo.id.desc())
        if liga_id:
            consulta = consulta.where(Equipo.liga_id == liga_id)
        if equipo_id:
            consulta = consulta.where(AbonoEquipo.equipo_id == equipo_id)
        with self.db.sesion() as s:
            return list(s.scalars(consulta).unique())

    def saldo_a_favor(self, equipo_id: int) -> int:
        return self._repartir_abonos({equipo_id})[1].get(equipo_id, 0)

    # --- Cambios -----------------------------------------------------------

    def registrar(self, partido_id: int, equipo_id: int, pagado: int, cuota: int | None = None,
                  fecha: date | None = None, forma_pago: str | None = None, nota: str = "") -> None:
        """Registra lo que pagó el equipo de ese partido. `cuota` permite corregir lo que le toca."""
        if pagado < 0 or (cuota is not None and cuota < 0):
            raise ErrorValidacion("Los montos no pueden ser negativos.")
        if forma_pago is not None and forma_pago not in FORMAS_PAGO:
            raise ErrorValidacion("Forma de pago inválida.", {"forma_pago": "Elige una opción"})
        linea = self._linea(partido_id, equipo_id)
        cuota_final = linea.cuota if cuota is None else cuota
        if pagado > cuota_final:
            raise ErrorValidacion(f"Lo pagado no puede ser mayor que el arbitraje ({formatear_monto(cuota_final)}).",
                                  {"pagado": "Mayor que el arbitraje"})
        with self.db.sesion() as s:
            c = s.scalar(select(CobroEquipo).where(CobroEquipo.partido_id == partido_id,
                                                   CobroEquipo.equipo_id == equipo_id))
            if not c:
                c = CobroEquipo(partido_id=partido_id, equipo_id=equipo_id)
                s.add(c)
            c.cuota_centavos = cuota_final
            c.pagado_centavos = pagado
            c.fecha_pago = (fecha or c.fecha_pago or date.today()) if pagado else None
            c.forma_pago = forma_pago
            c.nota = (nota or "").strip() or None

    def registrar_abono(self, equipo_id: int, monto: int, fecha: date | None = None,
                        forma_pago: str | None = None, nota: str = "") -> AbonoEquipo:
        """Pago adelantado: se aplica solo a lo que el equipo debe, en orden de fecha."""
        if monto <= 0:
            raise ErrorValidacion("Escribe cuánto pagó.", {"monto": "Debe ser mayor que 0"})
        if forma_pago is not None and forma_pago not in FORMAS_PAGO:
            raise ErrorValidacion("Forma de pago inválida.", {"forma_pago": "Elige una opción"})
        with self.db.sesion() as s:
            if not s.get(Equipo, equipo_id):
                raise ErrorValidacion("El equipo ya no existe.", {"equipo": "Elige un equipo"})
            abono = AbonoEquipo(equipo_id=equipo_id, fecha=fecha or date.today(), monto_centavos=monto,
                                forma_pago=forma_pago, nota=(nota or "").strip() or None)
            s.add(abono)
            s.flush()
            abono_id = abono.id
        with self.db.sesion() as s:
            return s.get(AbonoEquipo, abono_id)

    def eliminar_abono(self, abono_id: int) -> None:
        with self.db.sesion() as s:
            abono = s.get(AbonoEquipo, abono_id)
            if abono:
                s.delete(abono)

    def pago_completo(self, claves: list[tuple[int, int]], fecha: date | None = None,
                      forma_pago: str | None = None) -> int:
        """Marca que esos equipos pagaron su arbitraje completo. Devuelve cuántos cambió."""
        cambiados = 0
        for partido_id, equipo_id in claves:
            linea = self._linea(partido_id, equipo_id)
            if linea.saldo == 0:
                continue
            self.registrar(partido_id, equipo_id, linea.pagado + linea.saldo, fecha=fecha,
                           forma_pago=forma_pago or linea.forma_pago, nota=linea.nota or "")
            cambiados += 1
        return cambiados

    def deshacer(self, partido_id: int, equipo_id: int) -> None:
        """Borra lo registrado: el equipo vuelve a deber su arbitraje normal."""
        with self.db.sesion() as s:
            c = s.scalar(select(CobroEquipo).where(CobroEquipo.partido_id == partido_id,
                                                   CobroEquipo.equipo_id == equipo_id))
            if c:
                s.delete(c)

    def _linea(self, partido_id: int, equipo_id: int) -> LineaCobro:
        with self.db.sesion() as s:
            p = s.get(Partido, partido_id)
            if not p:
                raise ErrorValidacion("El partido ya no existe.")
            if equipo_id not in (p.local_id, p.visitante_id):
                raise ErrorValidacion("Ese equipo no juega en este partido.")
            jornada_id = p.jornada_id
        for l in self.lineas(jornada_id=jornada_id, equipo_id=equipo_id):
            if l.partido.id == partido_id:
                return l
        raise ErrorValidacion("Este partido no tiene arbitraje que cobrar (¿está cancelado o la liga no tiene "
                              "arbitraje establecido?).")

    # --- Texto para WhatsApp -------------------------------------------------

    def recibo_texto(self, r: ReciboEquipo) -> str:
        lineas = [f"🧾 *Recibo de arbitrajes · {r.equipo.nombre}*", f"_{r.liga.nombre} · {r.periodo}_", ""]
        if not r.lineas:
            lineas += ["Sin partidos en este periodo.", ""]
        for l in r.lineas:
            p = l.partido
            lineas.append(f"*{fecha_larga(p.fecha)} {p.hora:%H:%M}* · vs {l.rival.nombre} ({l.jornada})")
            estado = "✅ Pagado" if l.saldo == 0 else f"Debe *{formatear_monto(l.saldo)}*"
            pagado = f" · pagó {formatear_monto(l.pagado_total)}" if l.pagado_total and l.saldo else ""
            adelantado = " (con pago adelantado)" if l.abonado else ""
            lineas.append(f"   Arbitraje {formatear_monto(l.cuota)}{pagado} · {estado}{adelantado}")
            lineas.append("")
        if r.abonos:
            lineas.append("*Pagos adelantados*")
            for a in r.abonos:
                forma = f" · {FORMAS_PAGO[a.forma_pago]}" if a.forma_pago else ""
                lineas.append(f"   {a.fecha:%d/%m/%Y}{forma}: {formatear_monto(a.monto_centavos)}")
            lineas.append("")
        lineas += [f"Total: {formatear_monto(r.total)}", f"Pagado: {formatear_monto(r.pagado)}",
                   f"*Saldo pendiente: {formatear_monto(r.saldo)}*"]
        if r.a_favor:
            lineas.append(f"*Saldo a favor: {formatear_monto(r.a_favor)}*")
        lineas += ["", f"_{colegios.activo().nombre}_"]
        return "\n".join(lineas)
