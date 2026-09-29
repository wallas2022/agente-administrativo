"""PP-14 adaptado al ambiente LOCAL (Bloque K6, RNF-01): CU-01 (RN-02),
CU-05 (PP-03/04) y la ingesta de conocimiento (Bloque K3, CU-08) no
necesitan resolver ningún host fuera de loopback para completarse.

En stage, PP-14 se verifica con monitoreo de red real (firewall/proxy —
ver docs/04-pruebas/casos-prueba/PP-14.md, bloqueante para el piloto). En
local no hay ese monitoreo, así que esta prueba bloquea a nivel de socket
cualquier resolución DNS que no sea 127.0.0.1/localhost/::1 y confirma que
los tres flujos igual se completan: en este ambiente, Postgres/Redis/
Qdrant/LanguageTool están mapeados a loopback y Ollama es el nativo de
Windows también en loopback (ver docs/06-operacion/instalacion.md) — nunca
hace falta salir a internet en operación.

Se salta si LanguageTool, Ollama o Qdrant no están arriba. Correr con el
stack local levantado (Ollama nativo y LanguageTool/Qdrant vía
docker compose ... -f infra/compose.local.yml):
    LANGUAGETOOL_HOST=127.0.0.1 LLM_BASE_URL=http://127.0.0.1:11434 \
        .venv/Scripts/python.exe -m pytest tests/integration/test_pp14_modo_offline.py -v --no-cov
"""

from __future__ import annotations

