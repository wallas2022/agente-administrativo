"""Pipeline de CU-06 (RF-11): conecta el motor de OCR (`ocr.documentos`) con
la persistencia. Lo invoca `tareas.ejecutar_analisis` cuando
`tipo_revision == "ocr"`.

Bloque 1: corre el motor y publica el texto reconocido como una nueva
versión del documento, igual que CU-01 publica la versión marcada (ver
`pipeline_contable._subir_version_corregida` en `tareas.py`).

Bloque 2 (RN-06, "calidad sin inventar"): una página ilegible (confianza
media por debajo de `OCR_PAGINA_ILEGIBLE`, o sin ninguna palabra reconocida)
publica cero texto -- un aviso, no un reconocimiento poco confiable (PP-06).
Si TODAS las páginas de OCR del documento son ilegibles, el análisis igual
se completa (no falla): se agrega un único `Hallazgo` de aviso, que es lo
que hace que `documento.estado` termine en "con_hallazgos" en vez de
"en_revision" (ver `tareas.ejecutar_analisis`). Las palabras por debajo de
`OCR_CONF_REVISAR` en páginas legibles se persisten como `Hallazgo`
individuales (`ocr.hallazgos.detectar_palabras_dudosas`), con sugerencia
opcional de LanguageTool -- nunca se autocorrige el texto reconocido.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy.orm import Session

from comun.modelos import Analisis, Hallazgo, VersionDocumento
from ocr.calidad import Umbrales, es_pagina_ilegible, umbrales_desde_entorno
from ocr.documentos import procesar_documento
from ocr.hallazgos import FuncionRevisarLT, PalabraDudosa, detectar_palabras_dudosas
from ocr.modelos import ResultadoPagina
from ocr.motor import FuncionOcr
from ocr.orientacion import FuncionOsd

__all__ = [
    "FuncionOcr",
    "FuncionOsd",
    "FuncionRevisarLT",
    "procesar_documento_ocr",
    "texto_completo",
]

_AVISO_PAGINA_ILEGIBLE = (
    "[Página {numero}: ilegible -- no se pudo reconocer texto con confianza suficiente]"
)


def _texto_pagina(pagina: ResultadoPagina, umbrales: Umbrales) -> str:
    if es_pagina_ilegible(pagina, umbrales):
        return _AVISO_PAGINA_ILEGIBLE.format(numero=pagina.numero)
    return pagina.texto


def texto_completo(paginas: list[ResultadoPagina], *, umbrales: Umbrales | None = None) -> str:
    """Concatena el texto de todas las páginas, separadas en blanco -- el
    mismo criterio que usaría alguien copiando el documento página a
    página. Una página ilegible nunca aporta texto inventado: aporta un
    aviso (RN-06, PP-06)."""
    umbrales_efectivos = umbrales or umbrales_desde_entorno()
    return "\n\n".join(_texto_pagina(pagina, umbrales_efectivos) for pagina in paginas)


def _hallazgo_documento_ilegible(
    *, analisis: Analisis, version_original: VersionDocumento, total_paginas: int
) -> Hallazgo:
    return Hallazgo(
        analisis_id=analisis.id,
        version_documento_id=version_original.id,
        severidad="alta",
        ubicacion="Documento completo",
        descripcion=(
            f"Las {total_paginas} página(s) procesadas por OCR son ilegibles: no se pudo "
            "reconocer texto con confianza suficiente (RN-06, PP-06). No se inventó texto."
        ),
        estado="pendiente",
    )


def _hallazgo_palabra_dudosa(
    *, analisis: Analisis, version_original: VersionDocumento, dudosa: PalabraDudosa
) -> Hallazgo:
    return Hallazgo(
        analisis_id=analisis.id,
        version_documento_id=version_original.id,
        severidad="alta" if dudosa.nivel == "dudosa" else "media",
        ubicacion=f"Página {dudosa.pagina}",
        descripcion=(
            f"Palabra reconocida con confianza {dudosa.nivel} ({dudosa.confianza:.0f}%): "
            f"«{dudosa.texto}»"
        ),
        correccion_sugerida=dudosa.sugerencia,
        texto_original=dudosa.texto,
        estado="pendiente",
    )


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
    funcion_revisar_lt: FuncionRevisarLT | None = None,
    glosario: set[str] | None = None,
    umbrales: Umbrales | None = None,
) -> tuple[list[Hallazgo], list[ResultadoPagina]]:
    """Corre el motor de OCR, publica el texto reconocido (con avisos en vez
    de texto para páginas ilegibles) como una nueva `VersionDocumento`, y
    devuelve los `Hallazgo` de calidad (aviso de documento ilegible, o
    palabras dudosas con su nivel/sugerencia) junto con el resultado por
    página -- para que capas posteriores (Bloque 3: vista lado a lado) no
    tengan que re-ejecutar el motor."""
    umbrales_efectivos = umbrales or umbrales_desde_entorno()
    paginas = procesar_documento(
        contenido_original,
        tipo_archivo=tipo_archivo,
        funcion_ocr=funcion_ocr,
        funcion_osd=funcion_osd,
    )

    base, _, _ = version_original.ruta_almacenamiento.rpartition(".")
    llave_texto = f"{base}.ocr.txt"
    subir_version_texto(
        llave_texto, texto_completo(paginas, umbrales=umbrales_efectivos).encode("utf-8")
    )
    sesion.add(
        VersionDocumento(
            documento_id=version_original.documento_id,
            numero_version=version_original.numero_version + 1,
            ruta_almacenamiento=llave_texto,
            es_corregida=True,
            fecha_creacion=analisis.fecha_inicio,
        )
    )

    hallazgos: list[Hallazgo] = []
    paginas_ocr = [p for p in paginas if not p.texto_nativo]
    if paginas_ocr and all(es_pagina_ilegible(p, umbrales_efectivos) for p in paginas_ocr):
        fila = _hallazgo_documento_ilegible(
            analisis=analisis, version_original=version_original, total_paginas=len(paginas_ocr)
        )
        sesion.add(fila)
        hallazgos.append(fila)
    else:
        for dudosa in detectar_palabras_dudosas(
            paginas,
            umbrales=umbrales_efectivos,
            glosario=glosario,
            funcion_revisar_lt=funcion_revisar_lt,
        ):
            fila = _hallazgo_palabra_dudosa(
                analisis=analisis, version_original=version_original, dudosa=dudosa
            )
            sesion.add(fila)
            hallazgos.append(fila)

    sesion.flush()
    return hallazgos, paginas
