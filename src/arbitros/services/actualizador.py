"""Actualización automática desde GitHub Releases.

Al abrir la app instalada se consulta la última versión publicada en el repositorio
configurado (`config.REPO_ACTUALIZACIONES`). Si es más nueva, se descarga el instalador
(`Arbitros-<versión>-instalador.exe`), se verifica con su archivo `.sha256` y se ejecuta en
modo silencioso; el instalador cierra la app, la actualiza y la vuelve a abrir.
Los datos no se tocan: viven en %APPDATA%\\Arbitros y la base de datos se respalda antes
de migrarse en el siguiente arranque.
"""

import hashlib
import json
import logging
import re
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

log = logging.getLogger(__name__)

API = "https://api.github.com/repos/{repo}/releases/latest"
HOSTS_PERMITIDOS = {"github.com", "api.github.com", "objects.githubusercontent.com",
                    "release-assets.githubusercontent.com"}
SUFIJO_INSTALADOR = "-instalador.exe"
TAMANO_BLOQUE = 256 * 1024


class ErrorActualizacion(Exception):
    pass


@dataclass
class InfoVersion:
    version: str
    notas: str
    url_instalador: str
    nombre_archivo: str
    tamano: int
    url_sha256: str | None


def version_a_tupla(texto: str) -> tuple[int, ...]:
    """'v0.6.0' -> (0, 6, 0). Ignora sufijos como '-beta'."""
    numeros = re.findall(r"\d+", texto.split("-")[0])
    return tuple(int(n) for n in numeros) or (0,)


def es_mas_nueva(candidata: str, actual: str) -> bool:
    return version_a_tupla(candidata) > version_a_tupla(actual)


def _validar_url(url: str) -> str:
    partes = urlparse(url)
    if partes.scheme != "https" or partes.hostname not in HOSTS_PERMITIDOS:
        raise ErrorActualizacion(f"Dirección de descarga no permitida: {url}")
    return url


class Actualizador:
    def __init__(self, repo: str, version_actual: str, abrir=urllib.request.urlopen):
        self.repo = repo
        self.version_actual = version_actual
        self._abrir = abrir  # inyectable en pruebas

    def buscar(self, timeout: float = 6) -> InfoVersion | None:
        """Devuelve la versión nueva disponible, o None si ya está al día.

        Lanza ErrorActualizacion si no hay conexión o la respuesta no es válida.
        """
        peticion = urllib.request.Request(
            API.format(repo=self.repo),
            headers={"Accept": "application/vnd.github+json", "User-Agent": "Arbitros-actualizador"},
        )
        try:
            with self._abrir(peticion, timeout=timeout) as r:
                datos = json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError) as e:
            raise ErrorActualizacion(f"No se pudo consultar la última versión: {e}") from e
        version = (datos.get("tag_name") or "").lstrip("vV")
        if not version or not es_mas_nueva(version, self.version_actual):
            return None
        activos = datos.get("assets") or []
        instalador = next((a for a in activos if a.get("name", "").endswith(SUFIJO_INSTALADOR)), None)
        if not instalador:
            log.warning("La versión %s no tiene instalador publicado", version)
            return None
        sha = next((a for a in activos if a.get("name") == instalador["name"] + ".sha256"), None)
        return InfoVersion(
            version=version,
            notas=(datos.get("body") or "").strip(),
            url_instalador=_validar_url(instalador["browser_download_url"]),
            nombre_archivo=instalador["name"],
            tamano=int(instalador.get("size") or 0),
            url_sha256=_validar_url(sha["browser_download_url"]) if sha else None,
        )

    def descargar(self, info: InfoVersion, carpeta: Path,
                  progreso: Callable[[float], None] | None = None) -> Path:
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / info.nombre_archivo
        temporal = destino.with_suffix(".parcial")
        sha = hashlib.sha256()
        recibido = 0
        try:
            with self._abrir(urllib.request.Request(info.url_instalador, headers={"User-Agent": "Arbitros"}),
                             timeout=30) as r, open(temporal, "wb") as f:
                while bloque := r.read(TAMANO_BLOQUE):
                    f.write(bloque)
                    sha.update(bloque)
                    recibido += len(bloque)
                    if progreso and info.tamano:
                        progreso(min(recibido / info.tamano, 1.0))
        except OSError as e:
            temporal.unlink(missing_ok=True)
            raise ErrorActualizacion(f"Falló la descarga: {e}") from e
        if info.tamano and recibido != info.tamano:
            temporal.unlink(missing_ok=True)
            raise ErrorActualizacion("La descarga quedó incompleta. Inténtalo de nuevo.")
        if info.url_sha256:
            esperado = self._sha_publicado(info.url_sha256)
            if esperado != sha.hexdigest():
                temporal.unlink(missing_ok=True)
                raise ErrorActualizacion("El archivo descargado no coincide con el publicado (verificación SHA-256).")
        temporal.replace(destino)
        return destino

    def _sha_publicado(self, url: str) -> str:
        try:
            with self._abrir(urllib.request.Request(url, headers={"User-Agent": "Arbitros"}), timeout=15) as r:
                texto = r.read().decode("utf-8", errors="replace")
        except OSError as e:
            raise ErrorActualizacion(f"No se pudo verificar la descarga: {e}") from e
        return texto.strip().split()[0].lower() if texto.strip() else ""

    @staticmethod
    def instalar(instalador: Path) -> None:
        """Lanza el instalador en modo silencioso. Quien llama debe cerrar la app enseguida."""
        subprocess.Popen(
            [str(instalador), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"],
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            close_fds=True,
        )
