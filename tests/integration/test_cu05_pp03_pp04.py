"""PP-03/PP-04 (Bloque O5, CU-05): recall/falsos positivos y preservación de
formato del documento corregido, contra el servicio LanguageTool real y el
LLM real (Ollama) -- no mockeados. Se salta si alguno de los dos no está
disponible (ver docs/03-diseno/secuencia/cu-05-ortografia.md).

A diferencia de tests/unit/, esto no es hermético ni rápido a propósito:
mide lo mismo que reportará docs/04-pruebas/resultados/local-S2.md. Correr
con el stack local levantado:
    .venv/Scripts/python.exe -m pytest tests/integration/test_cu05_pp03_pp04.py -v -s --no-cov
"""

from __future__ import annotations

import io
import os
import time
from collections import defaultdict
from pathlib import Path

import httpx
import pytest
from openpyxl import load_workbook

from orquestador.pipeline_ortografia import cargar_glosario
from ortografia.cliente_languagetool import revisar_texto
from ortografia.revision import HallazgoOrtografico, revisar_segmentos
from parsers.correcciones import CorreccionAplicable
from parsers.docx import leer_texto_docx
from parsers.pdf import leer_texto_pdf
from parsers.pptx import leer_texto_pptx
from parsers.segmentos import SegmentoTexto
from parsers.texto_plano import leer_texto_plano
from parsers.xlsx import leer_texto_xlsx

RAIZ_DATASET = Path(__file__).resolve().parents[1] / "dataset" / "cu-05"
RUTA_GLOSARIO = RAIZ_DATASET / "glosario-interno-ejemplo.csv"
RUTA_RESPUESTAS = RAIZ_DATASET / "Respuestas_CU05_Ortografia.xlsx"

RNF04_LIMITE_SEGUNDOS = 60.0


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


pytestmark = pytest.mark.skipif(
    not RAIZ_DATASET.exists() or not _languagetool_disponible() or not _ollama_disponible(),
    reason="dataset de CU-05, LanguageTool u Ollama no disponibles",
)


def _cargar_respuestas_esperadas() -> dict[str, list[tuple[str, str]]]:
    wb = load_workbook(RUTA_RESPUESTAS, data_only=True)
    ws = wb["Respuestas CU-05"]
    esperadas: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for fila in ws.iter_rows(min_row=4, values_only=True):
        numero, archivo, _ubicacion, error, correcto, _tipo = fila
        if not isinstance(numero, int) or not archivo:
            continue
        esperadas[str(archivo)].append((str(error), str(correcto)))
    return dict(esperadas)


def _extraer_segmentos(ruta: Path) -> list[SegmentoTexto]:
    extension = ruta.suffix.lower().lstrip(".")
    if extension == "docx":
        return leer_texto_docx(str(ruta))
    if extension == "pptx":
        return leer_texto_pptx(str(ruta))
    if extension == "xlsx":
        return leer_texto_xlsx(str(ruta))
    if extension == "pdf":
        return leer_texto_pdf(str(ruta))
    if extension == "txt":
        return leer_texto_plano(ruta.read_text(encoding="utf-8"))
    raise ValueError(f"Extensión no soportada: {ruta}")


def _llm_real(prompt: str) -> str:
    from rag.cliente_llm import generar_texto

    modelo = os.environ.get("LLM_MODEL_PRINCIPAL", "gpt-oss:20b")
    return generar_texto(prompt, modelo=modelo)


def _coincide(esperado: str, detectado: str) -> bool:
    esperado_norm, detectado_norm = esperado.strip().lower(), detectado.strip().lower()
    return esperado_norm in detectado_norm or detectado_norm in esperado_norm


def _recall_y_falsos_positivos(
    esperados: list[tuple[str, str]], hallazgos: list[HallazgoOrtografico]
) -> tuple[int, int, int]:
    """Devuelve (coincidencias, total_esperados, falsos_positivos)."""
    detectados = [h.texto_original for h in hallazgos]
    coincidencias = sum(
        1
        for error_esperado, _ in esperados
        if any(_coincide(error_esperado, d) for d in detectados)
    )
    falsos_positivos = sum(
        1
        for d in detectados
        if not any(_coincide(error_esperado, d) for error_esperado, _ in esperados)
    )
    return coincidencias, len(esperados), falsos_positivos


