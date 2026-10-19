"""Rol arbitral de una jornada: texto para WhatsApp, mensajes por árbitro y control de cambios.

El rol se arma a partir de `RolJornada` (datos ya resueltos: nombres, posiciones,
estado), que también usa el generador de imagen (`rol_imagen.py`).
"""

import json
from dataclasses import dataclass, field
from datetime import date, datetime, time
from urllib.parse import quote

from arbitros.db.database import Database
from arbitros.db.models import POSICIONES, Arbitro, Jornada, Liga
from arbitros.services.arbitros import enlace_whatsapp
from arbitros.services.asignaciones import AsignacionService
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import JornadaService, etiqueta_jornada
from arbitros.services.texto import fecha_larga, sin_acentos

AGRUPAR_CAMPO = "campo"
AGRUPAR_HORA = "hora"
AGRUPAR_ARBITRO = "arbitro"

POR_ASIGNAR = "Por asignar"


@dataclass
class OpcionesRol:
    agrupar: str = AGRUPAR_CAMPO
    categoria_id: int | None = None  # None = todas
    usar_apodos: bool = False
    incluir_cancelados: bool = True
    nota: str = ""


@dataclass
class ArbitroEnRol:
    posicion: str
    arbitro: Arbitro | None  # None = por asignar

    def nombre(self, usar_apodos: bool) -> str:
        if self.arbitro is None:
            return POR_ASIGNAR
        return (self.arbitro.apodo or self.arbitro.nombre) if usar_apodos else self.arbitro.nombre


@dataclass
class PartidoEnRol:
    id: int
    fecha: date
    hora: time
    campo: str
    categoria: str | None
    local: str
    visitante: str
    se_juega: bool
    estado: str
    motivo: str | None
    arbitros: list[ArbitroEnRol] = field(default_factory=list)

    @property
    def equipos(self) -> str:
        return f"{self.local} vs {self.visitante}"


@dataclass
class RolJornada:
    liga: Liga
    jornada: Jornada
    titulo: str  # "Jornada 5" / "Día 2"
    partidos: list[PartidoEnRol]

    @property
    def fechas(self) -> list[date]:
        return sorted({p.fecha for p in self.partidos})

    @property
    def faltantes(self) -> int:
        return sum(1 for p in self.partidos if p.se_juega for a in p.arbitros if a.arbitro is None)

    @property
    def texto_faltantes(self) -> str:
        n = self.faltantes
        return "Falta 1 árbitro por confirmar." if n == 1 else f"Faltan {n} árbitros por confirmar."


