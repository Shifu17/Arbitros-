from datetime import date, time
from urllib.parse import unquote

import pytest

from arbitros.db.models import ESTADO_CANCELADO
from arbitros.services.arbitros import ArbitroService, DatosArbitro
from arbitros.services.asignaciones import AsignacionService
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.jornadas import DatosPartido, JornadaService
from arbitros.services.ligas import DatosLiga, LigaService
from arbitros.services.rol import AGRUPAR_ARBITRO, AGRUPAR_HORA, OpcionesRol, RolService
from arbitros.services.rol_imagen import generar_png

SAB = date(2026, 10, 24)


@pytest.fixture
def ctx(db):
    ligas, jornadas, arbitros = LigaService(db), JornadaService(db), ArbitroService(db)
    asig = AsignacionService(db, ConfiguracionService(db))
    rol = RolService(db, jornadas, asig)
    liga = ligas.crear(DatosLiga(nombre="Liga Sabatina", posiciones=["central", "asistente_1"]))
    oro = ligas.categorias.crear(liga.id, "Oro")
    ligas.equipos.crear_varios(liga.id, "Tigres\nPumas\nÁguilas\nToros\nLeones\nHalcones", categoria_id=oro.id)
    c1 = ligas.campos.crear(liga.id, "Campo 1")
    c2 = ligas.campos.crear(liga.id, "Campo 2")
    eq = {e.nombre: e.id for e in ligas.equipos.listar(liga.id)}
    j = jornadas.crear(liga.id, SAB)

    def partido(local, visitante, campo, hora):
        return jornadas.crear_partido(j.id, DatosPartido(SAB, hora, eq[local], eq[visitante], campo.id,
                                                         ["central", "asistente_1"], categoria_id=oro.id), forzar=True)

    p1 = partido("Tigres", "Pumas", c1, time(9))
    p2 = partido("Águilas", "Toros", c2, time(9))
    p3 = partido("Leones", "Halcones", c1, time(11))
    juan = arbitros.crear(DatosArbitro(nombre="Juan Pérez", telefono="3311111111", apodo="Juanito"))
    ana = arbitros.crear(DatosArbitro(nombre="Ana López", telefono="3322222222"))
    asig.asignar(p1.id, "central", juan.id, forzar=True)
    asig.asignar(p1.id, "asistente_1", ana.id, forzar=True)
    asig.asignar(p3.id, "central", juan.id, forzar=True)
    return dict(rol=rol, jornadas=jornadas, asig=asig, j=j, p1=p1, p2=p2, p3=p3, juan=juan, ana=ana, oro=oro, liga=liga)


def test_texto_por_campo(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(nota="Llegar 20 min antes"))
    assert "*LIGA SABATINA*" in texto and "Jornada 1" in texto and "Sábado 24 de octubre" in texto
    assert texto.index("CAMPO 1") < texto.index("CAMPO 2")
    # Dentro de Campo 1, el de las 9 antes que el de las 11
    assert texto.index("Tigres vs Pumas") < texto.index("Leones vs Halcones")
    assert "Central: Juan Pérez" in texto and "_Por asignar_" in texto
    assert "Faltan 3 árbitros por confirmar" in texto and "📌 Llegar 20 min antes" in texto


def test_texto_por_hora_y_apodos(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(agrupar=AGRUPAR_HORA, usar_apodos=True))
    assert "🕒 *09:00*" in texto and "Central: Juanito" in texto
    assert texto.index("09:00") < texto.index("11:00")


def test_texto_por_arbitro(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(agrupar=AGRUPAR_ARBITRO))
    assert texto.index("Ana López") < texto.index("Juan Pérez")
    assert texto.count("Juan Pérez") == 1 and "(Central)" in texto


def test_cancelados(ctx):
    ctx["jornadas"].cambiar_estado([ctx["p2"].id], ESTADO_CANCELADO, "Lluvia")
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol())
    assert "CANCELADOS" in texto and "Lluvia" in texto
    assert "CAMPO 2" not in texto
    sin = ctx["rol"].texto(ctx["j"].id, OpcionesRol(incluir_cancelados=False))
    assert "CANCELADOS" not in sin