@pytest.fixture(scope="module")
def glosario() -> set[str]:
    return cargar_glosario(RUTA_GLOSARIO)


@pytest.fixture(scope="module")
def respuestas_esperadas() -> dict[str, list[tuple[str, str]]]:
    return _cargar_respuestas_esperadas()


ARCHIVOS = [
    "CU05-01_Procedimiento_Cierre_Mensual.docx",
    "CU05-02_Resultados_Cierre_Agosto.pptx",
    "CU05-03_Informe_Conciliacion_Bancaria.pdf",
    "CU05-04_Catalogo_Descripciones.xlsx",
    "CU05-05_Texto_para_pegar.txt",
]


_RESULTADOS: dict[str, dict] = {}


@pytest.mark.parametrize("nombre_archivo", ARCHIVOS)
def test_pp03_recall_y_falsos_positivos_por_archivo(
    nombre_archivo: str,
    glosario: set[str],
    respuestas_esperadas: dict[str, list[tuple[str, str]]],
    capsys: pytest.CaptureFixture[str],
) -> None:
    ruta = RAIZ_DATASET / nombre_archivo
    segmentos = _extraer_segmentos(ruta)
    esperados = respuestas_esperadas[nombre_archivo]

    inicio = time.monotonic()
    hallazgos = revisar_segmentos(
        segmentos, glosario=glosario, funcion_revisar_lt=revisar_texto, funcion_llm=_llm_real
    )
    duracion = time.monotonic() - inicio

    coincidencias, total_esperados, falsos_positivos = _recall_y_falsos_positivos(
        esperados, hallazgos
    )
    total_detectados = len(hallazgos)
    tasa_fp = falsos_positivos / total_detectados if total_detectados else 0.0

    cumple_rnf04 = duracion <= RNF04_LIMITE_SEGUNDOS
    etiqueta_rnf04 = "cumple" if cumple_rnf04 else "NO cumple"
    with capsys.disabled():
        print(
            f"\n{nombre_archivo}: {coincidencias}/{total_esperados} esperados detectados, "
            f"{falsos_positivos}/{total_detectados} falsos positivos ({tasa_fp:.0%}), "
            f"{duracion:.1f}s ({etiqueta_rnf04} RNF-04, límite {RNF04_LIMITE_SEGUNDOS:.0f}s)"
        )
    # RNF-04 se mide y se reporta (ver docs/04-pruebas/resultados/local-S2.md)
    # pero no se afirma como pass/fail acá: en este equipo sin GPU, un
    # documento con algún caso dudoso necesita 1 llamada al LLM
    # (gpt-oss:20b) que ya se sabe lenta en CPU (ver local-S1.md) -- es una
    # limitación de hardware conocida, no algo que este test deba ocultar
    # fallando en silencio ni tampoco bloquear la suite por ello.

    # Ningún término del glosario debe aparecer como texto_original marcado.
    glosario_normalizado = {t.strip().lower() for t in glosario}
    for h in hallazgos:
        assert h.texto_original.strip().lower() not in glosario_normalizado, (
            f"'{h.texto_original}' es un término del glosario y no debió marcarse"
        )

    # Guarda resultados para el resumen final (ver test_pp03_resumen_global).
    _RESULTADOS[nombre_archivo] = {
        "coincidencias": coincidencias,
        "total_esperados": total_esperados,
        "falsos_positivos": falsos_positivos,
        "total_detectados": total_detectados,
        "duracion_s": duracion,
        "hallazgos": hallazgos,
    }


