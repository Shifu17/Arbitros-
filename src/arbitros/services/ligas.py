"""Ligas/torneos y sus catálogos: equipos, campos, posiciones por defecto y tarifas."""

from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import delete, func, select

from arbitros.db.database import Database
from arbitros.db.models import (
    FUTBOL_11,
    MODALIDADES,
    POSICIONES,
    TIPO_LIGA,
    TIPO_TORNEO,
    Campo,
    Categoria,
    Equipo,
    Jornada,
    Liga,
    Partido,
    Tarifa,
    TarifaCategoria,
    nombre_modalidad,
    posiciones_a_csv,
    posiciones_no_permitidas,
)
from arbitros.services.errores import ErrorValidacion
from arbitros.services.texto import sin_acentos

MAX_DIAS_TORNEO = 7


@dataclass
class DatosLiga:
    nombre: str
    tipo: str = TIPO_LIGA
    posiciones: list[str] = field(default_factory=lambda: ["central"])
    notas: str = ""
    modalidad: str = FUTBOL_11


@dataclass
class ResumenLiga:
    liga: Liga
    equipos: int
    campos: int
    jornadas: int
    categorias: int = 0


def _texto_no_permitidas(posiciones: list[str], modalidad: str | None) -> str:
    return f"{nombre_modalidad(modalidad)} no lleva: {', '.join(POSICIONES[p] for p in posiciones)}"


def _nombre_limpio(nombre: str) -> str:
    return " ".join((nombre or "").split())


class Catalogo:
    """Altas, bajas y cambios de equipos, campos o categorías de una liga (mismo comportamiento)."""

    def __init__(self, db: Database, modelo, singular: str, columnas_uso, articulo: str = "el"):
        self.db = db
        self.modelo = modelo
        self.singular = singular
        self.articulo = articulo
        # [(columna que referencia a este catálogo, nombre de lo que la usa)], p. ej. (Partido.local_id, "partidos")
        self._columnas_uso = columnas_uso

    def listar(self, liga_id: int, solo_activos: bool = False) -> list:
        m = self.modelo
        consulta = select(m).where(m.liga_id == liga_id)
        if solo_activos:
            consulta = consulta.where(m.activo.is_(True))
        with self.db.sesion() as s:
            return sorted(s.scalars(consulta), key=lambda x: sin_acentos(x.nombre))

    def crear(self, liga_id: int, nombre: str, **extra):
        nombre = _nombre_limpio(nombre)
        with self.db.sesion() as s:
            self._validar_nombre(s, liga_id, nombre)
            nuevo = self.modelo(liga_id=liga_id, nombre=nombre, **extra)
            s.add(nuevo)
            s.flush()
            return nuevo

    def crear_varios(self, liga_id: int, texto: str, **extra) -> tuple[list[str], list[str]]:
        """Un nombre por renglón. Devuelve (creados, omitidos por repetidos)."""
        creados, omitidos = [], []
        with self.db.sesion() as s:
            existentes = {
                sin_acentos(n) for n in s.scalars(select(self.modelo.nombre).where(self.modelo.liga_id == liga_id))
            }
            for renglon in (texto or "").splitlines():
                nombre = _nombre_limpio(renglon)
                if not nombre:
                    continue
                if sin_acentos(nombre) in existentes:
                    omitidos.append(nombre)
                    continue
                s.add(self.modelo(liga_id=liga_id, nombre=nombre, **extra))
                existentes.add(sin_acentos(nombre))
                creados.append(nombre)
        return creados, omitidos

    def actualizar(self, item_id: int, nombre: str, **extra):
        nombre = _nombre_limpio(nombre)
        with self.db.sesion() as s:
            item = s.get(self.modelo, item_id)
            if not item:
                raise ErrorValidacion(f"{self.articulo.capitalize()} {self.singular} ya no existe.")
            self._validar_nombre(s, item.liga_id, nombre, excluir_id=item_id)
            item.nombre = nombre
            for k, v in extra.items():
                setattr(item, k, v)
            return item

    def cambiar_activo(self, item_id: int, activo: bool) -> None:
        with self.db.sesion() as s:
            item = s.get(self.modelo, item_id)
            if item:
                item.activo = activo

    def eliminar(self, item_id: int) -> None:
        with self.db.sesion() as s:
            usos: dict[str, int] = {}
            for columna, que in self._columnas_uso:
                n = s.scalar(select(func.count()).where(columna == item_id))
                if n:
                    usos[que] = usos.get(que, 0) + n
            if usos:
                detalle = " y ".join(f"{n} {que}" for que, n in usos.items())
                raise ErrorValidacion(
                    f"No se puede eliminar: {self.articulo} {self.singular} ya tiene {detalle}. Desactívalo en su lugar."
                )
            item = s.get(self.modelo, item_id)
            if item:
                s.delete(item)

    def _validar_nombre(self, s, liga_id: int, nombre: str, excluir_id: int | None = None) -> None:
        if not nombre:
            raise ErrorValidacion("Escribe el nombre.", {"nombre": "Escribe el nombre"})
        consulta = select(self.modelo).where(self.modelo.liga_id == liga_id)
        if excluir_id is not None:
            consulta = consulta.where(self.modelo.id != excluir_id)
        if any(sin_acentos(x.nombre) == sin_acentos(nombre) for x in s.scalars(consulta)):
            raise ErrorValidacion(f"Ya existe {'una' if self.articulo == 'la' else 'un'} {self.singular} con ese nombre.",
                                  {"nombre": "Ya existe"})


