"""Pipeline de CU-05 (Bloque O4): conecta extracción (`parsers`) → revisión
ortográfica (RN-06, `ortografia.revision`) → persistencia. Lo invoca
`tareas.ejecutar_analisis` cuando `tipo_revision == "ortografia"`.

El documento corregido (RF-14) NO se genera acá -- a diferencia de CU-01, se
genera solo después de que el Revisor decide sobre los hallazgos (CU-07),
ver `ortografia.generar_corregido`, que la API invoca bajo demanda
(`POST /analisis/{id}/generar-corregido`).
"""

from __future__ import annotations

import csv
import io
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from comun.modelos import Analisis, Hallazgo, VersionDocumento
from orquestador.rutas_kb import encontrar_raiz_con_kb
from ortografia.cliente_languagetool import CoincidenciaLT
from ortografia.revision import revisar_segmentos
from parsers.docx import leer_texto_docx
from parsers.pdf import leer_texto_pdf
from parsers.pptx import leer_texto_pptx
from parsers.segmentos import SegmentoTexto
from parsers.texto_plano import leer_texto_plano
from parsers.xlsx import leer_texto_xlsx

FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]
FuncionLLM = Callable[[str], str]

FORMATOS_SOPORTADOS = frozenset({"docx", "pptx", "xlsx", "pdf", "txt"})


def _ruta_glosario_por_defecto() -> Path:
    return encontrar_raiz_con_kb() / "kb" / "glosario" / "glosario.csv"


def cargar_glosario(ruta: Path | None = None) -> set[str]:
    ruta_efectiva = ruta or _ruta_glosario_por_defecto()
    with ruta_efectiva.open(encoding="utf-8") as archivo:
        return {
            fila["termino"].strip() for fila in csv.DictReader(archivo) if fila.get("termino")
        }


def _extraer_segmentos(tipo_archivo: str, contenido: bytes) -> list[SegmentoTexto]:
    extension = tipo_archivo.lower().lstrip(".")
    if extension == "docx":
        return leer_texto_docx(io.BytesIO(contenido))
    if extension == "pptx":
        return leer_texto_pptx(io.BytesIO(contenido))
    if extension == "xlsx":
        return leer_texto_xlsx(io.BytesIO(contenido))
    if extension == "pdf":
        return leer_texto_pdf(io.BytesIO(contenido))
    if extension == "txt":
        return leer_texto_plano(contenido.decode("utf-8", errors="replace"))
    raise ValueError(f"Formato no soportado para revisión ortográfica: {tipo_archivo!r}")


def procesar_documento_ortografia(
    sesion: Session,
    *,
    analisis: Analisis,
    version_original: VersionDocumento,
    contenido_original: bytes,
    tipo_archivo: str,
    funcion_revisar_lt: FuncionRevisarLT,
    funcion_llm: FuncionLLM,
    glosario: set[str] | None = None,
) -> list[Hallazgo]:
    segmentos = _extraer_segmentos(tipo_archivo, contenido_original)

    hallazgos_ortograficos = revisar_segmentos(
        segmentos,
        glosario=glosario if glosario is not None else cargar_glosario(),
        funcion_revisar_lt=funcion_revisar_lt,
        funcion_llm=funcion_llm,
    )

    filas: list[Hallazgo] = []
    for h in hallazgos_ortograficos:
        fila = Hallazgo(
            analisis_id=analisis.id,
            version_documento_id=version_original.id,
            severidad=h.severidad,
            ubicacion=h.ubicacion,
            descripcion=h.descripcion,
            correccion_sugerida=h.correccion_sugerida,
            texto_original=h.texto_original,
            estado="pendiente",
        )
        sesion.add(fila)
        filas.append(fila)

    sesion.flush()
    return filas
