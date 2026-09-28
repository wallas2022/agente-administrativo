"""Pipeline de CU-05 (Bloque O4/O6): conecta extracción (`parsers`) → revisión
ortográfica (RN-06, `ortografia.revision`) → persistencia. Lo invoca
`tareas.ejecutar_analisis` cuando `tipo_revision == "ortografia"`.

RNF-04 (Bloque O6): `procesar_documento_ortografia` es la fase 1 -- solo
LanguageTool + glosario, rápida -- y publica de inmediato tanto los
hallazgos deterministas ("pendiente") como los dudosos ("en_validacion",
sin confirmar todavía); el análisis llega a un estado terminal sin esperar
al LLM. `resolver_dudosos_ortografia` es la fase 2 -- la única que llama al
LLM, en un solo lote -- y la corre `tareas.ejecutar_analisis` (síncrona, si
no hay cómo encolarla) o `tareas.validar_dudosos_ortografia` en segundo
plano (producción). Ver `orquestador.tareas` para cómo se conectan.

El documento corregido (RF-14) NO se genera acá -- a diferencia de CU-01, se
genera solo después de que el Revisor decide sobre los hallazgos (CU-07),
ver `ortografia.generar_corregido`, que la API invoca bajo demanda
(`POST /analisis/{id}/generar-corregido`).
"""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Callable
from pathlib import Path

from sqlalchemy.orm import Session

from comun.modelos import Analisis, Hallazgo, VersionDocumento
from orquestador.rutas_kb import encontrar_raiz_con_kb
from ortografia.cliente_languagetool import CoincidenciaLT
from ortografia.revision import CandidatoDudoso, clasificar_segmentos, validar_candidatos_con_llm
from parsers.docx import leer_texto_docx
from parsers.pdf import leer_texto_pdf
from parsers.pptx import leer_texto_pptx
from parsers.segmentos import SegmentoTexto
from parsers.texto_plano import leer_texto_plano
from parsers.xlsx import leer_texto_xlsx

FuncionRevisarLT = Callable[[str], list[CoincidenciaLT]]
FuncionLLM = Callable[[str], str]

FORMATOS_SOPORTADOS = frozenset({"docx", "pptx", "xlsx", "pdf", "txt"})

_PATRON_DESCRIPCION = re.compile(r"^«.+?»:\s*([\s\S]*)$", re.DOTALL)


def _ruta_glosario_por_defecto() -> Path:
    return encontrar_raiz_con_kb() / "kb" / "glosario" / "glosario.csv"


def cargar_glosario(ruta: Path | None = None) -> set[str]:
    ruta_efectiva = ruta or _ruta_glosario_por_defecto()
    with ruta_efectiva.open(encoding="utf-8") as archivo:
        return {
            fila["termino"].strip() for fila in csv.DictReader(archivo) if fila.get("termino")
        }


def extraer_segmentos(tipo_archivo: str, contenido: bytes) -> list[SegmentoTexto]:
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
    glosario: set[str] | None = None,
) -> tuple[list[Hallazgo], list[Hallazgo], dict[str, str]]:
    """Fase 1 (RNF-04, Bloque O6): solo LanguageTool + glosario -- sin LLM.
    Devuelve los hallazgos deterministas (estado "pendiente"), los dudosos
    (estado "en_validacion", todavía sin confirmar) y el contexto de cada
    segmento por ubicación (para que la fase 2 -- ver
    `resolver_dudosos_ortografia` -- no tenga que volver a extraer el
    documento si ya lo tiene a mano, p. ej. en la misma corrida síncrona)."""
    segmentos = extraer_segmentos(tipo_archivo, contenido_original)
    clasificacion = clasificar_segmentos(
        segmentos,
        glosario=glosario if glosario is not None else cargar_glosario(),
        funcion_revisar_lt=funcion_revisar_lt,
    )

    deterministas: list[Hallazgo] = []
    for h in clasificacion.deterministas:
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
        deterministas.append(fila)

    dudosos: list[Hallazgo] = []
    for candidato in clasificacion.dudosos:
        fila = Hallazgo(
            analisis_id=analisis.id,
            version_documento_id=version_original.id,
            severidad="media",
            ubicacion=candidato.ubicacion,
            descripcion=f"«{candidato.texto_original}»: {candidato.mensaje_lt}",
            correccion_sugerida=candidato.sugerencia_lt,
            texto_original=candidato.texto_original,
            estado="en_validacion",
            # Reutilizado solo para reconstruir el `CandidatoDudoso` en la
            # fase 2 (id de regla de LanguageTool, p. ej. "MIN_MESES") --
            # nunca lo pisa CU-01, que no usa "en_validacion". Evita agregar
            # una columna nueva solo para esto (Bloque O6).
            fuente_citada=candidato.regla_id,
        )
        sesion.add(fila)
        dudosos.append(fila)

    sesion.flush()
    contexto_por_ubicacion = {s.ubicacion: s.texto for s in segmentos}
    return deterministas, dudosos, contexto_por_ubicacion


def _mensaje_de_descripcion(descripcion: str) -> str:
    coincidencia = _PATRON_DESCRIPCION.match(descripcion)
    return coincidencia.group(1) if coincidencia else descripcion


def resolver_dudosos_ortografia(
    sesion: Session,
    *,
    hallazgos: list[Hallazgo],
    contexto_por_ubicacion: dict[str, str],
    funcion_llm: FuncionLLM,
) -> None:
    """Fase 2 (RNF-04, Bloque O6): la única que llama al LLM -- una sola vez
    por documento, para todos los hallazgos "en_validacion" a la vez. Los
    que el LLM confirma pasan a "confirmado" (con la sugerencia/explicación
    final, decidible por el Revisor igual que "pendiente"); los que
    descarta pasan a "descartado" -- NO se borran, quedan visibles para
    auditoría (RNF-06). No hace nada si `hallazgos` viene vacío (no gasta
    una llamada al LLM sin casos que validar)."""
    if not hallazgos:
        return

    candidatos = [
        CandidatoDudoso(
            ubicacion=h.ubicacion,
            texto_original=h.texto_original or "",
            sugerencia_lt=h.correccion_sugerida or "",
            mensaje_lt=_mensaje_de_descripcion(h.descripcion),
            regla_id=h.fuente_citada or "",
        )
        for h in hallazgos
    ]
    resultados = validar_candidatos_con_llm(
        candidatos, contexto_por_ubicacion=contexto_por_ubicacion, funcion_llm=funcion_llm
    )

    for hallazgo, resultado in zip(hallazgos, resultados, strict=True):
        if resultado.es_error:
            # "confirmado" (no "pendiente"): distinto en la UI de un hallazgo
            # determinista que nunca pasó por el LLM (Bloque O6, punto 1)
            # -- decidible igual que "pendiente" (ver decidir_hallazgo, que
            # no valida el estado previo).
            hallazgo.estado = "confirmado"
            hallazgo.correccion_sugerida = resultado.correccion_sugerida
            hallazgo.descripcion = (
                f"«{resultado.candidato.texto_original}»: {resultado.explicacion}"
            )
        else:
            hallazgo.estado = "descartado"
        hallazgo.fuente_citada = None
    sesion.flush()