class RolService:
    def __init__(self, db: Database, jornadas: JornadaService, asignaciones: AsignacionService):
        self.db = db
        self.jornadas = jornadas
        self.asignaciones = asignaciones

    # --- Datos ---------------------------------------------------------------

    def datos(self, jornada_id: int, opciones: OpcionesRol | None = None) -> RolJornada:
        opciones = opciones or OpcionesRol()
        with self.db.sesion() as s:
            jornada = s.get(Jornada, jornada_id)
            if not jornada:
                raise ErrorValidacion("La jornada ya no existe.")
            liga = s.get(Liga, jornada.liga_id)
        asignaciones = self.asignaciones.de_jornada(jornada_id)
        partidos = []
        for p in self.jornadas.listar_partidos(jornada_id):
            if opciones.categoria_id and p.categoria_id != opciones.categoria_id:
                continue
            if not p.se_juega and not opciones.incluir_cancelados:
                continue
            del_partido = asignaciones.get(p.id, {})
            partidos.append(PartidoEnRol(
                id=p.id, fecha=p.fecha, hora=p.hora, campo=p.campo.nombre if p.campo else "Sin campo",
                categoria=p.categoria.nombre if p.categoria else None,
                local=p.local.nombre, visitante=p.visitante.nombre, se_juega=p.se_juega, estado=p.estado,
                motivo=p.motivo_estado,
                arbitros=[ArbitroEnRol(pos, del_partido[pos].arbitro if pos in del_partido else None)
                          for pos in p.lista_posiciones],
            ))
        return RolJornada(liga, jornada, etiqueta_jornada(liga, jornada), partidos)

    # --- Texto para WhatsApp -------------------------------------------------

    def texto(self, jornada_id: int, opciones: OpcionesRol) -> str:
        rol = self.datos(jornada_id, opciones)
        if opciones.agrupar == AGRUPAR_ARBITRO:
            return self._texto_por_arbitro(rol, opciones)
        lineas = self._encabezado(rol, opciones)
        if not rol.partidos:
            lineas.append("_No hay partidos para mostrar._")
        activos = [p for p in rol.partidos if p.se_juega]
        cancelados = [p for p in rol.partidos if not p.se_juega]
        varias_fechas = len({p.fecha for p in activos}) > 1
        for fecha in sorted({p.fecha for p in activos}):
            del_dia = [p for p in activos if p.fecha == fecha]
            if varias_fechas:
                lineas += ["", f"📅 *{fecha_larga(fecha).upper()}*"]
            if opciones.agrupar == AGRUPAR_CAMPO:
                for campo in sorted({p.campo for p in del_dia}, key=sin_acentos):
                    lineas += ["", "━━━━━━━━━━━━━━", f"🏟️ *{campo.upper()}*"]
                    for p in sorted((p for p in del_dia if p.campo == campo), key=lambda p: p.hora):
                        lineas += [""] + self._bloque_partido(p, opciones, mostrar_campo=False)
            else:
                for hora in sorted({p.hora for p in del_dia}):
                    lineas += ["", "━━━━━━━━━━━━━━", f"🕒 *{hora:%H:%M}*"]
                    for p in sorted((p for p in del_dia if p.hora == hora), key=lambda p: sin_acentos(p.campo)):
                        lineas += [""] + self._bloque_partido(p, opciones, mostrar_hora=False)
        if cancelados:
            lineas += ["", "━━━━━━━━━━━━━━", "❌ *CANCELADOS / SUSPENDIDOS*"]
            for p in sorted(cancelados, key=lambda p: (p.fecha, p.hora)):
                motivo = f" ({p.motivo})" if p.motivo else ""
                dia = f"{fecha_larga(p.fecha)} · " if varias_fechas else ""
                lineas.append(f"~{dia}{p.hora:%H:%M} {p.campo} · {p.equipos}~ _{p.estado}{motivo}_")
        lineas += self._pie(rol, opciones)
        return "\n".join(lineas).strip()

    def _encabezado(self, rol: RolJornada, opciones: OpcionesRol) -> list[str]:
        lineas = [f"⚽ *{rol.liga.nombre.upper()}*", f"📋 *Rol arbitral · {rol.titulo}*"]
        if opciones.categoria_id:
            categorias = {p.categoria for p in rol.partidos if p.categoria}
            if categorias:
                lineas.append(f"🏷️ Categoría: *{', '.join(sorted(categorias))}*")
        fechas = rol.fechas
        if len(fechas) == 1:
            lineas.append(f"📅 {fecha_larga(fechas[0])}")
        elif fechas:
            lineas.append(f"📅 {fecha_larga(fechas[0])} al {fecha_larga(fechas[-1]).lower()}")
        return lineas

    @staticmethod
    def _pie(rol: RolJornada, opciones: OpcionesRol) -> list[str]:
        lineas = []
        if rol.faltantes:
            lineas += ["", f"⚠️ _{rol.texto_faltantes}_"]
        if opciones.nota.strip():
            lineas += ["", "━━━━━━━━━━━━━━", f"📌 {opciones.nota.strip()}"]
        return lineas

    @staticmethod
    def _bloque_partido(p: PartidoEnRol, opciones: OpcionesRol, mostrar_hora: bool = True,
                        mostrar_campo: bool = True) -> list[str]:
        partes = []
        if mostrar_hora:
            partes.append(f"🕒 *{p.hora:%H:%M}*")
        if mostrar_campo:
            partes.append(f"🏟️ {p.campo}")
        if p.categoria:
            partes.append(f"_{p.categoria}_")
        lineas = []
        if partes:
            lineas.append(" · ".join(partes))
        lineas.append(f"*{p.equipos}*")
        for a in p.arbitros:
            nombre = a.nombre(opciones.usar_apodos)
            icono = "👤" if a.posicion == "central" else "🚩"
            if a.arbitro is None:
                nombre = f"_{nombre}_"
            lineas.append(f"{icono} {POSICIONES[a.posicion]}: {nombre}")
        return lineas

    def _texto_por_arbitro(self, rol: RolJornada, opciones: OpcionesRol) -> str:
        lineas = self._encabezado(rol, opciones)
        por_arbitro = self._agrupar_por_arbitro(rol)
        if not por_arbitro:
            lineas += ["", "_Todavía no hay árbitros asignados._"]
        varias_fechas = len(rol.fechas) > 1
        for arbitro, items in por_arbitro:
            nombre = (arbitro.apodo or arbitro.nombre) if opciones.usar_apodos else arbitro.nombre
            lineas += ["", f"👤 *{nombre}*"]
            for p, posicion in items:
                dia = f"{fecha_larga(p.fecha)} · " if varias_fechas else ""
                lineas.append(f"• {dia}*{p.hora:%H:%M}* · {p.campo} · {p.equipos} _({POSICIONES[posicion]})_")
        lineas += self._pie(rol, opciones)
        return "\n".join(lineas).strip()

    @staticmethod
    def _agrupar_por_arbitro(rol: RolJornada) -> list[tuple[Arbitro, list[tuple[PartidoEnRol, str]]]]:
        grupos: dict[int, tuple[Arbitro, list]] = {}
        for p in sorted(rol.partidos, key=lambda p: (p.fecha, p.hora)):
            if not p.se_juega:
                continue
            for a in p.arbitros:
                if a.arbitro:
                    grupos.setdefault(a.arbitro.id, (a.arbitro, []))[1].append((p, a.posicion))
        return sorted(grupos.values(), key=lambda g: sin_acentos(g[0].nombre))

    # --- Mensaje individual ---------------------------------------------------

    def mensajes_individuales(self, jornada_id: int) -> list[tuple[Arbitro, str, str]]:
        """[(árbitro, texto, enlace de WhatsApp con el texto ya escrito)] de quienes tienen partidos."""
        rol = self.datos(jornada_id, OpcionesRol(incluir_cancelados=False))
        resultado = []
        for arbitro, items in self._agrupar_por_arbitro(rol):
            lineas = [
                f"Hola {arbitro.apodo or arbitro.nombre.split()[0]} 👋",
                f"Tu rol para *{rol.liga.nombre} · {rol.titulo}*:",
                "",
            ]
            for p, posicion in items:
                lineas += [
                    f"📅 {fecha_larga(p.fecha)} · 🕒 *{p.hora:%H:%M}*",
                    f"🏟️ {p.campo}" + (f" · _{p.categoria}_" if p.categoria else ""),
                    f"⚽ {p.equipos}",
                    f"🧑‍⚖️ {POSICIONES[posicion]}",
                    "",
                ]
            lineas.append("Por favor confirma de recibido. ¡Gracias!")
            texto = "\n".join(lineas)
            resultado.append((arbitro, texto, f"{enlace_whatsapp(arbitro.telefono)}?text={quote(texto)}"))
        return resultado

    # --- Publicación y cambios -------------------------------------------------

    def publicar(self, jornada_id: int) -> None:
        """Guarda cómo está el rol ahora, para después avisar solo lo que cambie."""
        foto = self._foto(jornada_id)
        with self.db.sesion() as s:
            jornada = s.get(Jornada, jornada_id)
            jornada.rol_publicado = json.dumps(foto, ensure_ascii=False)
            jornada.rol_publicado_en = datetime.now()

    def cambios(self, jornada_id: int) -> list[str] | None:
        """Cambios desde la última publicación. None si nunca se publicó."""
        jornada = self.jornadas.obtener(jornada_id)
        if not jornada or not jornada.rol_publicado:
            return None
        antes = json.loads(jornada.rol_publicado)
        ahora = self._foto(jornada_id)
        lineas = []
        for pid, p in ahora.items():
            if pid not in antes:
                lineas.append(f"➕ *Nuevo:* {_desc(p)}" + _arbitros_txt(p))
                continue
            a = antes[pid]
            if a["estado_juega"] and not p["estado_juega"]:
                motivo = f" ({p['motivo']})" if p["motivo"] else ""
                lineas.append(f"❌ *{p['estado'].upper()}:* {_desc(p)}{motivo}")
                continue
            if not a["estado_juega"] and p["estado_juega"]:
                lineas.append(f"✅ *Se vuelve a jugar:* {_desc(p)}" + _arbitros_txt(p))
                continue
            if not p["estado_juega"]:
                continue
            if (a["fecha"], a["hora"], a["campo"]) != (p["fecha"], p["hora"], p["campo"]):
                lineas.append(f"🕒 *Cambio de horario/campo:* {p['equipos']} ahora {_cuando(p)} (antes {_cuando(a)})")
            for pos, nombre in p["arbitros"].items():
                previo = a["arbitros"].get(pos)
                if previo != nombre:
                    lineas.append(f"👤 {p['equipos']} ({p['hora']} {p['campo']}) · {POSICIONES[pos]}: "
                                  f"{previo or POR_ASIGNAR} → *{nombre or POR_ASIGNAR}*")
        for pid, a in antes.items():
            if pid not in ahora:
                lineas.append(f"➖ *Se quitó:* {_desc(a)}")
        return lineas

    def texto_cambios(self, jornada_id: int) -> str:
        cambios = self.cambios(jornada_id) or []
        rol = self.datos(jornada_id)
        lineas = [f"🔄 *CAMBIOS AL ROL · {rol.liga.nombre} · {rol.titulo}*", ""]
        lineas += cambios or ["Sin cambios."]
        return "\n".join(lineas)

    def _foto(self, jornada_id: int) -> dict:
        rol = self.datos(jornada_id)
        return {
            str(p.id): {
                "fecha": p.fecha.isoformat(), "hora": f"{p.hora:%H:%M}", "campo": p.campo, "equipos": p.equipos,
                "estado": p.estado, "estado_juega": p.se_juega, "motivo": p.motivo,
                "arbitros": {a.posicion: (a.arbitro.nombre if a.arbitro else None) for a in p.arbitros},
            }
            for p in rol.partidos
        }


def _cuando(p: dict) -> str:
    d = date.fromisoformat(p["fecha"])
    return f"{fecha_larga(d)} {p['hora']} · {p['campo']}"


def _desc(p: dict) -> str:
    return f"{_cuando(p)} · {p['equipos']}"


def _arbitros_txt(p: dict) -> str:
    nombres = [f"{POSICIONES[pos]}: {n or POR_ASIGNAR}" for pos, n in p["arbitros"].items()]
    return f" — {', '.join(nombres)}" if nombres else ""
