"""RF-14, CU-05 (Bloque O4): aplicar solo las correcciones aceptadas por el
Revisor (CU-07) sobre el documento original.
"""

import io
import uuid

import pymupdf
from docx import Document

from comun.modelos import Hallazgo
from ortografia.generar_corregido import generar_documento_corregido
from parsers.docx import leer_texto_docx


def test_generar_documento_corregido_aplica_solo_hallazgos_aceptados() -> None:
    documento = io.BytesIO()
    doc = Document()
    doc.add_paragraph("Este procedimiento fue aprovado ayer.")
    doc.save(documento)

    hallazgo_aceptado = Hallazgo(
        analisis_id=uuid.uuid4(),
        version_documento_id=uuid.uuid4(),
        severidad="media",
        ubicacion="Párrafo 0",
        descripcion="«aprovado»: error",
        correccion_sugerida="aprobado",
        texto_original="aprovado",
        estado="aceptado",
    )
    hallazgo_rechazado = Hallazgo(
        analisis_id=uuid.uuid4(),
        version_documento_id=uuid.uuid4(),
        severidad="media",
        ubicacion="Párrafo 0",
        descripcion="«ayer»: irrelevante",
        correccion_sugerida="hoy",
        texto_original="ayer",
        estado="rechazado",
    )

    resultado = generar_documento_corregido(
        tipo_archivo="docx",
        contenido_original=documento.getvalue(),
        hallazgos=[hallazgo_aceptado, hallazgo_rechazado],
    )

    assert resultado is not None
    contenido_corregido, extension = resultado
    assert extension == "docx"
    segmentos = leer_texto_docx(io.BytesIO(contenido_corregido))
    texto = segmentos[0].texto
    assert "aprobado" in texto
    assert "ayer" in texto  # el rechazado no se aplicó


def test_generar_documento_corregido_sin_aceptados_devuelve_none() -> None:
    resultado = generar_documento_corregido(
        tipo_archivo="txt", contenido_original=b"texto", hallazgos=[]
    )

    assert resultado is None


def test_pdf_genera_docx_corregido_con_extension_distinta() -> None:
    documento_pdf = pymupdf.open()
    documento_pdf.new_page().insert_text((72, 72), "Se encontro un depositos sin registrar.")
    contenido = documento_pdf.tobytes()
    documento_pdf.close()

    hallazgo = Hallazgo(
        analisis_id=uuid.uuid4(),
        version_documento_id=uuid.uuid4(),
        severidad="media",
        ubicacion="Página 1, bloque 1",
        descripcion="«depositos»: error",
        correccion_sugerida="depósitos",
        texto_original="depositos",
        estado="aceptado",
    )

    resultado = generar_documento_corregido(
        tipo_archivo="pdf", contenido_original=contenido, hallazgos=[hallazgo]
    )

    assert resultado is not None
    contenido_corregido, extension = resultado
    assert extension == "docx"
    segmentos = leer_texto_docx(io.BytesIO(contenido_corregido))
    assert any("depósitos" in s.texto for s in segmentos)
