"""Cédulas arbitrales: archivos (PDF o fotos) por partido y excepciones.

Los archivos se copian a `documentos/cedulas/<liga>/<jornada>/` dentro de la carpeta
de datos, así quedan incluidos en los respaldos y no dependen de dónde estaba el original.
"""

import shutil
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy import select

from arbitros.config import Rutas
from arbitros.db.database import Database
from arbitros.db.models import CedulaArchivo, CedulaExcepcion, Jornada, Liga, Partido
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import etiqueta_jornada

EXTENSIONES = {".pdf", ".jpg", ".jpeg", ".png"}
TAMANO_MAXIMO = 25 * 1024 * 1024

REGISTRADA = "registrada"
EXCEPCION = "excepcion"
PENDIENTE = "pendiente"
PROXIMA = "proxima"  # el partido aún no se juega
NO_REQUERIDA = "no_requerida"  # cancelado o suspendido
NOMBRES_ESTADO = {
    REGISTRADA: "Registrada",
    EXCEPCION: "Excepción",
    PENDIENTE: "Pendiente",
    PROXIMA: "Por jugarse",
    NO_REQUERIDA: "No requerida",
}


@dataclass
class FilaCedula:
    partido: Partido
    liga: Liga
    jornada: str
    estado: str
    archivos: list[CedulaArchivo] = field(default_factory=list)
    motivo_excepcion: str | None = None


class CedulaService:
    def __init__(self, db: Database, rutas: Rutas):
        self.db = db
        self.rutas = rutas

    def listar(self, liga_id: int | None = None, jornada_id: int | None = None, desde: date | None = None,
               hasta: date | None = None, estados: set[str] | None = None) -> list[FilaCedula]:
        consulta = (
            select(Partido, Jornada, Liga)
            .join(Jornada, Partido.jornada_id == Jornada.id)
            .join(Liga, Jornada.liga_id == Liga.id)
            .order_by(Partido.fecha, Partido.hora)
        )
        if liga_id:
            consulta = consulta.where(Liga.id == liga_id)
        if jornada_id:
            consulta = consulta.where(Jornada.id == jornada_id)
        if desde:
            consulta = consulta.where(Partido.fecha >= desde)
        if hasta:
            consulta = consulta.where(Partido.fecha <= hasta)
        hoy = date.today()
        filas = []
        with self.db.sesion() as s:
            archivos: dict[int, list[CedulaArchivo]] = {}
            for a in s.scalars(select(CedulaArchivo).order_by(CedulaArchivo.id)):
                archivos.setdefault(a.partido_id, []).append(a)
            excepciones = {e.partido_id: e.motivo for e in s.scalars(select(CedulaExcepcion))}
            for p, jornada, liga in s.execute(consulta).unique():
                if p.id in archivos:
                    estado = REGISTRADA
                elif p.id in excepciones:
                    estado = EXCEPCION
                elif not p.se_juega:
                    estado = NO_REQUERIDA
                elif p.fecha > hoy:
                    estado = PROXIMA
                else:
                    estado = PENDIENTE
                if estados and estado not in estados:
                    continue
                filas.append(FilaCedula(p, liga, etiqueta_jornada(liga, jornada), estado,
                                        archivos.get(p.id, []), excepciones.get(p.id)))
        return filas

    def contar_pendientes(self) -> int:
        return len(self.listar(estados={PENDIENTE}))

    def subir(self, partido_id: int, origenes: list[Path]) -> list[CedulaArchivo]:
        if not origenes:
            raise ErrorValidacion("Elige al menos un archivo.")
        for o in origenes:
            if o.suffix.lower() not in EXTENSIONES:
                raise ErrorValidacion(f"«{o.name}» no es PDF ni imagen (JPG o PNG).")
            if not o.is_file():
                raise ErrorValidacion(f"No se encontró «{o.name}».")
            if o.stat().st_size > TAMANO_MAXIMO:
                raise ErrorValidacion(f"«{o.name}» pesa más de 25 MB.")
        with self.db.sesion() as s:
            partido = s.get(Partido, partido_id)
            if not partido:
                raise ErrorValidacion("El partido ya no existe.")
            jornada = s.get(Jornada, partido.jornada_id)
            carpeta_rel = Path("cedulas") / f"liga_{jornada.liga_id}" / f"jornada_{jornada.id}"
            carpeta = self.rutas.documentos / carpeta_rel
            carpeta.mkdir(parents=True, exist_ok=True)
            n = len(list(s.scalars(select(CedulaArchivo.id).where(CedulaArchivo.partido_id == partido_id))))
            nuevos = []
            for o in origenes:
                n += 1
                destino = carpeta / f"partido_{partido_id}_{n}{o.suffix.lower()}"
                while destino.exists():
                    n += 1
                    destino = carpeta / f"partido_{partido_id}_{n}{o.suffix.lower()}"
                shutil.copy2(o, destino)
                archivo = CedulaArchivo(partido_id=partido_id, ruta=(carpeta_rel / destino.name).as_posix(),
                                        nombre_original=o.name)
                s.add(archivo)
                nuevos.append(archivo)
            # Si ya tiene cédula, deja de ser excepción
            excepcion = s.get(CedulaExcepcion, partido_id)
            if excepcion:
                s.delete(excepcion)
            s.flush()
            return nuevos

    def ruta_absoluta(self, archivo: CedulaArchivo) -> Path:
        return self.rutas.documentos / Path(archivo.ruta)

    def quitar_archivo(self, archivo_id: int) -> None:
        with self.db.sesion() as s:
            archivo = s.get(CedulaArchivo, archivo_id)
            if not archivo:
                return
            ruta = self.ruta_absoluta(archivo)
            s.delete(archivo)
        ruta.unlink(missing_ok=True)

    def marcar_excepcion(self, partido_id: int, motivo: str) -> None:
        motivo = (motivo or "").strip()
        if not motivo:
            raise ErrorValidacion("Escribe el motivo de la excepción.", {"motivo": "Obligatorio"})
        with self.db.sesion() as s:
            s.merge(CedulaExcepcion(partido_id=partido_id, motivo=motivo))

    def quitar_excepcion(self, partido_id: int) -> None:
        with self.db.sesion() as s:
            excepcion = s.get(CedulaExcepcion, partido_id)
            if excepcion:
                s.delete(excepcion)
