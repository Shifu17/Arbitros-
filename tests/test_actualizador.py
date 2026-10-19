import hashlib
import io
import json

import pytest

from arbitros.services.actualizador import Actualizador, ErrorActualizacion, es_mas_nueva, version_a_tupla

INSTALADOR = b"MZ" + b"x" * 5000
URL = "https://github.com/colegio/arbitros-releases/releases/download/v0.7.0/"


class Respuesta(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def servidor(release: dict | None, archivos: dict[str, bytes] | None = None, falla: bool = False):
    """Simula GitHub: la API devuelve `release` y las URLs de descarga devuelven `archivos`."""

    def abrir(peticion, timeout=None):
        if falla:
            raise OSError("sin conexión")
        url = peticion.full_url
        if "api.github.com" in url:
            return Respuesta(json.dumps(release).encode())
        return Respuesta(archivos[url])

    return abrir


def release(version="v0.7.0", con_sha=True, sha=None, url_base=URL, tamano=None):
    nombre = f"Arbitros-{version.lstrip('v')}-instalador.exe"
    activos = [{"name": nombre, "size": len(INSTALADOR) if tamano is None else tamano,
                "browser_download_url": url_base + nombre}]
    if con_sha:
        activos.append({"name": nombre + ".sha256", "size": 64, "browser_download_url": url_base + nombre + ".sha256"})
    archivos = {url_base + nombre: INSTALADOR,
                url_base + nombre + ".sha256": f"{sha or hashlib.sha256(INSTALADOR).hexdigest()}  {nombre}\n".encode()}
    return {"tag_name": version, "body": "Novedades", "assets": activos}, archivos


def test_versiones():
    assert version_a_tupla("v1.10.0") == (1, 10, 0)
    assert es_mas_nueva("0.10.0", "0.9.9") and not es_mas_nueva("0.6.0", "0.6.0")
    assert not es_mas_nueva("0.5.9", "0.6.0")


def test_buscar_y_descargar(tmp_path):
    datos, archivos = release()
    act = Actualizador("colegio/arbitros-releases", "0.6.0", servidor(datos, archivos))
    info = act.buscar()
    assert info.version == "0.7.0" and info.notas == "Novedades"
    avances = []
    ruta = act.descargar(info, tmp_path, avances.append)
    assert ruta.read_bytes() == INSTALADOR and avances[-1] == 1.0
    assert not list(tmp_path.glob("*.parcial"))


def test_al_dia(tmp_path):
    datos, archivos = release("v0.6.0")
    assert Actualizador("x/y", "0.6.0", servidor(datos, archivos)).buscar() is None


def test_sin_conexion():
    with pytest.raises(ErrorActualizacion):
        Actualizador("x/y", "0.6.0", servidor(None, falla=True)).buscar()


def test_sha_no_coincide(tmp_path):
    datos, archivos = release(sha="0" * 64)
    act = Actualizador("x/y", "0.6.0", servidor(datos, archivos))
    with pytest.raises(ErrorActualizacion):
        act.descargar(act.buscar(), tmp_path)
    assert not list(tmp_path.iterdir())


def test_descarga_incompleta(tmp_path):
    datos, archivos = release(tamano=999999)
    act = Actualizador("x/y", "0.6.0", servidor(datos, archivos))
    with pytest.raises(ErrorActualizacion):
        act.descargar(act.buscar(), tmp_path)


def test_rechaza_hosts_no_permitidos():
    datos, archivos = release(url_base="http://malicioso.example/")
    with pytest.raises(ErrorActualizacion):
        Actualizador("x/y", "0.6.0", servidor(datos, archivos)).buscar()


def test_release_sin_instalador():
    assert Actualizador("x/y", "0.6.0", servidor({"tag_name": "v0.9.0", "assets": []})).buscar() is None
