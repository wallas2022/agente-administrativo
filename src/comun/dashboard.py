"""Lógica del Dashboard del Administrador (P-13, Bloque 3, RF-22) -- consumo
de LLM/embeddings (HU-26..28), recursos de infraestructura (HU-29) y
configuración vigente (HU-30). Separado de `api/main.py` por su tamaño,
igual que `comun/permisos.py`/`comun/uso_llm.py`; sin lógica de FastAPI acá
(`requiere_permiso("dashboard:ver")` vive en `api/main.py`).
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import TypedDict

import httpx
from sqlalchemy import case, func
from sqlalchemy.orm import Query, Session

from comun.modelos import Analisis, Area, UsoLlm, Usuario


class _FiltrosConsumo(TypedDict):
    desde: date | None
    hasta: date | None
    area_id: uuid.UUID | None
    caso_uso: str | None
    modelo: str | None

# Umbrales de alerta (P-13 §5) -- no configurables por ahora, documentados
# acá para que quien lea el código no tenga que ir al prompt original.
UMBRAL_DISCO_ALERTA_PCT = 70.0
UMBRAL_MEMORIA_OLLAMA_ALERTA_PCT = 90.0
UMBRAL_TIMEOUTS_ALERTA_PCT = 10.0
VENTANA_TIMEOUTS_HORAS = 24

# RNF-17: lista BLANCA, no lista negra -- una variable que no está acá
# explícitamente nunca aparece en /admin/dashboard/configuracion, sin
# importar cómo se llame. Tomada de .env.local.example (RF-02, RF-11,
# OCR, ortografía, RAG, retención) -- ninguna contiene PASSWORD/SECRET/
# KEY/TOKEN (ver test_dashboard.py::test_lista_blanca_no_contiene_secretos).
VARIABLES_CONFIGURACION_VISIBLES: tuple[str, ...] = (
    "APP_ENV",
    "LLM_PROVIDER",
    "LLM_MODEL_PRINCIPAL",
    "LLM_MODEL_EMBEDDINGS",
    "OLLAMA_KEEP_ALIVE",
    "SEGREGACION_APROBACION",
    "OCR_DPI_MINIMO",
    "OCR_CONF_DUDOSA",
    "OCR_CONF_REVISAR",
    "OCR_PAGINA_ILEGIBLE",
    "LANGUAGETOOL_LOCALE",
    "QDRANT_COLECCION",
    "DOCUMENTO_TAMANO_MAX_MB",
    "DOCUMENTO_RETENCION_DIAS",
)


# --- Consumo (HU-26, HU-28) -------------------------------------------------
#
# RNF-16 (dashboard <= 2s con 100,000 registros de uso): la primera versión
# de este módulo traía todas las filas a Python (`.all()`) y agregaba ahí --
# con 100,000 filas tardaba ~2.6s, por encima del umbral (medido con la
# prueba de rendimiento, ver tests/unit/test_dashboard_rendimiento.py). Todo
# lo de abajo agrega en SQL (GROUP BY/SUM/COUNT); el único bucle en Python
# que queda es sobre los pares (grupo, analisis_id) DISTINCT -- acotado por
# el número de análisis reales, no por el número de filas de uso_llm.

_TOKENS_POR_FILA = func.coalesce(UsoLlm.tokens_entrada, 0) + func.coalesce(UsoLlm.tokens_salida, 0)
_DURACION_POR_FILA = func.coalesce(UsoLlm.duracion_total_ms, 0)
_ES_TIMEOUT = case((UsoLlm.resultado == "timeout", 1), else_=0)


def _filtrar_consumo(
    consulta: Query,
    *,
    desde: date | None,
    hasta: date | None,
    area_id: uuid.UUID | None,
    caso_uso: str | None,
    modelo: str | None,
) -> Query:
    if desde is not None:
        consulta = consulta.filter(UsoLlm.fecha_hora >= desde)
    if hasta is not None:
        consulta = consulta.filter(UsoLlm.fecha_hora < hasta + timedelta(days=1))
    if area_id is not None:
        consulta = consulta.filter(UsoLlm.area_id == area_id)
    if caso_uso is not None:
        consulta = consulta.filter(UsoLlm.caso_uso == caso_uso)
    if modelo is not None:
        consulta = consulta.filter(UsoLlm.modelo == modelo)
    return consulta


def _fecha_iso(valor: object) -> str:
    """`func.date(...)` devuelve un `date` en Postgres y un `str` en SQLite
    (usado en pruebas) -- se normaliza acá en vez de asumir un tipo."""
    isoformat = getattr(valor, "isoformat", None)
    return isoformat() if callable(isoformat) else str(valor)


def _duracion_media_analisis_por_grupo(
    sesion: Session,
    columna_grupo,
    *,
    desde: date | None,
    hasta: date | None,
    area_id: uuid.UUID | None,
    caso_uso: str | None,
    modelo: str | None,
) -> dict[str, float | None]:
    """HU-28: "duración media del análisis" por caso de uso/modelo -- de los
    `Analisis` ya terminados (`fecha_fin` no nulo) referenciados por las
    filas de uso de ese grupo (`embeddings_kb` no tiene `analisis_id`,
    queda en `None` -- no aplica, no es "no informado"). Solo trae pares
    (grupo, analisis_id) DISTINCT, acotado por el número de análisis, no por
    el número de filas de uso_llm."""
    pares = _filtrar_consumo(
        sesion.query(columna_grupo.label("grupo"), UsoLlm.analisis_id).filter(
            UsoLlm.analisis_id.isnot(None)
        ),
        desde=desde,
        hasta=hasta,
        area_id=area_id,
        caso_uso=caso_uso,
        modelo=modelo,
    ).distinct()
    sub = pares.subquery()

    duraciones_por_grupo: dict[str, list[float]] = {}
    filas = (
        sesion.query(sub.c.grupo, Analisis.fecha_inicio, Analisis.fecha_fin)
        .join(Analisis, Analisis.id == sub.c.analisis_id)
        .filter(Analisis.fecha_fin.isnot(None))
        .all()
    )
    for grupo, inicio, fin in filas:
        if fin is None:
            continue
        duraciones_por_grupo.setdefault(grupo, []).append((fin - inicio).total_seconds() * 1000)

    return {
        grupo: sum(duraciones) / len(duraciones)
        for grupo, duraciones in duraciones_por_grupo.items()
    }


def _rankear(
    sesion: Session,
    columna_grupo,
    nombre_campo: str,
    *,
    desde: date | None,
    hasta: date | None,
    area_id: uuid.UUID | None,
    caso_uso: str | None,
    modelo: str | None,
) -> list[dict]:
    kwargs: _FiltrosConsumo = {
        "desde": desde,
        "hasta": hasta,
        "area_id": area_id,
        "caso_uso": caso_uso,
        "modelo": modelo,
    }
    consulta = _filtrar_consumo(
        sesion.query(
            columna_grupo,
            func.sum(_TOKENS_POR_FILA),
            func.sum(_DURACION_POR_FILA),
            func.count(UsoLlm.id),
        ),
        **kwargs,
    ).group_by(columna_grupo)

    duracion_media = _duracion_media_analisis_por_grupo(sesion, columna_grupo, **kwargs)

    filas = [
        {
            nombre_campo: clave,
            "tokens_totales": tokens or 0,
            "duracion_llm_total_ms": duracion or 0,
            "llamadas": llamadas,
            "duracion_media_analisis_ms": duracion_media.get(clave),
        }
        for clave, tokens, duracion, llamadas in consulta.all()
    ]
    return sorted(filas, key=lambda f: -f["tokens_totales"])


def calcular_consumo(
    sesion: Session,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    area_id: uuid.UUID | None = None,
    caso_uso: str | None = None,
    modelo: str | None = None,
) -> dict:
    kwargs: _FiltrosConsumo = {
        "desde": desde,
        "hasta": hasta,
        "area_id": area_id,
        "caso_uso": caso_uso,
        "modelo": modelo,
    }

    (
        tokens_entrada,
        tokens_salida,
        llamadas,
        timeouts,
        duracion_generacion_total_ms,
    ) = _filtrar_consumo(
        sesion.query(
            func.coalesce(func.sum(UsoLlm.tokens_entrada), 0),
            func.coalesce(func.sum(UsoLlm.tokens_salida), 0),
            func.count(UsoLlm.id),
            func.coalesce(func.sum(_ES_TIMEOUT), 0),
            func.coalesce(func.sum(UsoLlm.duracion_generacion_ms), 0),
        ),
        **kwargs,
    ).one()
    duracion_generacion_total_s = duracion_generacion_total_ms / 1000

    fecha_dia = func.date(UsoLlm.fecha_hora)
    serie = (
        _filtrar_consumo(
            sesion.query(
                fecha_dia.label("fecha"),
                func.coalesce(func.sum(UsoLlm.tokens_entrada), 0),
                func.coalesce(func.sum(UsoLlm.tokens_salida), 0),
                func.count(UsoLlm.id),
            ),
            **kwargs,
        )
        .group_by(fecha_dia)
        .order_by(fecha_dia)
        .all()
    )

    return {
        "tarjetas": {
            "tokens_entrada": tokens_entrada,
            "tokens_salida": tokens_salida,
            "tokens_totales": tokens_entrada + tokens_salida,
            "llamadas": llamadas,
            "tokens_por_segundo_promedio": (
                round(tokens_salida / duracion_generacion_total_s, 2)
                if duracion_generacion_total_s > 0
                else None
            ),
            "pct_timeouts": round(timeouts / llamadas * 100, 2) if llamadas else 0.0,
        },
        "serie_diaria": [
            {
                "fecha": _fecha_iso(fecha),
                "tokens_entrada": te,
                "tokens_salida": ts,
                "llamadas": llamadas_del_dia,
            }
            for fecha, te, ts, llamadas_del_dia in serie
        ],
        "ranking_caso_uso": _rankear(sesion, UsoLlm.caso_uso, "caso_uso", **kwargs),
        "ranking_modelo": _rankear(sesion, UsoLlm.modelo, "modelo", **kwargs),
    }


def calcular_consumo_por_usuario(
    sesion: Session, *, desde: date | None = None, hasta: date | None = None
) -> list[dict]:
    """HU-27: tabla por usuario -- área, número de análisis distintos,
    tokens, tiempo de LLM y timeouts. `COUNT(DISTINCT ...)` ignora los NULL
    por definición del SQL estándar, igual que el `set()` que reemplaza."""
    consulta = (
        sesion.query(
            Usuario.id,
            Usuario.nombre,
            Usuario.email,
            Area.nombre,
            func.count(func.distinct(UsoLlm.analisis_id)),
            func.coalesce(func.sum(UsoLlm.tokens_entrada), 0),
            func.coalesce(func.sum(UsoLlm.tokens_salida), 0),
            func.coalesce(func.sum(UsoLlm.duracion_total_ms), 0),
            func.coalesce(func.sum(_ES_TIMEOUT), 0),
        )
        .join(Usuario, UsoLlm.usuario_id == Usuario.id)
        .join(Area, Usuario.area_id == Area.id)
    )
    if desde is not None:
        consulta = consulta.filter(UsoLlm.fecha_hora >= desde)
    if hasta is not None:
        consulta = consulta.filter(UsoLlm.fecha_hora < hasta + timedelta(days=1))
    consulta = consulta.group_by(Usuario.id, Usuario.nombre, Usuario.email, Area.nombre)

    filas = [
        {
            "usuario_id": str(usuario_id),
            "usuario_nombre": nombre,
            "usuario_email": email,
            "area_nombre": area_nombre,
            "numero_analisis": numero_analisis,
            "tokens_entrada": tokens_entrada,
            "tokens_salida": tokens_salida,
            "duracion_llm_total_ms": duracion_total,
            "timeouts": timeouts,
        }
        for (
            usuario_id,
            nombre,
            email,
            area_nombre,
            numero_analisis,
            tokens_entrada,
            tokens_salida,
            duracion_total,
            timeouts,
        ) in consulta.all()
    ]
    return sorted(filas, key=lambda f: -(f["tokens_entrada"] + f["tokens_salida"]))


# --- Recursos (HU-29) --------------------------------------------------------


def _consultar_prometheus(
    prometheus_url: str, query: str, *, timeout: float = 5.0
) -> list[dict] | None:
    """`None` si Prometheus no está disponible (apagado por defecto en
    local, perfil "observabilidad" -- ver ADR-009) -- nunca falla la
    pantalla completa de Recursos por esto, solo esa sección."""
    try:
        respuesta = httpx.get(
            f"{prometheus_url}/api/v1/query", params={"query": query}, timeout=timeout
        )
        respuesta.raise_for_status()
        cuerpo = respuesta.json()
        if cuerpo.get("status") != "success":
            return None
        return cuerpo["data"]["result"]
    except Exception:
        return None


def _valor_unico(resultado: list[dict] | None) -> float | None:
    if not resultado:
        return None
    try:
        return float(resultado[0]["value"][1])
    except (KeyError, IndexError, ValueError, TypeError):
        return None


def _consultar_host(prometheus_url: str) -> dict | None:
    memoria_total = _valor_unico(
        _consultar_prometheus(prometheus_url, "node_memory_MemTotal_bytes")
    )
    memoria_disponible = _valor_unico(
        _consultar_prometheus(prometheus_url, "node_memory_MemAvailable_bytes")
    )
    if memoria_total is None or memoria_disponible is None:
        return None

    mountpoint = os.environ.get("DASHBOARD_DISCO_MOUNTPOINT", "/")
    disco_total = _valor_unico(
        _consultar_prometheus(
            prometheus_url, f'node_filesystem_size_bytes{{mountpoint="{mountpoint}"}}'
        )
    )
    disco_disponible = _valor_unico(
        _consultar_prometheus(
            prometheus_url, f'node_filesystem_avail_bytes{{mountpoint="{mountpoint}"}}'
        )
    )
    cpu_ocupado_pct = _valor_unico(
        _consultar_prometheus(
            prometheus_url,
            '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        )
    )
    vcpus = len(_consultar_prometheus(prometheus_url, 'node_cpu_seconds_total{mode="idle"}') or [])
    carga_1m = _valor_unico(_consultar_prometheus(prometheus_url, "node_load1"))

    return {
        "cpu_ocupado_pct": round(cpu_ocupado_pct, 2) if cpu_ocupado_pct is not None else None,
        "vcpus": vcpus or None,
        "memoria_usada_bytes": int(memoria_total - memoria_disponible),
        "memoria_total_bytes": int(memoria_total),
        "disco_usado_bytes": (
            int(disco_total - disco_disponible)
            if disco_total is not None and disco_disponible is not None
            else None
        ),
        "disco_total_bytes": int(disco_total) if disco_total is not None else None,
        "carga_1m": carga_1m,
    }


def _consultar_contenedores(prometheus_url: str) -> list[dict] | None:
    uso_cpu = _consultar_prometheus(
        prometheus_url,
        'sum by (name) (rate(container_cpu_usage_seconds_total{name!=""}[1m])) * 100',
    )
    uso_memoria = _consultar_prometheus(prometheus_url, 'container_memory_usage_bytes{name!=""}')
    limite_memoria = _consultar_prometheus(
        prometheus_url, 'container_spec_memory_limit_bytes{name!=""}'
    )
    if uso_cpu is None or uso_memoria is None:
        return None

    cpu_por_nombre = {r["metric"].get("name"): float(r["value"][1]) for r in uso_cpu}
    memoria_por_nombre = {r["metric"].get("name"): float(r["value"][1]) for r in uso_memoria}
    limite_por_nombre = {
        r["metric"].get("name"): float(r["value"][1]) for r in (limite_memoria or [])
    }

    nombres = set(cpu_por_nombre) | set(memoria_por_nombre)
    contenedores = []
    for nombre in sorted(nombres):
        if not nombre:
            continue
        limite = limite_por_nombre.get(nombre)
        # cAdvisor reporta un límite absurdamente alto (todo el host) cuando
        # el contenedor no tiene límite de memoria configurado -- se trata
        # igual que "sin límite" (None), no como un valor real a mostrar.
        limite_valido = limite if limite and limite < 1e15 else None
        memoria_usada = memoria_por_nombre.get(nombre)
        contenedores.append(
            {
                "nombre": nombre,
                "cpu_pct": round(cpu_por_nombre.get(nombre, 0.0), 2),
                "memoria_usada_bytes": int(memoria_usada) if memoria_usada is not None else None,
                "memoria_limite_bytes": int(limite_valido) if limite_valido is not None else None,
                "memoria_pct_del_limite": (
                    round(memoria_usada / limite_valido * 100, 2)
                    if memoria_usada is not None and limite_valido
                    else None
                ),
            }
        )
    return contenedores


def _prometheus_disponible(prometheus_url: str, *, timeout: float = 1.5) -> bool:
    """Comprobación única y rápida antes de lanzar las ~10 consultas PromQL
    de `_consultar_host`/`_consultar_contenedores` -- sin esto, con
    Prometheus apagado (caso por defecto en local, ADR-009) cada una agota
    su propio timeout de 5 s y la pantalla de Recursos tarda decenas de
    segundos en responder (medido en el stack real: ~36 s)."""
    try:
        respuesta = httpx.get(f"{prometheus_url}/-/ready", timeout=timeout)
        return respuesta.status_code == 200
    except Exception:
        return False


def _consultar_ollama(ollama_url: str) -> dict | None:
    try:
        en_memoria = httpx.get(f"{ollama_url}/api/ps", timeout=5.0)
        en_memoria.raise_for_status()
        instalados = httpx.get(f"{ollama_url}/api/tags", timeout=5.0)
        instalados.raise_for_status()
        return {
            "modelos_en_memoria": en_memoria.json().get("models", []),
            "modelos_instalados": instalados.json().get("models", []),
        }
    except Exception:
        return None


def _calcular_alertas(
    sesion: Session, *, host: dict | None, contenedores: list[dict] | None
) -> list[dict]:
    alertas: list[dict] = []

    if host and host.get("disco_total_bytes") and host.get("disco_usado_bytes") is not None:
        pct_disco = host["disco_usado_bytes"] / host["disco_total_bytes"] * 100
        if pct_disco >= UMBRAL_DISCO_ALERTA_PCT:
            alertas.append(
                {
                    "tipo": "disco",
                    "mensaje": (
                        f"Disco al {pct_disco:.1f} % (umbral {UMBRAL_DISCO_ALERTA_PCT:.0f} %)"
                    ),
                }
            )

    if contenedores:
        for contenedor in contenedores:
            if (
                "ollama" in contenedor["nombre"]
                and contenedor["memoria_pct_del_limite"] is not None
                and contenedor["memoria_pct_del_limite"] >= UMBRAL_MEMORIA_OLLAMA_ALERTA_PCT
            ):
                alertas.append(
                    {
                        "tipo": "memoria_ollama",
                        "mensaje": (
                            f"Memoria de Ollama al {contenedor['memoria_pct_del_limite']:.1f} % "
                            f"de su límite (umbral {UMBRAL_MEMORIA_OLLAMA_ALERTA_PCT:.0f} %)"
                        ),
                    }
                )

    hace_24h = datetime.now(UTC) - timedelta(hours=VENTANA_TIMEOUTS_HORAS)
    recientes = sesion.query(UsoLlm).filter(UsoLlm.fecha_hora >= hace_24h).all()
    if recientes:
        pct_timeouts = sum(1 for f in recientes if f.resultado == "timeout") / len(recientes) * 100
        if pct_timeouts > UMBRAL_TIMEOUTS_ALERTA_PCT:
            alertas.append(
                {
                    "tipo": "timeouts_llm",
                    "mensaje": (
                        f"{pct_timeouts:.1f} % de llamadas al LLM con timeout en las últimas "
                        f"{VENTANA_TIMEOUTS_HORAS} h (umbral {UMBRAL_TIMEOUTS_ALERTA_PCT:.0f} %)"
                    ),
                }
            )

    return alertas


def consultar_recursos(sesion: Session) -> dict:
    prometheus_url = os.environ.get("PROMETHEUS_URL", "http://prometheus:9090")
    ollama_url = os.environ.get("LLM_BASE_URL", "http://ollama:11434")

    disponible = _prometheus_disponible(prometheus_url)
    host = _consultar_host(prometheus_url) if disponible else None
    contenedores = _consultar_contenedores(prometheus_url) if disponible else None
    ollama = _consultar_ollama(ollama_url)

    return {
        "prometheus_disponible": disponible,
        "host": host,
        "contenedores": contenedores,
        "ollama": ollama,
        "alertas": _calcular_alertas(sesion, host=host, contenedores=contenedores),
    }


# --- Configuración (HU-30) ---------------------------------------------------


def obtener_configuracion_vigente() -> dict:
    """RNF-17: solo las variables de `VARIABLES_CONFIGURACION_VISIBLES`
    (lista blanca) -- una variable ausente en el entorno no aparece en el
    resultado (no se inventa un valor)."""
    variables = {
        nombre: os.environ[nombre]
        for nombre in VARIABLES_CONFIGURACION_VISIBLES
        if nombre in os.environ
    }
    return {
        "variables": variables,
        "app_version": os.environ.get("APP_VERSION", "sin-confirmar"),
        "git_commit": os.environ.get("GIT_COMMIT", "sin-confirmar"),
    }
