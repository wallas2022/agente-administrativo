"""Registro de uso del LLM y embeddings (P-13, Bloque 1, RF-21/RNF-15).

`registrar_uso_llm` nunca propaga un error: un fallo al insertar la fila de
uso no debe frenar ni romper un análisis real (RNF-15) -- se registra y se
sigue.

Los "casos de uso" (ver docs/02-analisis/06-analisis-dashboard-
administrador.md): "contable", "ortografia", "redaccion", "embeddings_kb"
(indexación de la Base de Conocimiento, CU-08) y "embeddings_busqueda" (RAG
en tiempo de análisis/redacción).
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy.orm import Session

from comun.modelos import UsoLlm
from rag.cliente_llm import MetricasOllama

_registro = logging.getLogger(__name__)

RESULTADO_OK = "ok"
RESULTADO_TIMEOUT = "timeout"
RESULTADO_ERROR = "error"


def _clasificar_error(error: Exception) -> str:
    return RESULTADO_TIMEOUT if isinstance(error, httpx.TimeoutException) else RESULTADO_ERROR


def registrar_uso_llm(
    sesion: Session,
    *,
    usuario_id: uuid.UUID,
    area_id: uuid.UUID,
    analisis_id: uuid.UUID | None,
    caso_uso: str,
    modelo: str,
    resultado: str,
    metricas: MetricasOllama | None,
) -> None:
    """RNF-15: cualquier excepción acá se registra en el log y se descarta
    -- nunca llega a quien está esperando el resultado real del LLM."""
    try:
        sesion.add(
            UsoLlm(
                usuario_id=usuario_id,
                area_id=area_id,
                analisis_id=analisis_id,
                caso_uso=caso_uso,
                modelo=modelo,
                fecha_hora=datetime.now(UTC),
                tokens_entrada=metricas.tokens_entrada if metricas else None,
                tokens_salida=metricas.tokens_salida if metricas else None,
                duracion_total_ms=metricas.duracion_total_ms if metricas else None,
                duracion_carga_ms=metricas.duracion_carga_ms if metricas else None,
                duracion_lectura_ms=metricas.duracion_lectura_ms if metricas else None,
                duracion_generacion_ms=metricas.duracion_generacion_ms if metricas else None,
                resultado=resultado,
            )
        )
        sesion.flush()
    except Exception:
        _registro.exception("No se pudo registrar uso_llm (no afecta el análisis)")


def envolver_generar_texto(
    *,
    sesion: Session,
    usuario_id: uuid.UUID,
    area_id: uuid.UUID,
    analisis_id: uuid.UUID | None,
    caso_uso: str,
    modelo: str | None = None,
    timeout: float = 300.0,
    formato: str | dict | None = None,
    pensamiento: str | None = None,
    num_ctx: int | None = None,
    num_predict: int | None = None,
):
    """Construye un `Callable[[str], str]` (el mismo contrato `FuncionLLM`
    que ya usa todo el proyecto) que llama a `generar_texto_con_metricas`
    con los parámetros dados y registra el uso -- éxito, timeout o error,
    sin cambiar el comportamiento de quien lo consume."""
    from rag.cliente_llm import generar_texto_con_metricas

    def _funcion(prompt: str) -> str:
        try:
            resultado = generar_texto_con_metricas(
                prompt,
                modelo=modelo,
                timeout=timeout,
                formato=formato,
                pensamiento=pensamiento,
                num_ctx=num_ctx,
                num_predict=num_predict,
            )
        except Exception as error:
            registrar_uso_llm(
                sesion,
                usuario_id=usuario_id,
                area_id=area_id,
                analisis_id=analisis_id,
                caso_uso=caso_uso,
                modelo=modelo or "",
                resultado=_clasificar_error(error),
                metricas=None,
            )
            raise
        registrar_uso_llm(
            sesion,
            usuario_id=usuario_id,
            area_id=area_id,
            analisis_id=analisis_id,
            caso_uso=caso_uso,
            modelo=resultado.metricas.modelo,
            resultado=RESULTADO_OK,
            metricas=resultado.metricas,
        )
        return resultado.texto

    return _funcion


def envolver_obtener_embedding(
    *,
    sesion: Session,
    usuario_id: uuid.UUID,
    area_id: uuid.UUID,
    analisis_id: uuid.UUID | None,
    caso_uso: str,
    modelo: str | None = None,
    timeout: float = 30.0,
):
    """Igual que `envolver_generar_texto`, para `Callable[[str], list[float]]`
    (`FuncionEmbedding`)."""
    from rag.cliente_embeddings import obtener_embedding_con_metricas

    def _funcion(texto: str) -> list[float]:
        try:
            resultado = obtener_embedding_con_metricas(texto, modelo=modelo, timeout=timeout)
        except Exception as error:
            registrar_uso_llm(
                sesion,
                usuario_id=usuario_id,
                area_id=area_id,
                analisis_id=analisis_id,
                caso_uso=caso_uso,
                modelo=modelo or "",
                resultado=_clasificar_error(error),
                metricas=None,
            )
            raise
        registrar_uso_llm(
            sesion,
            usuario_id=usuario_id,
            area_id=area_id,
            analisis_id=analisis_id,
            caso_uso=caso_uso,
            modelo=resultado.metricas.modelo,
            resultado=RESULTADO_OK,
            metricas=resultado.metricas,
        )
        return resultado.vector

    return _funcion


def envolver_funcion_llm_inyectada(
    funcion_llm: Callable[[str], str],
    *,
    sesion: Session,
    usuario_id: uuid.UUID,
    area_id: uuid.UUID,
    analisis_id: uuid.UUID | None,
    caso_uso: str,
) -> Callable[[str], str]:
    """Para los endpoints de `api/main.py` donde `funcion_llm` llega por
    `Depends(obtener_funcion_llm)` -- inyección que las pruebas sobreescriben
    con un fake (ver tests/unit/test_api_mejorar_redaccion_stream.py), así
    que acá no se puede asumir que `funcion_llm` es `generar_texto` real
    (`envolver_generar_texto` sí lo asume, correcto en orquestador/tareas.py,
    que no tiene este problema). Las métricas se recuperan del `ContextVar`
    que la propia `generar_texto` llena -- si `funcion_llm` es un fake de
    prueba que nunca pasa por ahí, quedan en `None` y aun así se registra la
    fila (con `modelo="desconocido"`), sin romper nada."""
    from rag.cliente_llm import ULTIMAS_METRICAS_LLM

    def _funcion(prompt: str) -> str:
        ULTIMAS_METRICAS_LLM.set(None)
        try:
            texto = funcion_llm(prompt)
        except Exception as error:
            registrar_uso_llm(
                sesion,
                usuario_id=usuario_id,
                area_id=area_id,
                analisis_id=analisis_id,
                caso_uso=caso_uso,
                modelo="desconocido",
                resultado=_clasificar_error(error),
                metricas=None,
            )
            raise
        metricas = ULTIMAS_METRICAS_LLM.get()
        registrar_uso_llm(
            sesion,
            usuario_id=usuario_id,
            area_id=area_id,
            analisis_id=analisis_id,
            caso_uso=caso_uso,
            modelo=metricas.modelo if metricas else "desconocido",
            resultado=RESULTADO_OK,
            metricas=metricas,
        )
        return texto

    return _funcion


def envolver_funcion_embedding_inyectada(
    funcion_embedding: Callable[[str], list[float]],
    *,
    sesion: Session,
    usuario_id: uuid.UUID,
    area_id: uuid.UUID,
    analisis_id: uuid.UUID | None,
    caso_uso: str,
) -> Callable[[str], list[float]]:
    """Igual que `envolver_funcion_llm_inyectada`, para `funcion_embedding`
    inyectada vía `Depends(obtener_funcion_embedding)`."""
    from rag.cliente_embeddings import ULTIMAS_METRICAS_EMBEDDING

    def _funcion(texto: str) -> list[float]:
        ULTIMAS_METRICAS_EMBEDDING.set(None)
        try:
            vector = funcion_embedding(texto)
        except Exception as error:
            registrar_uso_llm(
                sesion,
                usuario_id=usuario_id,
                area_id=area_id,
                analisis_id=analisis_id,
                caso_uso=caso_uso,
                modelo="desconocido",
                resultado=_clasificar_error(error),
                metricas=None,
            )
            raise
        metricas = ULTIMAS_METRICAS_EMBEDDING.get()
        registrar_uso_llm(
            sesion,
            usuario_id=usuario_id,
            area_id=area_id,
            analisis_id=analisis_id,
            caso_uso=caso_uso,
            modelo=metricas.modelo if metricas else "desconocido",
            resultado=RESULTADO_OK,
            metricas=metricas,
        )
        return vector

    return _funcion