def test_pp03_recall_global_es_al_menos_90_por_ciento(capsys: pytest.CaptureFixture[str]) -> None:
    if len(_RESULTADOS) < len(ARCHIVOS):
        pytest.skip("corre después de test_pp03_recall_y_falsos_positivos_por_archivo")

    total_coincidencias = sum(r["coincidencias"] for r in _RESULTADOS.values())
    total_esperados = sum(r["total_esperados"] for r in _RESULTADOS.values())
    total_detectados = sum(r["total_detectados"] for r in _RESULTADOS.values())
    total_falsos_positivos = sum(r["falsos_positivos"] for r in _RESULTADOS.values())

    recall = total_coincidencias / total_esperados if total_esperados else 1.0
    tasa_fp = total_falsos_positivos / total_detectados if total_detectados else 0.0

    with capsys.disabled():
        print(
            f"\nGLOBAL: recall {recall:.1%} ({total_coincidencias}/{total_esperados}), "
            f"falsos positivos {tasa_fp:.1%} ({total_falsos_positivos}/{total_detectados})"
        )
        print("RNF-04 por archivo (límite 60s):")
        for nombre, r in _RESULTADOS.items():
            cumple = "cumple" if r["duracion_s"] <= RNF04_LIMITE_SEGUNDOS else "NO cumple"
            print(f"  {nombre}: {r['duracion_s']:.1f}s ({cumple})")

    assert recall >= 0.90, f"Recall {recall:.1%} por debajo del umbral de PP-03 (>= 90%)"
    assert tasa_fp <= 0.10, (
        f"Falsos positivos {tasa_fp:.1%} por encima del umbral de PP-03 (<= 10%)"
    )


def test_pp04_docx_corregido_conserva_negrita_tabla_y_encabezado() -> None:
    """Aplica las correcciones que SÍ coinciden con la hoja de respuestas
    (como si el Revisor las hubiera aceptado) y confirma que el documento
    resultante abre sin error y conserva negrita, tabla y encabezado."""
    nombre = "CU05-01_Procedimiento_Cierre_Mensual.docx"
    if nombre not in _RESULTADOS:
        pytest.skip("corre después de test_pp03_recall_y_falsos_positivos_por_archivo")

    from docx import Document

    from parsers.docx import aplicar_correcciones_docx

    ruta = RAIZ_DATASET / nombre
    hallazgos = _RESULTADOS[nombre]["hallazgos"]
    correcciones = [
        CorreccionAplicable(h.ubicacion, h.texto_original, h.correccion_sugerida) for h in hallazgos
    ]

    resultado = aplicar_correcciones_docx(str(ruta), correcciones)

    documento = Document(io.BytesIO(resultado.contenido))
    assert any(p.text.strip() for p in documento.paragraphs), "el documento abrió pero está vacío"
    assert len(documento.tables) == 1, "la tabla no se conservó"
    assert any(r.bold for p in documento.paragraphs for r in p.runs), "la negrita no se conservó"
    encabezados = [
        p.text for s in documento.sections for p in s.header.paragraphs if p.text.strip()
    ]
    assert encabezados, "el encabezado no se conservó"


def test_pp04_pptx_corregido_conserva_titulo_vinetas_y_notas() -> None:
    """Igual que el docx, pero para PPTX: título, viñetas y notas del
    orador (el .pptx del dataset tiene los 3, ver CU05-02)."""
    nombre = "CU05-02_Resultados_Cierre_Agosto.pptx"
    if nombre not in _RESULTADOS:
        pytest.skip("corre después de test_pp03_recall_y_falsos_positivos_por_archivo")

    from pptx import Presentation

    from parsers.pptx import aplicar_correcciones_pptx

    ruta = RAIZ_DATASET / nombre
    hallazgos = _RESULTADOS[nombre]["hallazgos"]
    correcciones = [
        CorreccionAplicable(h.ubicacion, h.texto_original, h.correccion_sugerida) for h in hallazgos
    ]

    resultado = aplicar_correcciones_pptx(str(ruta), correcciones)

    presentacion = Presentation(io.BytesIO(resultado.contenido))
    diapositivas = list(presentacion.slides)
    assert len(diapositivas) == 3, "no se conservó el número de diapositivas"
    assert diapositivas[0].shapes.title.text.strip(), "el título no se conservó"
    assert diapositivas[1].has_notes_slide, "las notas del orador no se conservaron"
    assert diapositivas[1].notes_slide.notes_text_frame.text.strip()


