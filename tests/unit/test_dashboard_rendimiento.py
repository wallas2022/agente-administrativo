"""P-13 (Bloque 5, cierre): pruebas de rendimiento del dashboard --
RNF-15 (registrar_uso_llm no agrega más de 20 ms por llamada) y RNF-16 (el
dashboard responde en <= 2 s con 100,000 registros de uso).
"""

import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from comun.dashboard import calcular_consumo, calcular_consumo_por_usuario
from comun.modelos import Area, Base, Rol, UsoLlm, Usuario
from comun.uso_llm import registrar_uso_llm
from rag.cliente_llm import MetricasOllama

NUMERO_FILAS_SINTETICAS = 100_000
LIMITE_DASHBOARD_SEGUNDOS = 2.0
LIMITE_REGISTRO_MS = 20.0


@pytest.fixture()
def sesion() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


@pytest.fixture()
def usuario_y_area(sesion: Session) -> tuple[Usuario, Area]:
    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()
    usuario = Usuario(nombre="Ana", email="ana@local", area_id=area.id, rol_id=rol.id)
    sesion.add(usuario)
    sesion.commit()
    return usuario, area


def _sembrar_filas_sinteticas(
    sesion: Session, *, usuario_id: uuid.UUID, area_id: uuid.UUID
) -> None:
    """Inserción masiva vía Core (no ORM uno por uno) -- es preparación del
    escenario, no lo que miden las pruebas de este archivo."""
    ahora = datetime.now(UTC)
    casos_uso = ("contable", "ortografia", "redaccion", "embeddings_kb", "embeddings_busqueda")
    modelos = ("gpt-oss:20b", "qwen3:30b", "bge-m3")
    filas = [
        {
            "id": uuid.uuid4(),
            "usuario_id": usuario_id,
            "area_id": area_id,
            "analisis_id": None,
            "caso_uso": casos_uso[i % len(casos_uso)],
            "modelo": modelos[i % len(modelos)],
            "fecha_hora": ahora - timedelta(minutes=i),
            "tokens_entrada": 100 + (i % 50),
            "tokens_salida": 50 + (i % 20),
            "duracion_total_ms": 2000,
            "duracion_carga_ms": 100,
            "duracion_lectura_ms": 200,
            "duracion_generacion_ms": 1500,
            "resultado": "timeout" if i % 97 == 0 else "ok",
        }
        for i in range(NUMERO_FILAS_SINTETICAS)
    ]
    sesion.execute(insert(UsoLlm), filas)
    sesion.commit()


def test_rnf16_dashboard_con_100000_registros_responde_en_menos_de_2_segundos(
    sesion, usuario_y_area
) -> None:
    usuario, area = usuario_y_area
    _sembrar_filas_sinteticas(sesion, usuario_id=usuario.id, area_id=area.id)

    inicio = time.perf_counter()
    resultado_consumo = calcular_consumo(sesion)
    duracion_consumo = time.perf_counter() - inicio
    assert resultado_consumo["tarjetas"]["llamadas"] == NUMERO_FILAS_SINTETICAS
    assert duracion_consumo < LIMITE_DASHBOARD_SEGUNDOS, (
        f"calcular_consumo tardó {duracion_consumo:.2f}s con {NUMERO_FILAS_SINTETICAS:,} filas"
    )

    inicio = time.perf_counter()
    filas_por_usuario = calcular_consumo_por_usuario(sesion)
    duracion_usuarios = time.perf_counter() - inicio
    assert len(filas_por_usuario) == 1
    assert filas_por_usuario[0]["numero_analisis"] == 0  # todas con analisis_id=None
    assert duracion_usuarios < LIMITE_DASHBOARD_SEGUNDOS, (
        f"calcular_consumo_por_usuario tardó {duracion_usuarios:.2f}s con "
        f"{NUMERO_FILAS_SINTETICAS:,} filas"
    )


def test_rnf15_registrar_uso_llm_agrega_menos_de_20ms_por_llamada(sesion, usuario_y_area) -> None:
    usuario, area = usuario_y_area
    metricas = MetricasOllama(
        modelo="gpt-oss:20b",
        tokens_entrada=100,
        tokens_salida=50,
        duracion_total_ms=2000,
        duracion_carga_ms=100,
        duracion_lectura_ms=200,
        duracion_generacion_ms=1500,
    )

    numero_llamadas = 200
    inicio = time.perf_counter()
    for _ in range(numero_llamadas):
        registrar_uso_llm(
            sesion,
            usuario_id=usuario.id,
            area_id=area.id,
            analisis_id=None,
            caso_uso="contable",
            modelo="gpt-oss:20b",
            resultado="ok",
            metricas=metricas,
        )
    duracion_total = time.perf_counter() - inicio

    duracion_promedio_ms = (duracion_total / numero_llamadas) * 1000
    assert duracion_promedio_ms < LIMITE_REGISTRO_MS, (
        f"registrar_uso_llm tardó {duracion_promedio_ms:.2f} ms en promedio "
        f"(límite {LIMITE_REGISTRO_MS:.0f} ms, RNF-15)"
    )
