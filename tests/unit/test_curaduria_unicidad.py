# ruff: noqa: E501 -- SQL de esquemas mínimos previos a la migración
"""Bloque 3.5: unicidad de fuentes -- (fuente_id, version) único en dominio, BD, listado de
duplicados previos a la migración, importador de plantilla y la propia migración."""

import importlib.util
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from comun.modelos import Area, Base, FuenteConocimiento, Rol, Usuario
from curaduria.duplicados import listar_duplicados
from curaduria.fuentes import clasificar_tipo_fuente, evaluar_alta_fuente
from curaduria.plantilla import (
    HOJA_FUENTES,
    cargar_plantilla,
    leer_plantilla,
    validar_fuentes_contra_bd,
)

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PLANTILLA_REAL = RAIZ / "kb" / "plantillas" / "Plantilla_Base_Conocimiento_SFC.xlsx"
RUTA_MIGRACION = (
    RAIZ / "src" / "api" / "migraciones" / "versions" / "e7b2c9a14f60_unicidad_fuente_version.py"
)


class _Entorno:
    def __init__(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.sesion = Session(engine)
        self.area = Area(nombre="Contabilidad")
        self.otra_area = Area(nombre="Tesorería")
        rol = Rol(nombre="curador")
        self.sesion.add_all([self.area, self.otra_area, rol])
        self.sesion.flush()
        self.usuario = Usuario(
            nombre="Carla",
            email="carla@ejemplo.gt",
            area_id=self.area.id,
            rol_id=rol.id,
            origen_autenticacion="local",
            activo=True,
        )
        self.sesion.add(self.usuario)
        self.sesion.commit()

    def fuente(
        self,
        fuente_id="CONTIT-001",
        version="1",
        titulo="Redes y Telecomunicaciones",
        tipo="regla_interna",
        area=None,
        estado="borrador",
    ) -> FuenteConocimiento:
        fila = FuenteConocimiento(
            fuente_id=fuente_id,
            titulo=titulo,
            tipo=tipo,
            prioridad={"regla_interna": 1, "normativa": 2, "referencia": 3}[tipo],
            version=version,
            vigente_desde=date(2026, 1, 1),
            estado=estado,
            area_id=(area or self.area).id,
            dueno="Jefatura",
            archivo=f"{fuente_id}.pdf",
            cargado_por=self.usuario.id,
            fecha_carga=datetime.now(UTC),
        )
        self.sesion.add(fila)
        self.sesion.commit()
        return fila

    def evaluar(self, **kw):
        datos = {
            "fuente_id": "CONTIT-001",
            "version": "1",
            "titulo": "Redes y Telecomunicaciones",
            "tipo": "política (Word)",
            "area_id": self.area.id,
        }
        datos.update(kw)
        return evaluar_alta_fuente(self.sesion, **datos)


@pytest.fixture()
def e() -> _Entorno:
    return _Entorno()


# --- evaluación de un alta ---------------------------------------------------


def test_id_nuevo_se_permite_sin_advertencias(e) -> None:
    r = e.evaluar()

    assert r.permitido and r.codigo_http == 200 and r.advertencias == []
    assert r.es_nueva_version is False


def test_mismo_id_y_misma_version_da_409_con_el_mensaje_pedido(e) -> None:
    e.fuente()

    r = e.evaluar(titulo="Patrón de diseños")

    assert not r.permitido and r.codigo_http == 409
    assert r.mensaje == "Ya existe CONTIT-001 versión 1; use otro ID o suba una nueva versión"


def test_mismo_id_con_otra_version_es_una_nueva_version(e) -> None:
    e.fuente()

    r = e.evaluar(version="2")

    assert r.permitido and r.es_nueva_version and r.advertencias == []


def test_nueva_version_con_titulo_distinto_advierte(e) -> None:
    e.fuente()

    r = e.evaluar(version="2", titulo="Patrón de diseños")

    assert r.permitido and r.es_nueva_version
    assert len(r.advertencias) == 1
    assert "Redes y Telecomunicaciones" in r.advertencias[0]


def test_nueva_version_con_tipo_distinto_se_rechaza(e) -> None:
    e.fuente(tipo="regla_interna")

    r = e.evaluar(version="2", tipo="normativa (ley)")

    assert not r.permitido and r.codigo_http == 409
    assert "tipo" in r.mensaje and "CONTIT-001" in r.mensaje


def test_id_de_otra_area_da_403(e) -> None:
    e.fuente(area=e.otra_area)

    for version in ("1", "2"):
        r = e.evaluar(version=version)
        assert not r.permitido and r.codigo_http == 403
        assert "otra área" in r.mensaje


def test_espacios_alrededor_del_id_y_la_version_no_evitan_el_duplicado(e) -> None:
    e.fuente()

    r = e.evaluar(fuente_id="  CONTIT-001 ", version=" 1 ")

    assert not r.permitido and r.codigo_http == 409


# --- restricción en base de datos ---------------------------------------------


def test_la_base_rechaza_dos_filas_con_el_mismo_id_y_version(e) -> None:
    e.fuente(titulo="Redes y Telecomunicaciones")

    with pytest.raises(IntegrityError):
        e.fuente(titulo="Patrón de diseños")
    e.sesion.rollback()


def test_la_base_acepta_el_mismo_id_con_otra_version(e) -> None:
    e.fuente(version="1")
    e.fuente(version="2")

    assert e.sesion.query(FuenteConocimiento).count() == 2


# --- listado de duplicados existentes (sin borrar nada) ----------------------------


def test_listar_duplicados_con_filas_repetidas_de_una_base_previa() -> None:
    engine = create_engine("sqlite:///:memory:")
    # Esquema mínimo equivalente al previo a la migración: sin UNIQUE (fuente_id, version).
    with engine.begin() as con:
        con.execute(text("CREATE TABLE area (id CHAR(32) PRIMARY KEY, nombre VARCHAR(100))"))
        con.execute(
            text(
                "CREATE TABLE fuente_conocimiento (id CHAR(32) PRIMARY KEY, fuente_id VARCHAR(50), "
                "titulo VARCHAR(300), tipo VARCHAR(20), version VARCHAR(50), estado VARCHAR(20), "
                "area_id CHAR(32), fecha_carga DATETIME)"
            )
        )
        con.execute(
            text(
                "CREATE TABLE fragmento (id CHAR(32) PRIMARY KEY, fuente_id CHAR(32), contenido TEXT)"
            )
        )
        con.execute(text("INSERT INTO area VALUES ('a1', 'Contabilidad')"))
        for i, titulo in (("f1", "Redes y Telecomunicaciones"), ("f2", "Patrón de diseños")):
            con.execute(
                text(
                    "INSERT INTO fuente_conocimiento VALUES (:i, 'CONTIT-001', :t, 'regla_interna', "
                    "'1', 'borrador', 'a1', '2026-10-14 10:00:00')"
                ),
                {"i": i, "t": titulo},
            )
        con.execute(
            text(
                "INSERT INTO fuente_conocimiento VALUES ('f3', 'POL-001', 'Política', "
                "'regla_interna', '1', 'vigente', 'a1', '2026-10-14 11:00:00')"
            )
        )
        con.execute(text("INSERT INTO fragmento VALUES ('g1', 'f2', 'texto')"))

    with engine.connect() as con:
        grupos = listar_duplicados(con)
        antes = con.execute(text("SELECT count(*) FROM fuente_conocimiento")).scalar()

    assert len(grupos) == 1
    grupo = grupos[0]
    assert (grupo.fuente_id, grupo.version) == ("CONTIT-001", "1")
    assert {f.titulo for f in grupo.filas} == {"Redes y Telecomunicaciones", "Patrón de diseños"}
    assert {f.id for f in grupo.filas} == {"f1", "f2"}
    assert next(f for f in grupo.filas if f.id == "f2").fragmentos == 1
    with engine.connect() as con:
        assert con.execute(text("SELECT count(*) FROM fuente_conocimiento")).scalar() == antes == 3


def test_listar_duplicados_sin_duplicados_devuelve_lista_vacia(e) -> None:
    e.fuente(version="1")
    e.fuente(version="2")

    with e.sesion.connection() as con:
        assert listar_duplicados(con) == []


# --- importador de plantilla ---------------------------------------------------------


def test_el_importador_rechaza_ids_ya_existentes_con_hoja_fila_y_columna(e) -> None:
    resultado = leer_plantilla(RUTA_PLANTILLA_REAL.read_bytes())
    assert resultado.es_valido
    cargar_plantilla(
        e.sesion,
        resultado,
        area_id_por_defecto=e.area.id,
        cargado_por=e.usuario.id,
        ahora=datetime.now(UTC),
    )
    e.sesion.commit()

    errores = validar_fuentes_contra_bd(e.sesion, resultado, e.area.id)

    assert len(errores) == len(resultado.fuentes)
    primero = errores[0]
    assert primero.hoja == HOJA_FUENTES and primero.columna == "fuente_id"
    assert primero.fila is not None and primero.fila >= 2
    assert (
        "Ya existe" in primero.mensaje and "use otro ID o suba una nueva versión" in primero.mensaje
    )


def test_el_importador_acepta_ids_nuevos_y_nuevas_versiones(e) -> None:
    resultado = leer_plantilla(RUTA_PLANTILLA_REAL.read_bytes())
    assert validar_fuentes_contra_bd(e.sesion, resultado, e.area.id) == []

    for fuente in resultado.fuentes:
        e.fuente(
            fuente_id=fuente.fuente_id,
            version="0-anterior",
            titulo=fuente.titulo,
            tipo=clasificar_tipo_fuente(fuente.tipo_libre),
        )
    assert validar_fuentes_contra_bd(e.sesion, resultado, e.area.id) == []


def test_el_importador_rechaza_ids_de_otra_area(e) -> None:
    resultado = leer_plantilla(RUTA_PLANTILLA_REAL.read_bytes())
    e.fuente(fuente_id=resultado.fuentes[0].fuente_id, version="9", area=e.otra_area)

    errores = validar_fuentes_contra_bd(e.sesion, resultado, e.area.id)

    assert len(errores) == 1 and "otra área" in errores[0].mensaje


# --- migración ------------------------------------------------------------------------


def _cargar_migracion():
    spec = importlib.util.spec_from_file_location("migracion_unicidad", RUTA_MIGRACION)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_la_migracion_encadena_con_la_anterior_y_define_la_restriccion() -> None:
    m = _cargar_migracion()

    assert m.down_revision == "d41a9b7c5e20"
    assert m.NOMBRE_RESTRICCION == "ux_fuente_conocimiento_id_version"


def test_la_migracion_se_detiene_y_lista_los_duplicados_sin_borrar_nada() -> None:
    m = _cargar_migracion()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as con:
        con.execute(text("CREATE TABLE area (id CHAR(32) PRIMARY KEY, nombre VARCHAR(100))"))
        con.execute(
            text(
                "CREATE TABLE fuente_conocimiento (id CHAR(32) PRIMARY KEY, fuente_id VARCHAR(50), "
                "titulo VARCHAR(300), tipo VARCHAR(20), version VARCHAR(50), estado VARCHAR(20), "
                "area_id CHAR(32), fecha_carga DATETIME)"
            )
        )
        con.execute(text("CREATE TABLE fragmento (id CHAR(32) PRIMARY KEY, fuente_id CHAR(32))"))
        con.execute(text("INSERT INTO area VALUES ('a1', 'Contabilidad')"))
        for i in ("f1", "f2"):
            con.execute(
                text(
                    "INSERT INTO fuente_conocimiento VALUES (:i, 'CONTIT-001', 'T', 'regla_interna', "
                    "'1', 'borrador', 'a1', '2026-10-14 10:00:00')"
                ),
                {"i": i},
            )

    with engine.connect() as con:
        with pytest.raises(RuntimeError) as error:
            m.verificar_sin_duplicados(con)
        total = con.execute(text("SELECT count(*) FROM fuente_conocimiento")).scalar()

    mensaje = str(error.value)
    assert "CONTIT-001" in mensaje and "f1" in mensaje and "f2" in mensaje
    assert "no se borró nada" in mensaje.lower()
    assert total == 2


def test_la_migracion_no_falla_sin_duplicados() -> None:
    m = _cargar_migracion()
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as con:
        con.execute(text("CREATE TABLE area (id CHAR(32) PRIMARY KEY, nombre VARCHAR(100))"))
        con.execute(
            text(
                "CREATE TABLE fuente_conocimiento (id CHAR(32) PRIMARY KEY, fuente_id VARCHAR(50), "
                "titulo VARCHAR(300), tipo VARCHAR(20), version VARCHAR(50), estado VARCHAR(20), "
                "area_id CHAR(32), fecha_carga DATETIME)"
            )
        )
        con.execute(text("CREATE TABLE fragmento (id CHAR(32) PRIMARY KEY, fuente_id CHAR(32))"))
        con.execute(
            text(
                "INSERT INTO fuente_conocimiento VALUES ('f1', 'A', 'T', 'regla_interna', '1', "
                "'borrador', NULL, '2026-10-14 10:00:00')"
            )
        )

    with engine.connect() as con:
        m.verificar_sin_duplicados(con)