def test_filtro_categoria(ctx):
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol(categoria_id=ctx["oro"].id))
    assert "Categoría: *Oro*" in texto
    assert "No hay partidos" in ctx["rol"].texto(ctx["j"].id, OpcionesRol(categoria_id=999))


def test_mensajes_individuales(ctx):
    mensajes = ctx["rol"].mensajes_individuales(ctx["j"].id)
    assert [a.nombre for a, _, _ in mensajes] == ["Ana López", "Juan Pérez"]
    _, texto, enlace = mensajes[1]
    assert texto.startswith("Hola Juanito") and texto.count("🏟️") == 2
    assert enlace.startswith("https://wa.me/523311111111?text=") and unquote(enlace.split("text=")[1]) == texto


def test_cambios_desde_publicacion(ctx):
    rol, asig, jornadas = ctx["rol"], ctx["asig"], ctx["jornadas"]
    assert rol.cambios(ctx["j"].id) is None
    rol.publicar(ctx["j"].id)
    assert rol.cambios(ctx["j"].id) == []
    asig.quitar(ctx["p1"].id, "asistente_1")
    asig.asignar(ctx["p1"].id, "central", ctx["ana"].id, forzar=True)
    jornadas.cambiar_estado([ctx["p2"].id], ESTADO_CANCELADO, "Lluvia")
    p3 = ctx["p3"]
    jornadas.actualizar_partido(p3.id, DatosPartido(SAB, time(12), p3.local_id, p3.visitante_id, p3.campo_id,
                                                    p3.lista_posiciones, categoria_id=p3.categoria_id), forzar=True)
    cambios = rol.cambios(ctx["j"].id)
    texto = "\n".join(cambios)
    assert "Central: Juan Pérez → *Ana López*" in texto
    assert "Asistente 1: Ana López → *Por asignar*" in texto
    assert "CANCELADO" in texto and "Lluvia" in texto
    assert "ahora Sábado 24 de octubre 12:00" in texto and "antes Sábado 24 de octubre 11:00" in texto
    assert rol.texto_cambios(ctx["j"].id).startswith("🔄 *CAMBIOS AL ROL")
    rol.publicar(ctx["j"].id)
    assert rol.cambios(ctx["j"].id) == []


def test_partido_nuevo_y_eliminado_en_cambios(ctx):
    rol, jornadas = ctx["rol"], ctx["jornadas"]
    rol.publicar(ctx["j"].id)
    jornadas.eliminar_partido(ctx["p2"].id)
    texto = "\n".join(rol.cambios(ctx["j"].id))
    assert "Se quitó" in texto and "Águilas vs Toros" in texto


def test_imagen_png(ctx):
    datos = ctx["rol"].datos(ctx["j"].id, OpcionesRol(nota="Llegar 20 minutos antes"))
    png = generar_png(datos, OpcionesRol(nota="Llegar 20 minutos antes"))
    assert png[:8] == b"\x89PNG\r\n\x1a\n" and len(png) > 5000
    png_hora = generar_png(datos, OpcionesRol(agrupar=AGRUPAR_HORA))
    assert png_hora[:4] == b"\x89PNG"


def test_imagen_con_la_marca_del_colegio(ctx):
    from io import BytesIO

    from PIL import Image

    from arbitros import colegios

    datos = ctx["rol"].datos(ctx["j"].id, OpcionesRol())
    colegios.activar(colegios.SALTILLO)
    imagen = Image.open(BytesIO(generar_png(datos, OpcionesRol()))).convert("RGB")
    # El encabezado se pinta con el azul marino de Saltillo, no con el negro de Coahuila
    assert imagen.getpixel((60, 60)) == (0x0B, 0x1F, 0x4B)


