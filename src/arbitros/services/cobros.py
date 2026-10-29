"""Cobro del arbitraje a los equipos: quién pagó, cuánto debe y su recibo desglosado.

- El arbitraje de un partido es la suma de las tarifas de sus posiciones (la tarifa congelada
  de la asignación si ya se registró dinero al árbitro; si no, la de la liga/categoría).
- Cada equipo paga la mitad de cada posición (si sobra un centavo lo paga el local).
- La cuota se puede corregir por partido (p. ej. un equipo paga todo); al registrar un pago se
  congela en `CobroEquipo.cuota_centavos`.
- Los partidos cancelados o suspendidos no cobran, salvo que ya se haya registrado un cobro.
"""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select

from arbitros.config import ORGANIZACION
from arbitros.db.database import Database
from arbitros.db.models import FORMAS_PAGO, POSICIONES, Asignacion, CobroEquipo, Equipo, Jornada, Liga, Partido
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
    desglose: list[tuple[str, int]]  # (posición, parte que le toca al equipo)
    cuota: int
    cuota_fija: bool
    pagado: int
    fecha_pago: date | None = None
    forma_pago: str | None = None
    nota: str | None = None

    @property
    def saldo(self) -> int:
        return max(self.cuota - self.pagado, 0)

    @property
    def jugado(self) -> bool:
        return self.partido.fecha <= date.today()

    @property
    def ajuste(self) -> int:
        """Diferencia entre la cuota y la suma del desglose (cuando se corrigió a mano)."""
        return self.cuota - sum(m for _, m in self.desglose)

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


@dataclass
class ReciboEquipo:
    equipo: Equipo
    liga: Liga
    periodo: str
    lineas: list[LineaCobro] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(l.cuota for l in self.lineas)

    @property
    def pagado(self) -> int:
        return sum(l.pagado for l in self.lineas)

    @property
    def saldo(self) -> int:
        return sum(l.saldo for l in self.lineas)


def _repartir(tarifa: int, es_local: bool) -> int:
    mitad = tarifa // 2
    return tarifa - mitad if es_local else mitad


def _desglose_a_texto(desglose: list[tuple[str, int]]) -> str:
    return ",".join(f"{pos}:{monto}" for pos, monto in desglose)


def _texto_a_desglose(texto: str) -> list[tuple[str, int]]:
    partes = (x.partition(":") for x in texto.split(",") if x)
    return [(pos, int(monto)) for pos, _, monto in partes if pos in POSICIONES]


