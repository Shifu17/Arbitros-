"""Respaldos en ZIP de la base de datos y los documentos (cédulas).

Formato del ZIP:
    manifest.json      versión de la app y fecha
    arbitros.db        copia consistente de SQLite (API de backup)
    documentos/...     archivos adjuntos
"""

import json
import shutil
import sqlite3
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

from arbitros import __version__
from arbitros.config import Rutas
from arbitros.db.database import Database
from arbitros.db.migrar import configuracion_alembic
from arbitros.services.errores import ErrorValidacion

PREFIJO_MANUAL = "respaldo_"
PREFIJO_AUTO = "auto_"
PREFIJO_PREVIO = "antes_de_restaurar_"
MAX_AUTOMATICOS = 10
DIAS_ENTRE_AUTOMATICOS = 7
_FORMATO_FECHA = "%Y%m%d_%H%M%S"


@dataclass
class InfoRespaldo:
    ruta: Path
    fecha: datetime
    tamano_bytes: int
    automatico: bool


class RespaldoService:
    def __init__(self, db: Database, rutas: Rutas):
        self.db = db
        self.rutas = rutas

    def crear(self, destino: Path | None = None, prefijo: str = PREFIJO_MANUAL) -> Path:
        carpeta = destino or self.rutas.respaldos
        carpeta.mkdir(parents=True, exist_ok=True)
        ahora = datetime.now()
        sello = ahora.strftime(_FORMATO_FECHA)
        archivo = carpeta / f"{prefijo}{sello}.zip"
        n = 1
        while archivo.exists():
            n += 1
            archivo = carpeta / f"{prefijo}{sello}_{n}.zip"
        with tempfile.TemporaryDirectory() as tmp:
            copia_db = Path(tmp) / "arbitros.db"
            self._copiar_sqlite(self.rutas.db, copia_db)
            manifest = {"app": "arbitros", "version": __version__, "fecha": ahora.isoformat()}
            with zipfile.ZipFile(archivo, "w", zipfile.ZIP_DEFLATED) as z:
                z.writestr("manifest.json", json.dumps(manifest, indent=2))
                z.write(copia_db, "arbitros.db")
                for f in sorted(self.rutas.documentos.rglob("*")):
                    if f.is_file():
                        z.write(f, PurePosixPath("documentos", *f.relative_to(self.rutas.documentos).parts))
        return archivo

    def listar(self) -> list[InfoRespaldo]:
        infos = []
        for f in self.rutas.respaldos.glob("*.zip"):
            fecha = _fecha_de_nombre(f.name)
            if fecha:
                infos.append(InfoRespaldo(f, fecha, f.stat().st_size, f.name.startswith(PREFIJO_AUTO)))
        return sorted(infos, key=lambda i: i.fecha, reverse=True)

    def ultimo(self) -> InfoRespaldo | None:
        respaldos = self.listar()
        return respaldos[0] if respaldos else None

    def respaldo_automatico_si_toca(self, ahora: datetime | None = None) -> Path | None:
        """Crea un respaldo automático si el último tiene más de DIAS_ENTRE_AUTOMATICOS días."""
        ahora = ahora or datetime.now()
        ultimo = self.ultimo()
        if ultimo and ahora - ultimo.fecha < timedelta(days=DIAS_ENTRE_AUTOMATICOS):
            return None
        ruta = self.crear(prefijo=PREFIJO_AUTO)
        self._podar_automaticos()
        return ruta

    def restaurar(self, archivo_zip: Path) -> Path:
        """Reemplaza los datos actuales por los del ZIP.

        Antes crea un respaldo de seguridad (lo devuelve). Después de restaurar,
        quien llama debe volver a ejecutar las migraciones y recargar la sesión.
        """
        with tempfile.TemporaryDirectory() as tmp:
            extraido = Path(tmp)
            self._extraer_validando(archivo_zip, extraido)
            previo = self.crear(prefijo=PREFIJO_PREVIO)
            self.db.cerrar()
            shutil.copy2(extraido / "arbitros.db", self.rutas.db)
            if self.rutas.documentos.exists():
                shutil.rmtree(self.rutas.documentos)
            docs = extraido / "documentos"
            if docs.exists():
                shutil.copytree(docs, self.rutas.documentos)
            else:
                self.rutas.documentos.mkdir(parents=True, exist_ok=True)
        return previo

    def _extraer_validando(self, archivo_zip: Path, destino: Path) -> None:
        try:
            z = zipfile.ZipFile(archivo_zip)
        except (zipfile.BadZipFile, OSError):
            raise ErrorValidacion("El archivo no es un respaldo válido (no es un ZIP).")
        with z:
            nombres = z.namelist()
            if "manifest.json" not in nombres or "arbitros.db" not in nombres:
                raise ErrorValidacion("El archivo no es un respaldo de Árbitros.")
            for nombre in nombres:
                if not _ruta_permitida(nombre):
                    raise ErrorValidacion("El respaldo contiene archivos no permitidos.")
            try:
                manifest = json.loads(z.read("manifest.json"))
            except ValueError:
                raise ErrorValidacion("El respaldo está dañado (manifest).")
            if manifest.get("app") != "arbitros":
                raise ErrorValidacion("El archivo no es un respaldo de Árbitros.")
            z.extractall(destino)
        self._validar_version_db(destino / "arbitros.db")

    def _validar_version_db(self, ruta_db: Path) -> None:
        try:
            con = sqlite3.connect(ruta_db)
            try:
                fila = con.execute("SELECT version_num FROM alembic_version").fetchone()
            finally:
                con.close()
        except sqlite3.DatabaseError:
            raise ErrorValidacion("La base de datos del respaldo está dañada.")
        if not fila:
            raise ErrorValidacion("La base de datos del respaldo está incompleta.")
        scripts = ScriptDirectory.from_config(configuracion_alembic(self.db))
        try:
            scripts.get_revision(fila[0])
        except CommandError:
            raise ErrorValidacion(
                "Este respaldo es de una versión más nueva de la app. Actualiza la app e inténtalo otra vez."
            )

    def _podar_automaticos(self) -> None:
        automaticos = [r for r in self.listar() if r.automatico]
        for r in automaticos[MAX_AUTOMATICOS:]:
            r.ruta.unlink(missing_ok=True)

    @staticmethod
    def _copiar_sqlite(origen: Path, destino: Path) -> None:
        src = sqlite3.connect(origen)
        dst = sqlite3.connect(destino)
        try:
            src.backup(dst)
        finally:
            dst.close()
            src.close()


def _ruta_permitida(nombre: str) -> bool:
    ruta = PurePosixPath(nombre)
    if ruta.is_absolute() or ".." in ruta.parts or "\\" in nombre or ":" in nombre:
        return False
    return nombre in ("manifest.json", "arbitros.db") or ruta.parts[0] == "documentos"


def _fecha_de_nombre(nombre: str) -> datetime | None:
    for prefijo in (PREFIJO_MANUAL, PREFIJO_AUTO, PREFIJO_PREVIO):
        if nombre.startswith(prefijo):
            try:
                return datetime.strptime(nombre[len(prefijo):len(prefijo) + 15], _FORMATO_FECHA)
            except ValueError:
                return None
    return None
