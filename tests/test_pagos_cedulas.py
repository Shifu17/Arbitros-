from datetime import date, time, timedelta

import openpyxl
import pytest

from arbitros.db.models import ESTADO_CANCELADO
from arbitros.services.arbitros import ArbitroService, DatosArbitro
from arbitros.services.asignaciones import AsignacionService
from arbitros.services.cedulas import EXCEPCION, NO_REQUERIDA, PENDIENTE, PROXIMA, REGISTRADA, CedulaService
from arbitros.services.cobros import CobroService
from arbitros.services.configuracion import ConfiguracionService
from arbitros.services.errores import ErrorValidacion
from arbitros.services.jornadas import DatosPartido, JornadaService
from arbitros.services.ligas import DatosLiga, LigaService
from arbitros.services.pagos import PagoService
from arbitros.services.reportes import ReporteService

AYER = date.today() - timedelta(days=1)
MANANA = date.today() + timedelta(days=1)


@pytest.fixture
def ctx(db, rutas):
    ligas, jornadas, arbitros = LigaService(db), JornadaService(db), ArbitroService(db)
    asig = AsignacionService(db, ConfiguracionService(db))
    pagos = PagoService(db, ligas)
    cedulas = CedulaService(db, rutas)
    liga = ligas.crear(DatosLiga(nombre="Liga A", posiciones=["central", "asistente_1"]))
    ligas.configurar_posiciones_y_tarifas(liga.id, ["central", "asistente_1"], {"central": 35000, "asistente_1": 20000})
    premier = ligas.categorias.crear(liga.id, "Premier")
    ligas.configurar_categoria(premier.id, None, {"central": 50000, "asistente_1": 30000})
    libre = ligas.categorias.crear(liga.id, "Libre")  # sin tarifas propias: usa las de la liga
    ligas.equipos.crear_varios(liga.id, "Tigres\nPumas\nÁguilas\nToros\nLeones\nHalcones")
    campo = ligas.campos.crear(liga.id, "Campo 1")
    eq = {e.nombre: e.id for e in ligas.equipos.listar(liga.id)}
    j1 = jornadas.crear(liga.id, AYER)
    j2 = jornadas.crear(liga.id, MANANA)

    def partido(j, fecha, local, visitante, hora, categoria_id=libre.id):
        return jornadas.crear_partido(j.id, DatosPartido(fecha, hora, eq[local], eq[visitante], campo.id,
                                                         ["central", "asistente_1"], categoria_id=categoria_id),
                                      forzar=True)

    p1 = partido(j1, AYER, "Tigres", "Pumas", time(9))
    p2 = partido(j1, AYER, "Águilas", "Toros", time(11), premier.id)
    p3 = partido(j2, MANANA, "Leones", "Halcones", time(9))
    juan = arbitros.crear(DatosArbitro(nombre="Juan Pérez", telefono="3311111111"))
    ana = arbitros.crear(DatosArbitro(nombre="Ana López", telefono="3322222222"))
    for p in (p1, p2, p3):
        asig.asignar(p.id, "central", juan.id, forzar=True)
    asig.asignar(p1.id, "asistente_1", ana.id, forzar=True)
    return dict(ligas=ligas, jornadas=jornadas, pagos=pagos, cedulas=cedulas, cobros=CobroService(db, ligas),
                rutas=rutas, liga=liga, j1=j1,
                p1=p1, p2=p2, p3=p3, juan=juan, ana=ana, premier=premier)


def _linea(ctx, partido, arbitro):
    return next(l for l in ctx["pagos"].lineas() if l.partido.id == partido.id and l.arbitro.id == arbitro.id)


def test_tarifas_por_liga_y_categoria(ctx):
    assert _linea(ctx, ctx["p1"], ctx["juan"]).tarifa == 35000
    assert _linea(ctx, ctx["p1"], ctx["ana"]).tarifa == 20000
    assert _linea(ctx, ctx["p2"], ctx["juan"]).tarifa == 50000  # Premier paga más


def test_resumen_pendiente_y_por_jugar(ctx):
    [ana, juan] = ctx["pagos"].resumen_por_arbitro()
    assert (juan.partidos, juan.total, juan.pendiente, juan.por_jugar) == (3, 120000, 85000, 35000)
    assert ana.pendiente == 20000