class LigaService:
    def __init__(self, db: Database):
        self.db = db
        self.equipos = Catalogo(db, Equipo, "equipo", [(Partido.local_id, "partidos"), (Partido.visitante_id, "partidos")])
        self.campos = Catalogo(db, Campo, "campo", [(Partido.campo_id, "partidos")])
        self.categorias = Catalogo(
            db, Categoria, "categoría", [(Equipo.categoria_id, "equipos"), (Partido.categoria_id, "partidos")], articulo="la"
        )

    # --- Ligas ------------------------------------------------------------

    def listar(self, activas: bool = True) -> list[ResumenLiga]:
        def conteo(modelo):
            return select(func.count(modelo.id)).where(modelo.liga_id == Liga.id).scalar_subquery()

        consulta = (
            select(Liga, conteo(Equipo), conteo(Campo), conteo(Jornada), conteo(Categoria))
            .where(Liga.activa.is_(activas))
        )
        with self.db.sesion() as s:
            resumenes = [ResumenLiga(*fila) for fila in s.execute(consulta)]
        return sorted(resumenes, key=lambda r: sin_acentos(r.liga.nombre))

    def hay_ligas(self) -> bool:
        with self.db.sesion() as s:
            return bool(s.scalar(select(func.count(Liga.id)).where(Liga.activa.is_(True))))

    def obtener(self, liga_id: int) -> Liga | None:
        with self.db.sesion() as s:
            return s.get(Liga, liga_id)

    def crear(self, datos: DatosLiga, dias_torneo: list[date] | None = None) -> Liga:
        """Para un torneo, `dias_torneo` crea sus días (jornadas) de una vez."""
        with self.db.sesion() as s:
            nombre = self._validar(s, datos)
            dias = sorted(set(dias_torneo or []))
            if datos.tipo == TIPO_TORNEO and not dias:
                raise ErrorValidacion("Indica la fecha del torneo.", {"fecha": "Escribe la fecha"})
            if len(dias) > MAX_DIAS_TORNEO:
                raise ErrorValidacion(f"Un torneo corto puede tener hasta {MAX_DIAS_TORNEO} días.")
            liga = Liga(
                nombre=nombre,
                tipo=datos.tipo,
                modalidad=datos.modalidad,
                posiciones_defecto=posiciones_a_csv(datos.posiciones),
                notas=(datos.notas or "").strip() or None,
            )
            s.add(liga)
            s.flush()
            if datos.tipo == TIPO_TORNEO:
                for i, dia in enumerate(dias, start=1):
                    s.add(Jornada(liga_id=liga.id, numero=i, fecha_inicio=dia))
            return liga

    def actualizar(self, liga_id: int, nombre: str, notas: str = "") -> Liga:
        with self.db.sesion() as s:
            liga = s.get(Liga, liga_id)
            if not liga:
                raise ErrorValidacion("La liga ya no existe.")
            liga.nombre = self._validar(s, DatosLiga(nombre=nombre, tipo=liga.tipo, posiciones=liga.lista_posiciones), liga_id)
            liga.notas = (notas or "").strip() or None
            return liga

    def cambiar_activa(self, liga_id: int, activa: bool) -> None:
        with self.db.sesion() as s:
            liga = s.get(Liga, liga_id)
            if liga:
                liga.activa = activa

    # --- Posiciones y tarifas --------------------------------------------

    def tarifas(self, liga_id: int) -> dict[str, int]:
        """Centavos por posición; las posiciones sin tarifa valen 0."""
        with self.db.sesion() as s:
            guardadas = {t.posicion: t.monto_centavos for t in s.scalars(select(Tarifa).where(Tarifa.liga_id == liga_id))}
        return {p: guardadas.get(p, 0) for p in POSICIONES}

    def configurar_posiciones_y_tarifas(self, liga_id: int, posiciones: list[str], tarifas: dict[str, int],
                                        modalidad: str | None = None) -> None:
        if modalidad is not None and modalidad not in MODALIDADES:
            raise ErrorValidacion("Tipo de partido inválido.")
        if not posiciones_a_csv(posiciones):
            raise ErrorValidacion("Marca al menos una posición por defecto.")
        if any(v < 0 for v in tarifas.values()):
            raise ErrorValidacion("Las tarifas no pueden ser negativas.")
        with self.db.sesion() as s:
            liga = s.get(Liga, liga_id)
            if not liga:
                raise ErrorValidacion("La liga ya no existe.")
            if sobran := posiciones_no_permitidas(posiciones, modalidad or liga.modalidad):
                raise ErrorValidacion(_texto_no_permitidas(sobran, modalidad or liga.modalidad))
            liga.posiciones_defecto = posiciones_a_csv(posiciones)
            if modalidad is not None:
                liga.modalidad = modalidad
            for posicion, monto in tarifas.items():
                if posicion in POSICIONES:
                    s.merge(Tarifa(liga_id=liga_id, posicion=posicion, monto_centavos=monto))

    # --- Categorías (sub-ligas) -------------------------------------------

    def tarifas_categoria(self, categoria_id: int) -> dict[str, int] | None:
        """Tarifas propias de la categoría, o None si usa las de la liga."""
        with self.db.sesion() as s:
            filas = {t.posicion: t.monto_centavos
                     for t in s.scalars(select(TarifaCategoria).where(TarifaCategoria.categoria_id == categoria_id))}
        return {p: filas.get(p, 0) for p in POSICIONES} if filas else None

    def configurar_categoria(
        self, categoria_id: int, posiciones: list[str] | None, tarifas: dict[str, int] | None,
        modalidad: str | None = None,
    ) -> None:
        """`None` en posiciones, tarifas o modalidad = usar lo de la liga."""
        if modalidad is not None and modalidad not in MODALIDADES:
            raise ErrorValidacion("Tipo de partido inválido.")
        if posiciones is not None and not posiciones_a_csv(posiciones):
            raise ErrorValidacion("Marca al menos una posición por defecto.")
        if tarifas and any(v < 0 for v in tarifas.values()):
            raise ErrorValidacion("Las tarifas no pueden ser negativas.")
        with self.db.sesion() as s:
            categoria = s.get(Categoria, categoria_id)
            if not categoria:
                raise ErrorValidacion("La categoría ya no existe.")
            efectiva = modalidad or s.get(Liga, categoria.liga_id).modalidad
            if posiciones is not None and (sobran := posiciones_no_permitidas(posiciones, efectiva)):
                raise ErrorValidacion(_texto_no_permitidas(sobran, efectiva))
            categoria.posiciones_defecto = posiciones_a_csv(posiciones) if posiciones is not None else None
            categoria.modalidad = modalidad
            s.execute(delete(TarifaCategoria).where(TarifaCategoria.categoria_id == categoria_id))
            for posicion, monto in (tarifas or {}).items():
                if posicion in POSICIONES:
                    s.add(TarifaCategoria(categoria_id=categoria_id, posicion=posicion, monto_centavos=monto))

    def posiciones_para(self, liga: Liga, categoria: Categoria | None) -> list[str]:
        """Posiciones por defecto de un partido nuevo: las de la categoría si tiene, si no las de la liga."""
        return (categoria.lista_posiciones if categoria else None) or liga.lista_posiciones

    def modalidad_para(self, liga: Liga, categoria: Categoria | None) -> str:
        """Tipo de partido por defecto: el de la categoría si tiene, si no el de la liga."""
        return (categoria.modalidad if categoria else None) or liga.modalidad or FUTBOL_11

    def tarifa_para(self, liga_id: int, categoria_id: int | None, posicion: str) -> int:
        """Centavos que se pagan por `posicion`: tarifa de la categoría si tiene propias, si no la de la liga."""
        if categoria_id is not None:
            propias = self.tarifas_categoria(categoria_id)
            if propias is not None:
                return propias.get(posicion, 0)
        return self.tarifas(liga_id).get(posicion, 0)

    @staticmethod
    def _validar(s, datos: DatosLiga, excluir_id: int | None = None) -> str:
        errores = {}
        nombre = _nombre_limpio(datos.nombre)
        if not nombre:
            errores["nombre"] = "Escribe el nombre"
        else:
            consulta = select(Liga)
            if excluir_id is not None:
                consulta = consulta.where(Liga.id != excluir_id)
            if any(sin_acentos(x.nombre) == sin_acentos(nombre) for x in s.scalars(consulta)):
                errores["nombre"] = "Ya existe una liga o torneo con ese nombre"
        if datos.tipo not in (TIPO_LIGA, TIPO_TORNEO):
            errores["tipo"] = "Tipo inválido"
        if datos.modalidad not in MODALIDADES:
            errores["modalidad"] = "Tipo de partido inválido"
        if not posiciones_a_csv(datos.posiciones):
            errores["posiciones"] = "Marca al menos una posición"
        elif sobran := posiciones_no_permitidas(datos.posiciones, datos.modalidad):
            errores["posiciones"] = _texto_no_permitidas(sobran, datos.modalidad)
        if errores:
            raise ErrorValidacion("Revisa los datos marcados.", errores)
        return nombre
