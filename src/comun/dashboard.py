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

import httpx
from sqlalchemy.orm import Session

from comun.modelos import Analisis, UsoLlm, Usuario

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


def _filas_de_consumo(
    sesion: Session,
    *,
    desde: date | None,
    hasta: date | None,
    area_id: uuid.UUID | None,
    caso_uso: str | None,
    modelo: str | None,
) -> list[UsoLlm]:
    consulta = sesion.query(UsoLlm)
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
    return consulta.all()


def _duracion_media_analisis_por_grupo(
    sesion: Session, filas: list[UsoLlm], campo: str
) -> dict[str, float | None]:
    """HU-28: "duración media del análisis" por caso de uso/modelo -- de los
    `Analisis` ya terminados (`fecha_fin` no nulo) referenciados por las
    filas de uso de ese grupo (`embeddings_kb` no tiene `analisis_id`,
    queda en `None` -- no aplica, no es "no informado")."""
    ids_por_grupo: dict[str, set[uuid.UUID]] = {}
    for fila in filas:
        if fila.analisis_id is None:
            continue
        ids_por_grupo.setdefault(getattr(fila, campo), set()).add(fila.analisis_id)

    resultado: dict[str, float | None] = {}
    for clave, ids in ids_por_grupo.items():
        analisis_filas = (
            sesion.query(Analisis)
            .filter(Analisis.id.in_(ids), Analisis.fecha_fin.isnot(None))
            .all()
        )
        duraciones_ms = [
            (a.fecha_fin - a.fecha_inicio).total_seconds() * 1000
            for a in analisis_filas
            if a.fecha_fin is not None
        ]
        resultado[clave] = sum(duraciones_ms) / len(duraciones_ms) if duraciones_ms else None
    return resultado


def _rankear(sesion: Session, filas: list[UsoLlm], campo: str) -> list[dict]:
    agregados: dict[str, dict] = {}
    for fila in filas:
        clave = getattr(fila, campo)
        grupo = agregados.setdefault(
            clave, {"tokens_totales": 0, "duracion_llm_total_ms": 0, "llamadas": 0}
        )
        grupo["tokens_totales"] += (fila.tokens_entrada or 0) + (fila.tokens_salida or 0)
        grupo["duracion_llm_total_ms"] += fila.duracion_total_ms or 0
        grupo["llamadas"] += 1

    duracion_media_analisis = _duracion_media_analisis_por_grupo(sesion, filas, campo)
    return [
        {
            campo: clave,
            **valores,
            "duracion_media_analisis_ms": duracion_media_analisis.get(clave),
        }
        for clave, valores in sorted(
            agregados.items(), key=lambda kv: -kv[1]["tokens_totales"]
        )
    ]


def calcular_consumo(
    sesion: Session,
    *,
    desde: date | None = None,
    hasta: date | None = None,
    area_id: uuid.UUID | None = None,
    caso_uso: str | None = None,
    modelo: str | None = None,
) -> dict:
    filas = _filas_de_consumo(
        sesion, desde=desde, hasta=hasta, area_id=area_id, caso_uso=caso_uso, modelo=modelo
    )

    tokens_entrada = sum(f.tokens_entrada or 0 for f in filas)
    tokens_salida = sum(f.tokens_salida or 0 for f in filas)
    llamadas = len(filas)
    timeouts = sum(1 for f in filas if f.resultado == "timeout")
    duracion_generacion_total_s = sum(f.duracion_generacion_ms or 0 for f in filas) / 1000

    serie_por_fecha: dict[date, dict] = {}
    for fila in filas:
        clave = fila.fecha_hora.date()
        dia = serie_por_fecha.setdefault(
            clave, {"tokens_entrada": 0, "tokens_salida": 0, "llamadas": 0}
        )
        dia["tokens_entrada"] += fila.tokens_entrada or 0
        dia["tokens_salida"] += fila.tokens_salida or 0
        dia["llamadas"] += 1

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
            {"fecha": fecha.isoformat(), **valores}
            for fecha, valores in sorted(serie_por_fecha.items())
        ],
        "ranking_caso_uso": _rankear(sesion, filas, "caso_uso"),
        "ranking_modelo": _rankear(sesion, filas, "modelo"),
    }


def calcular_consumo_por_usuario(
    sesion: Session, *, desde: date | None = None, hasta: date | None = None
) -> list[dict]:
    """HU-27: tabla por usuario -- área, número de análisis distintos,
    tokens, tiempo de LLM y timeouts."""
    consulta = sesion.query(UsoLlm, Usuario).join(Usuario, UsoLlm.usuario_id == Usuario.id)
    if desde is not None:
        consulta = consulta.filter(UsoLlm.fecha_hora >= desde)
    if hasta is not None:
        consulta = consulta.filter(UsoLlm.fecha_hora < hasta + timedelta(days=1))

    agregados: dict[uuid.UUID, dict] = {}
    for uso, usuario in consulta.all():
        grupo = agregados.setdefault(
            usuario.id,
            {
                "usuario_id": str(usuario.id),
                "usuario_nombre": usuario.nombre,
                "usuario_email": usuario.email,
                "area_nombre": usuario.area.nombre,
                "analisis_ids": set(),
                "tokens_entrada": 0,
                "tokens_salida": 0,
                "duracion_llm_total_ms": 0,
                "timeouts": 0,
            },
        )
        if uso.analisis_id is not None:
            grupo["analisis_ids"].add(uso.analisis_id)
        grupo["tokens_entrada"] += uso.tokens_entrada or 0
        grupo["tokens_salida"] += uso.tokens_salida or 0
        grupo["duracion_llm_total_ms"] += uso.duracion_total_ms or 0
        if uso.resultado == "timeout":
            grupo["timeouts"] += 1

    filas = [
        {
            "usuario_id": g["usuario_id"],
            "usuario_nombre": g["usuario_nombre"],
            "usuario_email": g["usuario_email"],
            "area_nombre": g["area_nombre"],
            "numero_analisis": len(g["analisis_ids"]),
            "tokens_entrada": g["tokens_entrada"],
            "tokens_salida": g["tokens_salida"],
            "duracion_llm_total_ms": g["duracion_llm_total_ms"],
            "timeouts": g["timeouts"],
        }
        for g in agregados.values()
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
