"""Pipeline de CU-06 (RF-11, fase 1/MVP): conecta el motor de OCR
(`ocr.documentos`) con la persistencia. Lo invoca `tareas.ejecutar_analisis`
cuando `tipo_revision == "ocr"`.

Fase 1 (este módulo): sin clasificación de confianza por umbral ni hallazgos
de "palabra dudosa" (eso es RN-06/Bloque 2) -- solo corre el motor y publica
el texto reconocido como una nueva versión del documento, igual que CU-01
publica la versión marcada (ver `pipeline_contable._subir_version_corregida`
en `tareas.py`).
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from comun.modelos import Analisis, VersionDocumento
from ocr.documentos import procesar_documento
from ocr.modelos import ResultadoPagina
from ocr.motor import FuncionOcr
from ocr.orientacion import FuncionOsd

__all__ = ["FuncionOcr", "FuncionOsd", "procesar_documento_ocr", "texto_completo"]


def texto_completo(paginas: list[ResultadoPagina]) -> str:
    """Concatena el texto de todas las páginas, separadas en blanco -- el
    mismo criterio que usaría alguien copiando el documento página a
    página."""
    return "\n\n".join(pagina.texto for pagina in paginas)


def procesar_documento_ocr(
    sesion: Session,
    *,
    analisis: Analisis,
    version_original: VersionDocumento,
    contenido_original: bytes,
    tipo_archivo: str,
    subir_version_texto: Callable[[str, bytes], None],
    funcion_ocr: FuncionOcr | None = None,
    funcion_osd: FuncionOsd | None = None,
) -> list[ResultadoPagina]:
    """Corre el motor de OCR sobre el documento original y publica el texto
    reconocido como una nueva `VersionDocumento` (`es_corregida=True`, mismo
    patrón que la versión marcada de CU-01). Devuelve el resultado por
    página para que capas posteriores (Bloque 2: hallazgos de palabras
    dudosas; Bloque 3: vista lado a lado) no tengan que re-ejecutar el
    motor."""
    paginas = procesar_documento(
        contenido_original,
        tipo_archivo=tipo_archivo,
        funcion_ocr=funcion_ocr,
        funcion_osd=funcion_osd,
    )

    base, _, _ = version_original.ruta_almacenamiento.rpartition(".")
    llave_texto = f"{base}.ocr.txt"
    subir_version_texto(llave_texto, texto_completo(paginas).encode("utf-8"))

    sesion.add(
        VersionDocumento(
            documento_id=version_original.documento_id,
            numero_version=version_original.numero_version + 1,
            ruta_almacenamiento=llave_texto,
            es_corregida=True,
            fecha_creacion=analisis.fecha_inicio,
        )
    )
    sesion.flush()
    return paginas