class CobroService:
    def __init__(self, db: Database, ligas: LigaService):
        self.db = db
        self.ligas = ligas

    # --- Consultas -------------------------------------------------------------

    def lineas(self, desde: date | None = None, hasta: date | None = None, liga_id: int | None = None,
               jornada_id: int | None = None, equipo_id: int | None = None) -> list[LineaCobro]:
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
        if equipo_id:
            consulta = consulta.where((Partido.local_id == equipo_id) | (Partido.visitante_id == equipo_id))
        tarifas: dict[tuple, int] = {}
        resultado = []
        with self.db.sesion() as s:
            filas = list(s.execute(consulta).unique())
            ids = [p.id for p, _, _ in filas]
            cobros = {(c.partido_id, c.equipo_id): c
                      for c in s.scalars(select(CobroEquipo).where(CobroEquipo.partido_id.in_(ids)))}
            congeladas = {(a.partido_id, a.posicion): a.tarifa_centavos
                          for a in s.scalars(select(Asignacion).where(Asignacion.partido_id.in_(ids),
                                                                      Asignacion.tarifa_centavos.is_not(None)))
                          .unique()}
        for p, jornada, liga in filas:
            por_posicion = []
            for posicion in p.lista_posiciones:
                if (p.id, posicion) in congeladas:
                    tarifa = congeladas[(p.id, posicion)]
                elif p.se_juega:
                    clave = (liga.id, p.categoria_id, posicion)
                    if clave not in tarifas:
                        tarifas[clave] = self.ligas.tarifa_para(*clave)
                    tarifa = tarifas[clave]
                else:
                    tarifa = 0
                por_posicion.append((posicion, tarifa))
            for equipo, rival, es_local in ((p.local, p.visitante, True), (p.visitante, p.local, False)):
                if equipo_id and equipo.id != equipo_id:
                    continue
                desglose = [(pos, _repartir(t, es_local)) for pos, t in por_posicion if t]
                c = cobros.get((p.id, equipo.id))
                if c and c.desglose is not None:
                    desglose = _texto_a_desglose(c.desglose)
                cuota = c.cuota_centavos if c and c.cuota_centavos is not None else sum(m for _, m in desglose)
                if not c and (cuota == 0 or not p.se_juega):
                    continue  # nada que cobrar: no estorba en las listas
                resultado.append(LineaCobro(
                    p, liga, etiqueta_jornada(liga, jornada), equipo, rival, es_local, desglose, cuota,
                    bool(c and c.cuota_centavos is not None), c.pagado_centavos if c else 0,
                    c.fecha_pago if c else None, c.forma_pago if c else None, c.nota if c else None,
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
            r.pagado += l.pagado
            if l.jugado:
                r.pendiente += l.saldo
            else:
                r.por_jugar += l.saldo
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
        return ReciboEquipo(equipo, liga, periodo, self.lineas(desde, hasta, jornada_id=jornada_id, equipo_id=equipo_id))

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
            raise ErrorValidacion(f"Lo pagado no puede ser mayor que la cuota ({formatear_monto(cuota_final)}).",
                                  {"pagado": "Mayor que la cuota"})
        with self.db.sesion() as s:
            c = s.scalar(select(CobroEquipo).where(CobroEquipo.partido_id == partido_id,
                                                   CobroEquipo.equipo_id == equipo_id))
            if not c:
                c = CobroEquipo(partido_id=partido_id, equipo_id=equipo_id)
                s.add(c)
            c.cuota_centavos = cuota_final
            c.desglose = _desglose_a_texto(linea.desglose)
            c.pagado_centavos = pagado
            c.fecha_pago = (fecha or c.fecha_pago or date.today()) if pagado else None
            c.forma_pago = forma_pago
            c.nota = (nota or "").strip() or None

    def pago_completo(self, claves: list[tuple[int, int]], fecha: date | None = None,
                      forma_pago: str | None = None) -> int:
        """Marca que esos equipos pagaron su cuota completa. Devuelve cuántos cambió."""
        cambiados = 0
        for partido_id, equipo_id in claves:
            linea = self._linea(partido_id, equipo_id)
            if linea.saldo == 0:
                continue
            self.registrar(partido_id, equipo_id, linea.cuota, fecha=fecha,
                           forma_pago=forma_pago or linea.forma_pago, nota=linea.nota or "")
            cambiados += 1
        return cambiados

    def deshacer(self, partido_id: int, equipo_id: int) -> None:
        """Borra lo registrado: el equipo vuelve a deber su cuota normal."""
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
        raise ErrorValidacion("Este partido no tiene arbitraje que cobrar (¿está cancelado o sin tarifas?).")

    # --- Texto para WhatsApp -------------------------------------------------

    def recibo_texto(self, r: ReciboEquipo) -> str:
        lineas = [f"🧾 *Recibo de arbitrajes · {r.equipo.nombre}*", f"_{r.liga.nombre} · {r.periodo}_", ""]
        if not r.lineas:
            lineas.append("Sin partidos en este periodo.")
            return "\n".join(lineas)
        for l in r.lineas:
            p = l.partido
            lineas.append(f"*{fecha_larga(p.fecha)} {p.hora:%H:%M}* · vs {l.rival.nombre} ({l.jornada})")
            for posicion, monto in l.desglose:
                lineas.append(f"   {POSICIONES[posicion]}: {formatear_monto(monto)}")
            if l.ajuste:
                lineas.append(f"   Ajuste: {'+' if l.ajuste > 0 else '−'}{formatear_monto(abs(l.ajuste))}")
            estado = "✅ Pagado" if l.saldo == 0 else f"Debe *{formatear_monto(l.saldo)}*"
            pagado = f" · pagó {formatear_monto(l.pagado)}" if l.pagado and l.saldo else ""
            lineas.append(f"   Cuota {formatear_monto(l.cuota)}{pagado} · {estado}")
            lineas.append("")
        lineas += [f"Total: {formatear_monto(r.total)}", f"Pagado: {formatear_monto(r.pagado)}",
                   f"*Saldo pendiente: {formatear_monto(r.saldo)}*", "", f"_{ORGANIZACION}_"]
        return "\n".join(lineas)