def test_pagado_en_campo_y_saldo(ctx):
    pagos = ctx["pagos"]
    l = _linea(ctx, ctx["p1"], ctx["juan"])
    pagos.registrar_en_campo(l.asignacion_id, 20000)
    l = _linea(ctx, ctx["p1"], ctx["juan"])
    assert (l.pagado_campo, l.saldo, l.tarifa_fija) == (20000, 15000, True)
    with pytest.raises(ErrorValidacion):
        pagos.registrar_en_campo(l.asignacion_id, 40000)  # más que la tarifa
    # Cambiar la tarifa de la liga ya no afecta un partido con dinero registrado
    ctx["ligas"].configurar_posiciones_y_tarifas(ctx["liga"].id, ["central"], {"central": 99900})
    assert _linea(ctx, ctx["p1"], ctx["juan"]).tarifa == 35000


def test_todo_pagado_en_campo(ctx):
    pagos = ctx["pagos"]
    ids = [l.asignacion_id for l in pagos.lineas(jornada_id=ctx["j1"].id)]
    assert pagos.todo_pagado_en_campo(ids) == 3
    assert all(l.saldo == 0 for l in pagos.lineas(jornada_id=ctx["j1"].id))


def test_liquidar_y_deshacer(ctx):
    pagos = ctx["pagos"]
    l1 = _linea(ctx, ctx["p1"], ctx["juan"])
    pagos.registrar_en_campo(l1.asignacion_id, 10000)
    pendientes = pagos.pendientes_de(ctx["juan"].id)
    assert {l.partido.id for l in pendientes} == {ctx["p1"].id, ctx["p2"].id}  # el de mañana no
    pago = pagos.liquidar(ctx["juan"].id, [l.asignacion_id for l in pendientes], nota="Transferencia")
    assert pago.monto_centavos == 25000 + 50000
    assert pagos.pendientes_de(ctx["juan"].id) == []
    with pytest.raises(ErrorValidacion):
        pagos.registrar_en_campo(l1.asignacion_id, 0)  # ya liquidada
    [(p, n)] = pagos.historial(ctx["juan"].id)
    assert n == 2 and p.nota == "Transferencia"
    assert "No tienes pagos pendientes" in pagos.estado_de_cuenta(ctx["juan"].id)
    pagos.deshacer_pago(pago.id)
    assert len(pagos.pendientes_de(ctx["juan"].id)) == 2
    assert pagos.historial() == []


def test_liquidar_validaciones(ctx):
    pagos = ctx["pagos"]
    otro = _linea(ctx, ctx["p1"], ctx["ana"])
    with pytest.raises(ErrorValidacion):
        pagos.liquidar(ctx["juan"].id, [otro.asignacion_id])
    with pytest.raises(ErrorValidacion):
        pagos.liquidar(ctx["juan"].id, [])


def test_estado_de_cuenta(ctx):
    texto = ctx["pagos"].estado_de_cuenta(ctx["juan"].id)
    assert "Juan Pérez" in texto and "*Total pendiente: $850*" in texto


def test_cancelado_no_se_paga_salvo_tarifa_manual(ctx):
    pagos, jornadas = ctx["pagos"], ctx["jornadas"]
    l = _linea(ctx, ctx["p2"], ctx["juan"])
    jornadas.cambiar_estado([ctx["p2"].id], ESTADO_CANCELADO, "Lluvia")
    assert all(x.partido.id != ctx["p2"].id for x in pagos.lineas())
    pagos.registrar_en_campo(l.asignacion_id, 0, tarifa=15000)  # se presentó: se le paga algo
    assert _linea(ctx, ctx["p2"], ctx["juan"]).saldo == 15000


def test_cedulas_estados_y_archivos(ctx, tmp_path):
    ced = ctx["cedulas"]
    estados = {f.partido.id: f.estado for f in ced.listar()}
    assert estados == {ctx["p1"].id: PENDIENTE, ctx["p2"].id: PENDIENTE, ctx["p3"].id: PROXIMA}
    foto = tmp_path / "cedula.JPG"
    foto.write_bytes(b"jpg")
    [archivo] = ced.subir(ctx["p1"].id, [foto])
    destino = ced.ruta_absoluta(archivo)
    assert destino.read_bytes() == b"jpg" and destino.is_relative_to(ctx["rutas"].documentos)
    ced.marcar_excepcion(ctx["p2"].id, "Torneo relámpago: cédula única")
    estados = {f.partido.id: f.estado for f in ced.listar()}
    assert estados[ctx["p1"].id] == REGISTRADA and estados[ctx["p2"].id] == EXCEPCION
    assert ced.contar_pendientes() == 0
    ced.quitar_archivo(archivo.id)
    assert not destino.exists() and ced.contar_pendientes() == 1
    ctx["jornadas"].cambiar_estado([ctx["p1"].id], ESTADO_CANCELADO)
    assert {f.partido.id: f.estado for f in ced.listar()}[ctx["p1"].id] == NO_REQUERIDA