def test_designacion_con_fotos_y_logo_de_liga(ctx, rutas, tmp_path):
    from io import BytesIO

    from PIL import Image

    from arbitros import colegios
    from arbitros.services.imagenes import ImagenService

    rojo, verde = (220, 20, 20), (20, 160, 60)
    Image.new("RGB", (600, 800), rojo).save(tmp_path / "juan.jpg")
    Image.new("RGB", (300, 300), verde).save(tmp_path / "liga.png")
    imagenes = ImagenService(ctx["rol"].db, rutas)
    imagenes.guardar_foto(ctx["juan"].id, tmp_path / "juan.jpg")
    imagenes.guardar_logo(ctx["liga"].id, tmp_path / "liga.png")

    def colores(png: bytes) -> set:
        return {c for _, c in Image.open(BytesIO(png)).convert("RGB").getcolors(1 << 24)}

    # Coahuila: sigue siendo «Rol arbitral», sin fotos ni logo de la liga
    datos = ctx["rol"].datos(ctx["j"].id, OpcionesRol())
    assert "Rol arbitral" in ctx["rol"].texto(ctx["j"].id, OpcionesRol())
    assert not {rojo, verde} & colores(generar_png(datos, OpcionesRol(), rutas.documentos))

    colegios.activar(colegios.SALTILLO)
    datos = ctx["rol"].datos(ctx["j"].id, OpcionesRol())
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol())
    assert "Designación arbitral" in texto and "Rol arbitral" not in texto
    assert {rojo, verde} <= colores(generar_png(datos, OpcionesRol(), rutas.documentos))
    # Sin la carpeta de documentos (o si se borran las imágenes) sale con iniciales y el logo del colegio
    assert generar_png(datos, OpcionesRol(agrupar=AGRUPAR_HORA))[:4] == b"\x89PNG"


def test_fotos_y_logos(db, rutas, tmp_path):
    from PIL import Image

    from arbitros.services.errores import ErrorValidacion
    from arbitros.services.imagenes import ImagenService

    arbitro = ArbitroService(db).crear(DatosArbitro(nombre="Ana López", telefono="3322222222"))
    imagenes = ImagenService(db, rutas)
    (tmp_path / "no_es_imagen.png").write_text("hola")
    with pytest.raises(ErrorValidacion):
        imagenes.guardar_foto(arbitro.id, tmp_path / "no_es_imagen.png")
    with pytest.raises(ErrorValidacion):
        imagenes.guardar_foto(arbitro.id, tmp_path / "foto.gif")

    Image.new("RGB", (800, 600), "blue").save(tmp_path / "foto.jpg")
    imagenes.guardar_foto(arbitro.id, tmp_path / "foto.jpg")
    arbitro = ArbitroService(db).obtener(arbitro.id)
    ruta = imagenes.ruta(arbitro.foto)
    assert ruta and ruta.is_relative_to(rutas.documentos) and Image.open(ruta).size == (400, 400)

    imagenes.quitar_foto(arbitro.id)
    assert ArbitroService(db).obtener(arbitro.id).foto is None and not ruta.exists()


def test_partido_de_bardas_en_rol(ctx):
    p = ctx["p2"]
    ctx["jornadas"].actualizar_partido(p.id, DatosPartido(SAB, p.hora, p.local_id, p.visitante_id, p.campo_id,
                                                          ["central", "central_2", "anotador"],
                                                          categoria_id=p.categoria_id, modalidad="bardas"),
                                       forzar=True)
    ctx["asig"].asignar(p.id, "anotador", ctx["ana"].id, forzar=True)
    texto = ctx["rol"].texto(ctx["j"].id, OpcionesRol())
    assert "_Fútbol de bardas_" in texto and "📝 Anotador: Ana López" in texto and "Central 2: _Por asignar_" in texto
    png = generar_png(ctx["rol"].datos(ctx["j"].id), OpcionesRol())
    assert png.startswith(bytes([0x89]) + b"PNG")