def test_pp04_xlsx_corregido_conserva_hoja_y_celdas_no_tocadas() -> None:
    """PP-04 (punto 4, Bloque O6): igual que docx/pptx, pero para XLSX --
    el dataset real (CU05-04) no tiene fórmulas, así que lo que hay que
    conservar es la hoja completa (6 filas x 3 columnas) y las celdas que
    ninguna corrección tocó (encabezados, códigos de cuenta)."""
    nombre = "CU05-04_Catalogo_Descripciones.xlsx"
    if nombre not in _RESULTADOS:
        pytest.skip("corre después de test_pp03_recall_y_falsos_positivos_por_archivo")

    from parsers.xlsx import aplicar_correcciones_xlsx

    ruta = RAIZ_DATASET / nombre
    hallazgos = _RESULTADOS[nombre]["hallazgos"]
    correcciones = [
        CorreccionAplicable(h.ubicacion, h.texto_original, h.correccion_sugerida) for h in hallazgos
    ]
    assert correcciones, "PP-03 no detectó ningún error en este archivo -- no hay nada que corregir"

    libro_original = load_workbook(str(ruta), data_only=False)
    hoja_original = libro_original["Descripciones"]

    resultado = aplicar_correcciones_xlsx(str(ruta), correcciones)

    libro = load_workbook(io.BytesIO(resultado.contenido), data_only=False)
    assert libro.sheetnames == ["Descripciones"], "no se conservó la hoja"
    hoja = libro["Descripciones"]
    assert hoja.dimensions == "A1:C6", "no se conservaron filas/columnas"
    # A1 (encabezado) y A4 (código de cuenta) no los tocó ninguna corrección
    # -- deben quedar exactamente igual que en el archivo original.
    assert hoja["A1"].value == hoja_original["A1"].value, "el encabezado no se conservó"
    assert hoja["A4"].value == hoja_original["A4"].value == "2020", (
        "una celda no tocada por ninguna corrección cambió"
    )

    textos_originales = {c.texto_original.strip().lower() for c in correcciones}
    for fila in hoja.iter_rows():
        for celda in fila:
            if isinstance(celda.value, str):
                assert celda.value.strip().lower() not in textos_originales, (
                    f"'{celda.value}' sigue con el error original en {celda.coordinate}"
                )


def test_pp04_texto_plano_corregido_no_toca_lo_que_no_marco_languagetool() -> None:
    """PP-04 (punto 4, Bloque O6): igual que docx/pptx/xlsx, pero para el
    modo "pegar texto" -- no hay formato que preservar, así que lo que hay
    que verificar es que el texto corregido reemplaza justo los errores
    detectados y deja el resto (incluido el término de glosario "SFC")
    intacto."""
    nombre = "CU05-05_Texto_para_pegar.txt"
    if nombre not in _RESULTADOS:
        pytest.skip("corre después de test_pp03_recall_y_falsos_positivos_por_archivo")

    from parsers.texto_plano import aplicar_correcciones_texto_plano

    ruta = RAIZ_DATASET / nombre
    texto_original = ruta.read_text(encoding="utf-8")
    hallazgos = _RESULTADOS[nombre]["hallazgos"]
    correcciones = [
        CorreccionAplicable(h.ubicacion, h.texto_original, h.correccion_sugerida) for h in hallazgos
    ]
    assert correcciones, "PP-03 no detectó ningún error en este archivo -- no hay nada que corregir"

    texto_corregido = aplicar_correcciones_texto_plano(texto_original, correcciones)

    assert texto_corregido != texto_original, "el texto corregido quedó igual al original"
    assert "SFC" in texto_corregido, "el término de glosario no debió tocarse"
    for correccion in correcciones:
        assert correccion.texto_original not in texto_corregido, (
            f"'{correccion.texto_original}' sigue en el texto corregido"
        )
        assert correccion.texto_nuevo in texto_corregido, (
            f"'{correccion.texto_nuevo}' no aparece en el texto corregido"
        )