def test_cedulas_validaciones(ctx, tmp_path):
    ced = ctx["cedulas"]
    malo = tmp_path / "notas.docx"
    malo.write_text("x")
    with pytest.raises(ErrorValidacion):
        ced.subir(ctx["p1"].id, [malo])
    with pytest.raises(ErrorValidacion):
        ced.marcar_excepcion(ctx["p1"].id, "  ")


def test_subir_cedula_quita_excepcion(ctx, tmp_path):
    ced = ctx["cedulas"]
    ced.marcar_excepcion(ctx["p1"].id, "Sin cédula")
    pdf = tmp_path / "c.pdf"
    pdf.write_bytes(b"%PDF")
    ced.subir(ctx["p1"].id, [pdf, pdf])
    [fila] = [f for f in ced.listar() if f.partido.id == ctx["p1"].id]
    assert fila.estado == REGISTRADA and fila.motivo_excepcion is None and len(fila.archivos) == 2


def test_reportes_y_excel(ctx, tmp_path):
    rep = ReporteService(ctx["pagos"], ctx["cedulas"], ctx["cobros"])
    filas = rep.arbitrajes(None, None)
    assert filas[0].nombre == "Juan Pérez" and filas[0].total_partidos == 3 and filas[0].por_posicion == {"central": 3}
    assert rep.partidos_por_estado(None, None)["programado"] == 3
    ruta = rep.exportar_excel(tmp_path / "reporte", AYER - timedelta(days=30), MANANA)
    libro = openpyxl.load_workbook(ruta)
    assert libro.sheetnames == ["Resumen por árbitro", "Arbitrajes", "Detalle de pagos", "Historial de pagos",
                               "Pagos de equipos", "Detalle de equipos", "Cédulas"]
    hoja = libro["Resumen por árbitro"]
    assert hoja["A5"].value == "Ana López" and hoja["F6"].value == 850.0


def _cobro(ctx, partido, local=True):
    return next(l for l in ctx["cobros"].lineas() if l.partido.id == partido.id and l.es_local == local)


def test_cada_equipo_paga_la_mitad_del_arbitraje(ctx):
    local, visita = _cobro(ctx, ctx["p1"]), _cobro(ctx, ctx["p1"], local=False)
    assert local.equipo.nombre == "Tigres" and visita.equipo.nombre == "Pumas"
    assert local.desglose == [("central", 17500), ("asistente_1", 10000)] and local.cuota == 27500
    assert visita.cuota == 27500 and local.saldo == 27500 and not local.cuota_fija
    assert _cobro(ctx, ctx["p2"]).cuota == 40000  # tarifas de Premier


def test_centavo_impar_lo_paga_el_local(ctx):
    ctx["ligas"].configurar_posiciones_y_tarifas(ctx["liga"].id, ["central", "asistente_1"],
                                                 {"central": 35001, "asistente_1": 20000})
    assert _cobro(ctx, ctx["p1"]).cuota == 27501 and _cobro(ctx, ctx["p1"], False).cuota == 27500


def test_registrar_pago_de_equipo_y_congelar_cuota(ctx):
    cob, p1 = ctx["cobros"], ctx["p1"]
    tigres = _cobro(ctx, p1).equipo
    cob.registrar(p1.id, tigres.id, 20000, fecha=AYER, forma_pago="efectivo", nota="Faltan 75")
    l = _cobro(ctx, p1)
    assert l.pagado == 20000 and l.saldo == 7500 and l.cuota_fija and l.fecha_pago == AYER and l.forma_pago == "efectivo"
    ctx["ligas"].configurar_posiciones_y_tarifas(ctx["liga"].id, ["central", "asistente_1"],
                                                 {"central": 90000, "asistente_1": 20000})
    assert _cobro(ctx, p1).cuota == 27500  # congelada
    assert _cobro(ctx, p1, False).cuota == 55000  # el visitante aún no paga: usa la tarifa nueva
    with pytest.raises(ErrorValidacion):
        cob.registrar(p1.id, tigres.id, 30000)
    with pytest.raises(ErrorValidacion):
        cob.registrar(p1.id, tigres.id, 100, forma_pago="cheque")
    with pytest.raises(ErrorValidacion):
        cob.registrar(ctx["p2"].id, tigres.id, 100)  # no juega ese partido
    # Un equipo paga todo el arbitraje: se le corrige la cuota y queda un ajuste en el desglose
    cob.registrar(p1.id, tigres.id, 55000, cuota=55000)
    l = _cobro(ctx, p1)
    assert l.saldo == 0 and l.ajuste == 27500 and l.desglose == [("central", 17500), ("asistente_1", 10000)]
    cob.deshacer(p1.id, tigres.id)
    assert _cobro(ctx, p1).pagado == 0 and not _cobro(ctx, p1).cuota_fija