import io
import os
import socket
import uuid
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import boto3
import httpx
import pytest
from moto import mock_aws
from openpyxl import Workbook
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import (
    Analisis,
    Area,
    Base,
    Documento,
    FuenteConocimiento,
    Rol,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from curaduria.extraccion import extraer_fragmentos
from curaduria.indexacion import indexar_fragmentos
from orquestador.pipeline_ortografia import cargar_glosario
from orquestador.tareas import ejecutar_analisis
from ortografia.cliente_languagetool import revisar_texto
from ortografia.revision import revisar_segmentos
from parsers.texto_plano import leer_texto_plano
from rag.cliente_embeddings import DIMENSION_BGE_M3, obtener_embedding

RAIZ = Path(__file__).resolve().parents[2]
RUTA_PDF_EJEMPLO = RAIZ / "kb" / "plantillas" / "ejemplos" / "POL-001_Politica_Cierre_EJEMPLO.pdf"
RAIZ_DATASET_CU05 = RAIZ / "tests" / "dataset" / "cu-05"
ARCHIVO_CU05 = RAIZ_DATASET_CU05 / "CU05-05_Texto_para_pegar.txt"
RUTA_GLOSARIO_CU05 = RAIZ_DATASET_CU05 / "glosario-interno-ejemplo.csv"

HOSTS_PERMITIDOS = {"127.0.0.1", "localhost", "::1"}


def _languagetool_disponible() -> bool:
    host = os.environ.get("LANGUAGETOOL_HOST", "127.0.0.1")
    puerto = os.environ.get("LANGUAGETOOL_PORT", "8010")
    try:
        r = httpx.get(f"http://{host}:{puerto}/v2/languages", timeout=10.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _ollama_disponible() -> bool:
    base_url = os.environ.get("LLM_BASE_URL", "http://127.0.0.1:11434")
    try:
        r = httpx.get(f"{base_url}/api/tags", timeout=10.0)
        return r.status_code == 200
    except httpx.HTTPError:
        return False


def _qdrant_disponible() -> bool:
    try:
        QdrantClient(host="127.0.0.1", port=6333).get_collections()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not RUTA_PDF_EJEMPLO.exists()
    or not ARCHIVO_CU05.exists()
    or not _languagetool_disponible()
    or not _ollama_disponible()
    or not _qdrant_disponible(),
    reason="dataset de CU-05/K3, LanguageTool, Ollama o Qdrant no disponibles",
)


@pytest.fixture()
def sin_red_externa(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bloquea cualquier resolución DNS fuera de loopback -- simula "red
    externa deshabilitada" para poder automatizar PP-14 en local sin
    depender de monitoreo de firewall (eso se verifica en stage)."""
    original_getaddrinfo = socket.getaddrinfo

    def _restringido(host, *args, **kwargs):  # noqa: ANN001, ANN002, ANN003
        if host not in HOSTS_PERMITIDOS:
            raise socket.gaierror(
                f"[PP-14/local] resolución de {host!r} bloqueada -- no está en "
                f"la lista de hosts locales permitidos {sorted(HOSTS_PERMITIDOS)}"
            )
        return original_getaddrinfo(host, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", _restringido)


def test_el_bloqueo_de_red_externa_esta_activo(sin_red_externa: None) -> None:
    """Si esta prueba fallara, el resto del archivo no probaría nada: hay
    que confirmar primero que el bloqueo de verdad bloquea."""
    with pytest.raises(socket.gaierror):
        socket.getaddrinfo("www.google.com", 80)


# --- CU-01 (RN-02): cuenta inexistente, ruta determinista sin LLM --------


def _libro_con_cuenta_inexistente() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Partidas"
    ws.append(["Cuenta", "Descripcion", "Fecha", "Debe", "Haber", "Moneda"])
    ws.append(["1010", "Cobro a cliente", date(2026, 1, 5), 100.0, 0.0, "Q"])
    ws.append(["9999", "Cuenta que no existe", date(2026, 1, 5), 0.0, 100.0, "Q"])
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def _sesion_con_documento_analisis_y_version(
    contenido: bytes,
) -> tuple[Session, uuid.UUID, uuid.UUID, str]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)

    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()

    usuario = Usuario(nombre="Ana Lista", email="ana@ejemplo.gt", area_id=area.id, rol_id=rol.id)
    sesion.add(usuario)
    sesion.flush()

    documento = Documento(
        nombre_original="cierre.xlsx",
        tipo_archivo="xlsx",
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="contable")
    sesion.add_all([documento, tipo_revision])
    sesion.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=usuario.id,
        fecha_inicio=datetime.now(UTC),
        estado=EstadoAnalisis.PROCESANDO.value,
        periodo_cierre="2026-01",
    )
    sesion.add(analisis)
    sesion.flush()

    llave = f"{area.id}/{documento.id}/cierre.xlsx"
    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento=llave,
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    sesion.add(version)
    sesion.commit()

    return sesion, documento.id, analisis.id, llave


def _llm_no_debe_llamarse(_prompt: str) -> str:
    raise AssertionError("RN-02 es determinista -- no debería llamar al LLM")


def test_cu01_rn02_funciona_sin_red_externa(sin_red_externa: None) -> None:
    """CU-01: una cuenta inexistente (RN-02) se explica por plantilla, sin
    LLM. Solo toca Postgres (aquí SQLite en memoria), S3 (moto, sin red
    real) y Qdrant real por loopback para la cita (la colección de prueba
    está vacía a propósito -- lo que importa es que no falle por red)."""
    contenido = _libro_con_cuenta_inexistente()
    sesion, documento_id, analisis_id, llave = _sesion_con_documento_analisis_y_version(contenido)

    with mock_aws():
        cliente_s3 = boto3.client("s3", region_name="us-east-1")
        cliente_s3.create_bucket(Bucket="documentos-pp14")
        cliente_s3.put_object(Bucket="documentos-pp14", Key=llave, Body=contenido)

        resultado = ejecutar_analisis(
            sesion,
            documento_id,
            analisis_id,
            cliente_s3=cliente_s3,
            bucket="documentos-pp14",
            cliente_qdrant=QdrantClient(host="127.0.0.1", port=6333),
            funcion_embedding=obtener_embedding,
            funcion_llm=_llm_no_debe_llamarse,
            modelo_llm="no-debe-usarse",
            coleccion_rag="pp14-cu01-vacia",
        )

    assert resultado == EstadoDocumento.CON_HALLAZGOS.value


# --- CU-05 (PP-03/04): ortografía con LanguageTool + Ollama reales --------


def test_cu05_funciona_sin_red_externa(sin_red_externa: None) -> None:
    """Un documento del dataset real de CU-05, revisado con LanguageTool y
    Ollama reales -- ambos alcanzables solo por loopback en este ambiente."""
    glosario = cargar_glosario(RUTA_GLOSARIO_CU05)
    segmentos = leer_texto_plano(ARCHIVO_CU05.read_text(encoding="utf-8"))
    modelo = os.environ.get("LLM_MODEL_PRINCIPAL", "gpt-oss:20b")

    def _llm(prompt: str) -> str:
        from rag.cliente_llm import generar_texto

        return generar_texto(prompt, modelo=modelo)

    hallazgos = revisar_segmentos(
        segmentos, glosario=glosario, funcion_revisar_lt=revisar_texto, funcion_llm=_llm
    )

    assert isinstance(hallazgos, list)


# --- Ingesta de conocimiento (Bloque K3, CU-08) ---------------------------


def _fuente_vigente_de_prueba(sesion: Session) -> FuenteConocimiento:
    area = sesion.query(Area).filter_by(nombre="Contabilidad").one_or_none()
    if area is None:
        area = Area(nombre="Contabilidad")
        sesion.add(area)
        sesion.flush()
    rol = sesion.query(Rol).filter_by(nombre="curador").one_or_none()
    if rol is None:
        rol = Rol(nombre="curador")
        sesion.add(rol)
        sesion.flush()
    usuario = Usuario(
        nombre="Carla Curadora",
        email=f"carla-{uuid.uuid4()}@ejemplo.gt",
        area_id=area.id,
        rol_id=rol.id,
        origen_autenticacion="local",
        activo=True,
    )
    sesion.add(usuario)
    sesion.flush()

    fuente = FuenteConocimiento(
        fuente_id=f"PP14-{uuid.uuid4().hex[:8]}",
        titulo="Política de cierre contable (prueba PP-14)",
        tipo="regla_interna",
        prioridad=1,
        version="pp14",
        vigente_desde=date(2026, 1, 1),
        estado="vigente",
        area_id=area.id,
        dueno="Jefatura de Contabilidad",
        archivo="POL-001.pdf",
        cargado_por=usuario.id,
        fecha_carga=datetime.now(UTC),
    )
    sesion.add(fuente)
    sesion.flush()
    return fuente


def test_ingesta_k3_funciona_sin_red_externa(sin_red_externa: None) -> None:
    """Bloque K3: extraer (parsers, sin red) + indexar (Qdrant + embeddings
    de Ollama, ambos por loopback) un documento real de la base de
    conocimiento."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)
    fuente = _fuente_vigente_de_prueba(sesion)

    fragmentos = extraer_fragmentos("pdf", RUTA_PDF_EJEMPLO.read_bytes())
    assert fragmentos  # el PDF de ejemplo tiene texto -- no dispara PdfSinTextoError

    resultado = indexar_fragmentos(
        sesion,
        QdrantClient(host="127.0.0.1", port=6333),
        fuente=fuente,
        area_nombre="Contabilidad",
        fragmentos=fragmentos,
        funcion_embedding=obtener_embedding,
        dimension=DIMENSION_BGE_M3,
        coleccion="pp14-k3-ingesta",
    )

    assert resultado.fragmentos_indexados == len(fragmentos)
