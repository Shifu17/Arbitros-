import pytest

from arbitros.services.arbitros import (
    FILTRO_INACTIVOS,
    FILTRO_TODOS,
    ArbitroService,
    DatosArbitro,
    enlace_whatsapp,
    formatear_telefono,
    normalizar_telefono,
)
from arbitros.services.errores import ErrorValidacion


@pytest.fixture
def svc(db):
    return ArbitroService(db)


def test_normalizar_telefono():
    assert normalizar_telefono(" (33) 1234-5678 ") == "3312345678"
    assert normalizar_telefono("+52 33 1234 5678") == "+523312345678"
    assert formatear_telefono("3312345678") == "33 1234 5678"
    assert enlace_whatsapp("3312345678") == "https://wa.me/523312345678"
    assert enlace_whatsapp("+13055551234") == "https://wa.me/13055551234"


def test_crear_y_listar(svc):
    svc.crear(DatosArbitro(nombre="  Juan   Pérez ", telefono="33 1234 5678", apodo="Juancho"))
    svc.crear(DatosArbitro(nombre="Ana López", telefono="3311112222", categoria="A"))
    lista = svc.listar()
    assert [a.nombre for a in lista] == ["Ana López", "Juan Pérez"]
    assert lista[1].telefono == "3312345678"
    assert svc.contar_activos() == 2


def test_busqueda(svc):
    svc.crear(DatosArbitro(nombre="Juan Pérez", telefono="3312345678", apodo="Juancho"))
    svc.crear(DatosArbitro(nombre="Ana López", telefono="3311112222", categoria="Juvenil"))
    assert [a.nombre for a in svc.listar("juanch")] == ["Juan Pérez"]
    assert [a.nombre for a in svc.listar("1111")] == ["Ana López"]
    assert [a.nombre for a in svc.listar("juvenil")] == ["Ana López"]
    assert [a.nombre for a in svc.listar("PEREZ")] == ["Juan Pérez"]


def test_validaciones(svc):
    with pytest.raises(ErrorValidacion) as e:
        svc.crear(DatosArbitro(nombre=" ", telefono="123"))
    assert set(e.value.campos) == {"nombre", "telefono"}


def test_telefono_duplicado(svc):
    svc.crear(DatosArbitro(nombre="Juan", telefono="3312345678"))
    with pytest.raises(ErrorValidacion) as e:
        svc.crear(DatosArbitro(nombre="Pedro", telefono="33-1234-5678"))
    assert "Juan" in e.value.campos["telefono"]


def test_actualizar_conserva_su_telefono(svc):
    a = svc.crear(DatosArbitro(nombre="Juan", telefono="3312345678"))
    svc.actualizar(a.id, DatosArbitro(nombre="Juan Pérez", telefono="3312345678", notas="ok"))
    assert svc.obtener(a.id).nombre == "Juan Pérez"


def test_filtro_activos(svc):
    a = svc.crear(DatosArbitro(nombre="Juan", telefono="3312345678"))
    svc.crear(DatosArbitro(nombre="Ana", telefono="3311112222"))
    svc.cambiar_activo(a.id, False)
    assert [x.nombre for x in svc.listar()] == ["Ana"]
    assert [x.nombre for x in svc.listar(filtro=FILTRO_INACTIVOS)] == ["Juan"]
    assert len(svc.listar(filtro=FILTRO_TODOS)) == 2