def test_pago_completo_y_resumen_por_equipo(ctx):
    cob = ctx["cobros"]
    claves = [l.clave for l in cob.lineas(jornada_id=ctx["j1"].id)]
    assert len(claves) == 4 and cob.pago_completo(claves[:3], forma_pago="transferencia") == 3
    assert cob.pago_completo(claves[:3]) == 0
    resumen = {r.equipo.nombre: r for r in cob.resumen_por_equipo()}
    assert resumen["Toros"].pendiente == 40000 and resumen["Tigres"].pendiente == 0 and resumen["Tigres"].pagado == 27500
    assert resumen["Leones"].por_jugar == 27500 and resumen["Leones"].pendiente == 0


def test_cancelado_no_cobra(ctx):
    p1 = ctx["p1"]
    ctx["jornadas"].cambiar_estado([p1.id], ESTADO_CANCELADO, "Lluvia")
    assert not [l for l in ctx["cobros"].lineas() if l.partido.id == p1.id]
    with pytest.raises(ErrorValidacion):
        ctx["cobros"].registrar(p1.id, p1.local_id, 100)


def test_recibo_desglosado(ctx):
    cob, p1 = ctx["cobros"], ctx["p1"]
    cob.registrar(p1.id, p1.local_id, 27500, fecha=AYER, forma_pago="al_arbitro")
    recibo = cob.recibo(p1.local_id)
    assert recibo.equipo.nombre == "Tigres" and recibo.total == 27500 and recibo.saldo == 0
    texto = cob.recibo_texto(recibo)
    assert "Recibo de arbitrajes · Tigres" in texto and "Central: $175" in texto and "Pagado" in texto
    from arbitros.services.recibo_imagen import generar_pdf, generar_png
    assert generar_png(recibo)[1:4] == b"PNG" and generar_pdf(recibo).startswith(b"%PDF")
    vacio = cob.recibo(p1.local_id, jornada_id=ctx["j1"].id)
    assert vacio.periodo == "Jornada 1"


def test_tarifas_y_cuotas_por_tipo_de_partido(ctx):
    ligas, liga = ctx["ligas"], ctx["liga"]
    # Fútbol 11 (tipo principal): monto establecido que paga cada equipo
    ligas.configurar_posiciones_y_tarifas(liga.id, ["central", "asistente_1"], {"central": 35000, "asistente_1": 20000},
                                          cuotas_equipo={"central": 25000, "asistente_1": 15000})
    l = _cobro(ctx, ctx["p1"])
    assert l.desglose == [("central", 25000), ("asistente_1", 15000)] and l.cuota == 40000
    assert _cobro(ctx, ctx["p1"], local=False).cuota == 40000  # los dos equipos pagan lo establecido
    # Fútbol 7 con sus propios montos
    ligas.configurar_tarifas_tipo(liga.id, "futbol_7", {"central": 30000}, {"central": 20000})
    assert ligas.tarifa_para(liga.id, None, "central", "futbol_7") == 30000
    assert ligas.tarifa_para(liga.id, None, "central", "bardas") == 35000  # sin montos propios: los del principal
    p = ctx["jornadas"].crear_partido(ctx["j1"].id, DatosPartido(
        AYER, time(13), ctx["p1"].local_id, ctx["p1"].visitante_id, ctx["p1"].campo_id, ["central"],
        categoria_id=ctx["p1"].categoria_id, modalidad="futbol_7"), forzar=True)
    AsignacionService(ctx["pagos"].db, ConfiguracionService(ctx["pagos"].db)).asignar(
        p.id, "central", ctx["ana"].id, forzar=True)
    assert _linea(ctx, p, ctx["ana"]).tarifa == 30000
    assert _cobro(ctx, p).desglose == [("central", 20000)]
    # Vaciar los montos de un tipo vuelve a usar los del principal
    ligas.configurar_tarifas_tipo(liga.id, "futbol_7", {"central": 0}, {"central": None})
    assert not ligas.tiene_tarifas_propias(liga.id, "futbol_7") and _cobro(ctx, p).cuota == 25000
    # Categoría con montos propios
    ligas.configurar_categoria(ctx["premier"].id, None, {"central": 50000, "asistente_1": 30000},
                               cuotas_equipo={"central": 30000, "asistente_1": None})
    assert _cobro(ctx, ctx["p2"]).desglose == [("central", 30000), ("asistente_1", 15000)]
    with pytest.raises(ErrorValidacion):
        ligas.configurar_tarifas_tipo(liga.id, "futbol_7", {"central": 100}, {"central": -1})
