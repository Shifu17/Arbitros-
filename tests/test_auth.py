import pytest

from arbitros.db.models import ROL_ADMIN, ROL_CONSULTA
from arbitros.services.auth import AuthService
from arbitros.services.errores import ErrorAutenticacion, ErrorValidacion


@pytest.fixture
def auth(db):
    return AuthService(db)


def test_primer_admin_y_login(auth):
    assert not auth.hay_usuarios()
    clave = auth.crear_admin_inicial("Admin", "Coordinador", "secreta1")
    assert len(clave) == 19 and clave.count("-") == 3
    assert auth.hay_usuarios()
    u = auth.autenticar("ADMIN ", "secreta1")
    assert u.es_admin and u.usuario == "admin"


def test_no_permite_segundo_admin_inicial(auth):
    auth.crear_admin_inicial("admin", "A", "secreta1")
    with pytest.raises(ErrorValidacion):
        auth.crear_admin_inicial("otro", "B", "secreta1")


def test_password_incorrecta(auth):
    auth.crear_admin_inicial("admin", "A", "secreta1")
    with pytest.raises(ErrorAutenticacion):
        auth.autenticar("admin", "mala")


def test_password_corta(auth):
    with pytest.raises(ErrorValidacion) as e:
        auth.crear_admin_inicial("admin", "A", "123")
    assert "password" in e.value.campos


def test_usuario_desactivado_no_entra(auth):
    auth.crear_admin_inicial("admin", "A", "secreta1")
    c = auth.crear_usuario("lector", "Lector", "secreta2", ROL_CONSULTA)
    auth.cambiar_activo(c.id, False)
    with pytest.raises(ErrorAutenticacion):
        auth.autenticar("lector", "secreta2")


def test_no_se_puede_desactivar_ultimo_admin(auth):
    auth.crear_admin_inicial("admin", "A", "secreta1")
    admin = auth.autenticar("admin", "secreta1")
    with pytest.raises(ErrorValidacion):
        auth.cambiar_activo(admin.id, False)


def test_recuperacion_con_clave(auth):
    clave = auth.crear_admin_inicial("admin", "A", "secreta1")
    # Acepta minúsculas y sin guiones
    nueva_clave = auth.recuperar_con_clave(clave.lower().replace("-", ""), "admin", "nueva123")
    assert nueva_clave != clave
    auth.autenticar("admin", "nueva123")
    # La clave anterior deja de servir
    with pytest.raises(ErrorAutenticacion):
        auth.recuperar_con_clave(clave, "admin", "otra1234")


def test_recuperacion_solo_admins(auth):
    clave = auth.crear_admin_inicial("admin", "A", "secreta1")
    auth.crear_usuario("lector", "Lector", "secreta2", ROL_CONSULTA)
    with pytest.raises(ErrorAutenticacion):
        auth.recuperar_con_clave(clave, "lector", "nueva123")


def test_cambiar_password(auth):
    auth.crear_admin_inicial("admin", "A", "secreta1")
    u = auth.autenticar("admin", "secreta1")
    with pytest.raises(ErrorValidacion):
        auth.cambiar_password(u.id, "mala", "nueva123")
    auth.cambiar_password(u.id, "secreta1", "nueva123")
    auth.autenticar("admin", "nueva123")


def test_usuario_duplicado(auth):
    auth.crear_admin_inicial("admin", "A", "secreta1")
    with pytest.raises(ErrorValidacion):
        auth.crear_usuario("Admin", "B", "secreta1", ROL_ADMIN)



def test_usuario_y_nombre_validos(auth):
    with pytest.raises(ErrorValidacion) as e:
        auth.crear_admin_inicial("mi usuario", "Juan 99", "secreta1")
    assert set(e.value.campos) == {"usuario", "nombre"}
    auth.crear_admin_inicial("coordinador.saul", "Saúl Pérez", "secreta1")
