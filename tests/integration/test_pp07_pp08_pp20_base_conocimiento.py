"""PP-07, PP-08 y PP-20 (Bloque K7, RF-16/RF-17/RNF-06, CU-08): verifican
con datos e infraestructura reales (Qdrant + Ollama nativo, sin mocks) que
las citas de la base de conocimiento son correctas, vigentes, y respetan
la separación regla/referencia.

PP-07/PP-08 en su forma literal (docs/04-pruebas/casos-prueba/PP-07.md,
PP-08.md) piden una base de conocimiento de PILOTO real (20-50 documentos)
que todavía no existe -- ese umbral a esa escala queda [POR CONFIRMAR].
Este archivo verifica el mismo criterio (fuente correcta, vigente, y
nunca una versión obsoleta) sobre una muestra pequeña pero real y
reproducible: los 3 documentos de ejemplo de kb/plantillas/ejemplos/,
pasando por el ciclo de vida real de CU-08 (curaduria.fuentes.aprobar_fuente
+ curaduria.indexacion.indexar_fuente), no datos sintéticos insertados
directamente en Qdrant.

Se salta si Ollama o Qdrant no están arriba. Correr con el stack local
levantado:
    LLM_BASE_URL=http://127.0.0.1:11434 \
        .venv/Scripts/python.exe -m pytest \
        tests/integration/test_pp07_pp08_pp20_base_conocimiento.py -v -s --no-cov
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Iterator
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest
from qdrant_client import QdrantClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.modelos import Area, Base, FuenteConocimiento, Rol, Usuario
from curaduria.extraccion import extraer_fragmentos
from curaduria.fuentes import aprobar_fuente
from curaduria.indexacion import desactivar_fragmentos_de_fuente, indexar_fuente
from rag.busqueda import buscar_fragmentos, construir_citas
from rag.cliente_embeddings import DIMENSION_BGE_M3, obtener_embedding

RAIZ_EJEMPLOS = Path(__file__).resolve().parents[2] / "kb" / "plantillas" / "ejemplos"
RUTA_POL_001_VIGENTE = RAIZ_EJEMPLOS / "POL-001_Politica_Cierre_EJEMPLO.pdf"
RUTA_POL_000_OBSOLETA = RAIZ_EJEMPLOS / "POL-000_Politica_Cierre_OBSOLETA_EJEMPLO.pdf"
RUTA_EST_001_DOCX = RAIZ_EJEMPLOS / "EST-001_Guia_Estilo_EJEMPLO.docx"

COLECCION = "pp07-pp08-pp20-kb"


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
    not RUTA_POL_001_VIGENTE.exists()
    or not RUTA_POL_000_OBSOLETA.exists()
    or not RUTA_EST_001_DOCX.exists()
    or not _ollama_disponible()
    or not _qdrant_disponible(),
    reason="dataset de ejemplo (kb/plantillas/ejemplos), Ollama o Qdrant no disponibles",
)


def _usuario_curador(sesion: Session) -> Usuario:
    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="curador")
    sesion.add_all([area, rol])
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
    return usuario


def _nueva_fuente(
    sesion: Session,
    usuario: Usuario,
    *,
    fuente_id: str,
    titulo: str,
    tipo: str,
    version: str,
    archivo: str,
) -> FuenteConocimiento:
    prioridad = {"regla_interna": 1, "normativa": 2, "referencia": 3}[tipo]
    fuente = FuenteConocimiento(
        fuente_id=fuente_id,
        titulo=titulo,
        tipo=tipo,
        prioridad=prioridad,
        version=version,
        vigente_desde=date(2026, 1, 1),
        estado="borrador",
        area_id=usuario.area_id,
        dueno="Jefatura de Contabilidad",
        archivo=archivo,
        cargado_por=usuario.id,
        fecha_carga=datetime.now(UTC),
    )
    sesion.add(fuente)
    sesion.flush()
    return fuente


@pytest.fixture(scope="module")
def base_conocimiento_real() -> Iterator[dict[str, Any]]:
    """Ingesta real (Bloque K3) de 3 fuentes en una sola colección de
    Qdrant, con el ciclo de vida real de CU-08:
    - POL-001 v1.0 (contenido del PDF "...OBSOLETA..."), aprobada primero.
    - POL-001 v2.0 (contenido del PDF vigente), aprobada después --
      obsoletea v1.0 automáticamente (curaduria.fuentes.aprobar_fuente).
      El orden aprobar -> desactivar v1 -> indexar v2 es el que corrige el
      bug real encontrado en este mismo bloque (ver api/main.py y el
      commit de K7): desactivar DESPUÉS de indexar apagaba también los
      puntos recién indexados de v2, porque comparten fuente_id.
    - EST-001 (tipo="referencia", .docx), vigente.
    Se arma una sola vez por módulo (llamadas reales a Ollama)."""
    sesion = Session(create_engine("sqlite:///:memory:"))
    Base.metadata.create_all(sesion.get_bind())
    usuario = _usuario_curador(sesion)
    cliente_qdrant = QdrantClient(host="127.0.0.1", port=6333)
    if cliente_qdrant.collection_exists(COLECCION):
        cliente_qdrant.delete_collection(COLECCION)

    comun = dict(
        sesion=sesion,
        cliente_qdrant=cliente_qdrant,
        area_nombre="Contabilidad",
        funcion_embedding=obtener_embedding,
        dimension=DIMENSION_BGE_M3,
        usuario_id=usuario.id,
        coleccion=COLECCION,
    )

    v1 = _nueva_fuente(
        sesion, usuario, fuente_id="POL-001", titulo="Política de cierre contable",
        tipo="regla_interna", version="1.0", archivo=RUTA_POL_000_OBSOLETA.name,
    )
    aprobar_fuente(sesion, v1, aprobado_por=usuario.id, ahora=datetime.now(UTC))
    indexar_fuente(
        sesion, cliente_qdrant, fuente=v1, tipo_archivo="pdf",
        contenido_archivo=RUTA_POL_000_OBSOLETA.read_bytes(),
        area_nombre=comun["area_nombre"], funcion_embedding=comun["funcion_embedding"],
        dimension=comun["dimension"], usuario_id=comun["usuario_id"], coleccion=comun["coleccion"],
    )

    v2 = _nueva_fuente(
        sesion, usuario, fuente_id="POL-001", titulo="Política de cierre contable",
        tipo="regla_interna", version="2.0", archivo=RUTA_POL_001_VIGENTE.name,
    )
    anterior = aprobar_fuente(sesion, v2, aprobado_por=usuario.id, ahora=datetime.now(UTC))
    assert anterior is not None and anterior.id == v1.id
    desactivar_fragmentos_de_fuente(
        cliente_qdrant, coleccion=COLECCION, fuente_id_negocio="POL-001"
    )
    indexar_fuente(
        sesion, cliente_qdrant, fuente=v2, tipo_archivo="pdf",
        contenido_archivo=RUTA_POL_001_VIGENTE.read_bytes(),
        area_nombre=comun["area_nombre"], funcion_embedding=comun["funcion_embedding"],
        dimension=comun["dimension"], usuario_id=comun["usuario_id"], coleccion=comun["coleccion"],
    )

    referencia = _nueva_fuente(
        sesion, usuario, fuente_id="EST-001", titulo="Guía de estilo",
        tipo="referencia", version="1.0", archivo=RUTA_EST_001_DOCX.name,
    )
    aprobar_fuente(sesion, referencia, aprobado_por=usuario.id, ahora=datetime.now(UTC))
    indexar_fuente(
        sesion, cliente_qdrant, fuente=referencia, tipo_archivo="docx",
        contenido_archivo=RUTA_EST_001_DOCX.read_bytes(),
        area_nombre=comun["area_nombre"], funcion_embedding=comun["funcion_embedding"],
        dimension=comun["dimension"], usuario_id=comun["usuario_id"], coleccion=comun["coleccion"],
    )

    yield {
        "cliente_qdrant": cliente_qdrant,
        "fragmentos_v1": extraer_fragmentos("pdf", RUTA_POL_000_OBSOLETA.read_bytes()),
        "fragmentos_v2": extraer_fragmentos("pdf", RUTA_POL_001_VIGENTE.read_bytes()),
        "fragmentos_ref": extraer_fragmentos("docx", RUTA_EST_001_DOCX.read_bytes()),
    }

    cliente_qdrant.delete_collection(COLECCION)


def test_pp20_ingesta_pdf_produce_citas_con_seccion_correcta(base_conocimiento_real) -> None:
    datos = base_conocimiento_real
    fragmento = next(f for f in datos["fragmentos_v2"] if f.seccion == "§3")

    resultados = buscar_fragmentos(
        datos["cliente_qdrant"],
        coleccion=COLECCION,
        texto_consulta=fragmento.contenido,
        funcion_embedding=obtener_embedding,
        top_k=1,
    )

    assert resultados, "no se encontró ningún fragmento vigente para la consulta del PDF"
    assert resultados[0].fuente_id == "POL-001"
    assert resultados[0].version == "2.0"
    assert resultados[0].seccion == "§3"
    assert resultados[0].pagina == fragmento.pagina


def test_pp20_ingesta_docx_produce_citas_con_seccion_correcta(base_conocimiento_real) -> None:
    """top_k amplio a propósito: con los parámetros de producción (top_k=3
    por defecto), en este corpus de prueba (7 fragmentos de POL-001,
    prioridad 1, frente a solo 5 de EST-001, prioridad 3) el orden por
    prioridad de `buscar_fragmentos` empuja a EST-001 fuera del top-3 casi
    siempre -- ver el hallazgo documentado en
    test_pp07_hallazgo_referencia_puede_quedar_fuera_del_top_k_por_prioridad.
    Eso es un efecto legítimo del diseño de K4 (prioridad antes que
    similitud, ya probado en tests/unit/test_rag.py), no un defecto de la
    ingesta. Aquí se aísla lo que sí es objetivo de PP-20: que, una vez
    recuperado, el fragmento de EST-001 trae la sección correcta."""
    datos = base_conocimiento_real
    # El primer fragmento (portada/título) puede no tener marca de sección
    # -- se usa uno que sí la tenga para poder verificar la cita completa.
    fragmento = next(f for f in datos["fragmentos_ref"] if f.seccion is not None)

    resultados = buscar_fragmentos(
        datos["cliente_qdrant"],
        coleccion=COLECCION,
        texto_consulta=fragmento.contenido,
        funcion_embedding=obtener_embedding,
        top_k=20,
    )
    _, referencia = construir_citas(resultados)

    assert referencia is not None, (
        f"EST-001 no aparece entre los resultados ampliados: {resultados}"
    )
    assert "EST-001" in referencia
    assert fragmento.seccion in referencia


def test_pp08_ninguna_cita_referencia_la_version_obsoleta(base_conocimiento_real) -> None:
    """El contenido de v1.0 (obsoleta) es la edición anterior de la MISMA
    política que v2.0 (vigente) -- textualmente muy similar -- así que si
    el filtro estado=vigente fallara, sería justo este escenario el que lo
    revelaría (a diferencia de dos documentos sin relación temática)."""
    datos = base_conocimiento_real
    consultas = [f.contenido for f in datos["fragmentos_v2"]]

    citas_a_obsoleta = 0
    for consulta in consultas:
        resultados = buscar_fragmentos(
            datos["cliente_qdrant"],
            coleccion=COLECCION,
            texto_consulta=consulta,
            funcion_embedding=obtener_embedding,
            top_k=3,
        )
        citas_a_obsoleta += sum(
            1 for r in resultados if r.fuente_id == "POL-001" and r.version == "1.0"
        )

    assert citas_a_obsoleta == 0


def test_pp07_citas_de_una_muestra_real_son_correctas_y_vigentes(
    base_conocimiento_real, capsys: pytest.CaptureFixture[str]
) -> None:
    """No es la muestra de piloto (20-50 documentos reales) que pide
    PP-07.md -- eso queda [POR CONFIRMAR] hasta que exista una base de
    conocimiento de piloto real. Aquí se mide el mismo criterio (fuente
    correcta + vigente) con los parámetros de PRODUCCIÓN de
    `buscar_fragmentos` (top_k=3 por defecto), sobre el subconjunto donde
    la muestra sí es representativa: consultas cuya fuente correcta es la
    de mayor prioridad (POL-001, regla_interna) -- exactamente el caso que
    más le importa a RF-12 (la "Regla aplicada" de un hallazgo). El
    subconjunto de EST-001 (referencia) queda fuera de este umbral por una
    razón real y documentada, no oculta: ver el hallazgo de
    test_pp07_hallazgo_referencia_puede_quedar_fuera_del_top_k_por_prioridad."""
    datos = base_conocimiento_real
    muestra = [f.contenido for f in datos["fragmentos_v2"]]

    correctas = 0
    for consulta in muestra:
        resultados = buscar_fragmentos(
            datos["cliente_qdrant"],
            coleccion=COLECCION,
            texto_consulta=consulta,
            funcion_embedding=obtener_embedding,
        )
        regla_aplicada, _ = construir_citas(resultados)
        if regla_aplicada is not None and "POL-001" in regla_aplicada:
            correctas += 1

    porcentaje = 100 * correctas / len(muestra)
    with capsys.disabled():
        print(
            f"\nPP-07 ('Regla aplicada', muestra reproducible de {len(muestra)} consultas "
            f"reales, no la muestra de piloto de PP-07.md): "
            f"{porcentaje:.1f}% fuente correcta+vigente"
        )
    assert porcentaje >= 95.0


def test_pp07_hallazgo_referencia_puede_quedar_fuera_del_top_k_por_prioridad(
    base_conocimiento_real, capsys: pytest.CaptureFixture[str]
) -> None:
    """No es una aserción de umbral de PP-07 -- es un HALLAZGO de este
    bloque (K7) que se deja documentado en el código y en local-SKB.md,
    no oculto: con los parámetros de producción (`buscar_fragmentos`
    top_k=3, factor_candidatos=5) y un área donde una fuente de mayor
    prioridad tiene >= top_k fragmentos vigentes, una fuente tipo
    "referencia" puede no aparecer NUNCA como cita para ninguna consulta,
    incluso siendo la más relevante semánticamente. Es consecuencia directa
    del diseño intencional de K4 ("prioridad antes que similitud", ya
    probado en tests/unit/test_rag.py) -- no se cambia aquí porque es una
    decisión de negocio, no un defecto; se deja constancia para que quede
    sobre la mesa en una futura revisión de RF-12/K4 (p. ej. ¿debería
    "Referencia" buscarse con su propio top_k, independiente del de
    "Regla aplicada"?)."""
    datos = base_conocimiento_real
    consulta = next(f for f in datos["fragmentos_ref"] if f.seccion is not None).contenido

    resultados_produccion = buscar_fragmentos(
        datos["cliente_qdrant"],
        coleccion=COLECCION,
        texto_consulta=consulta,
        funcion_embedding=obtener_embedding,
    )
    _, referencia_produccion = construir_citas(resultados_produccion)

    with capsys.disabled():
        print(
            "\nPP-07 (hallazgo, no umbral): con top_k=3 (producción), la 'Referencia' "
            f"para una consulta real de EST-001 es: {referencia_produccion!r}"
        )
