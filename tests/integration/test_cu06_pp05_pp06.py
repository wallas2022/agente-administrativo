"""PP-05/PP-06 (CU-06, Bloque 4): CER en imágenes legibles y "nunca inventar"
en imágenes de baja calidad, contra el Tesseract real -- no mockeado.

El binario de Tesseract no está disponible en el host (ver docs/02-analisis/
04-analisis-cu06-ocr.md): este archivo se salta ahí automáticamente y debe
correrse dentro del contenedor del worker (que sí lo tiene, ver
src/orquestador/Dockerfile):
    docker cp tests/dataset/cu-06 infra-worker-1:/app/tests-dataset-cu-06
    docker cp tests/integration/test_cu06_pp05_pp06.py infra-worker-1:/app/
    docker exec infra-worker-1 pip install --no-cache-dir pytest
    docker exec -e CU06_DATASET=/app/tests-dataset-cu-06 infra-worker-1 \
        python -m pytest test_cu06_pp05_pp06.py -v -s
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from pathlib import Path

import pytest

from ocr.calidad import Umbrales, es_pagina_ilegible, umbrales_desde_entorno
from ocr.documentos import procesar_documento
from ocr.orientacion import detectar_rotacion_tesseract

# Mismo patrón que tests/integration/test_cu05_pp03_pp04.py: CU06_DATASET
# permite apuntar a una copia del dataset dentro del contenedor (ver
# docstring arriba) sin depender de que tests/dataset/ viaje con la imagen.
RAIZ_DATASET = Path(os.environ.get("CU06_DATASET", "")) if os.environ.get("CU06_DATASET") else (
    Path(__file__).resolve().parents[1] / "dataset" / "cu-06"
)
RUTA_RESPUESTAS = RAIZ_DATASET / "respuestas.json"
TESSERACT_DISPONIBLE = shutil.which("tesseract") is not None

pytestmark = pytest.mark.skipif(
    not RUTA_RESPUESTAS.exists() or not TESSERACT_DISPONIBLE,
    reason="dataset de CU-06 o Tesseract no disponibles (correr dentro del worker)",
)

PP05_UMBRAL_CER = 0.05  # PP-05: CER <= 5 % (equivalente a >= 95 % de precisión)


def _distancia_levenshtein(a: str, b: str) -> int:
    """Implementación propia (sin librerías de terceros, por instrucción
    explícita de P-11) -- programación dinámica clásica de edición de
    cadenas, O(len(a) * len(b))."""
    if len(a) < len(b):
        a, b = b, a
    fila_anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        fila_actual = [i] + [0] * len(b)
        for j, cb in enumerate(b, start=1):
            costo = 0 if ca == cb else 1
            fila_actual[j] = min(
                fila_anterior[j] + 1,
                fila_actual[j - 1] + 1,
                fila_anterior[j - 1] + costo,
            )
        fila_anterior = fila_actual
    return fila_anterior[-1]


def _normalizar(texto: str) -> str:
    """CER sobre el contenido, no sobre los espacios en blanco incidentales
    (saltos de línea exactos, dobles espacios) que Tesseract puede alinear
    distinto a como se escribió el texto esperado."""
    return re.sub(r"\s+", " ", texto).strip()


def _cer(esperado: str, obtenido: str) -> float:
    esperado_norm = _normalizar(esperado)
    obtenido_norm = _normalizar(obtenido)
    if not esperado_norm:
        return 0.0 if not obtenido_norm else 1.0
    return _distancia_levenshtein(esperado_norm, obtenido_norm) / len(esperado_norm)


def _cargar_respuestas() -> dict[str, object]:
    return json.loads(RUTA_RESPUESTAS.read_text(encoding="utf-8"))


def _extension(nombre: str) -> str:
    return nombre.rsplit(".", 1)[-1].lower()


@pytest.mark.parametrize(
    "nombre_archivo",
    ["legible_render_limpio.png", "legible_perspectiva.png", "legible_rotada_90.png"],
)
def test_pp05_cer_en_imagenes_legibles(nombre_archivo: str) -> None:
    respuestas = _cargar_respuestas()
    contenido = (RAIZ_DATASET / nombre_archivo).read_bytes()

    inicio = time.monotonic()
    paginas = procesar_documento(contenido, tipo_archivo=_extension(nombre_archivo))
    segundos = time.monotonic() - inicio

    assert len(paginas) == 1
    pagina = paginas[0]
    cer = _cer(respuestas[nombre_archivo], pagina.texto)  # type: ignore[arg-type]
    print(f"\n[{nombre_archivo}] CER={cer:.3f} confianza_media={pagina.confianza_media:.1f} "
          f"segundos={segundos:.2f}")

    assert cer <= PP05_UMBRAL_CER, f"CER {cer:.3f} por encima del umbral PP-05 (5 %)"
    # RNF-03 (0 cifras alteradas): el monto exacto debe aparecer tal cual,
    # no solo "aproximadamente bien" dentro de la tolerancia general de CER.
    assert "Q 1,250.00" in pagina.texto, "el monto no se reconoció exactamente"


def test_pp05_cer_en_pdf_escaneado_de_dos_paginas() -> None:
    respuestas = _cargar_respuestas()
    nombre_archivo = "pdf_escaneado_2paginas.pdf"
    contenido = (RAIZ_DATASET / nombre_archivo).read_bytes()
    esperado_por_pagina: list[str] = respuestas[nombre_archivo]  # type: ignore[assignment]

    inicio = time.monotonic()
    paginas = procesar_documento(contenido, tipo_archivo="pdf")
    segundos = time.monotonic() - inicio

    assert len(paginas) == 2
    for pagina, esperado in zip(paginas, esperado_por_pagina, strict=True):
        cer = _cer(esperado, pagina.texto)
        segundos_por_pagina = segundos / len(paginas)
        print(
            f"\n[{nombre_archivo} pág. {pagina.numero}] CER={cer:.3f} "
            f"confianza_media={pagina.confianza_media:.1f} segundos/pág={segundos_por_pagina:.2f}"
        )
        assert cer <= PP05_UMBRAL_CER, f"CER {cer:.3f} por encima del umbral PP-05 (5 %)"

    # El monto de la página 1 y la sigla SAT de la página 2 deben sobrevivir
    # intactos (0 cifras alteradas / 0 texto inventado).
    assert "Q 2,500.00" in paginas[0].texto
    assert "SAT" in paginas[1].texto


def test_rotacion_90_grados_se_detecta_con_tesseract_real() -> None:
    """Confirma el mecanismo de OSD contra el binario real (no un fake) --
    separado del CER general, que ya corre sobre la imagen ya enderezada."""
    import cv2
    import numpy as np

    contenido = (RAIZ_DATASET / "legible_rotada_90.png").read_bytes()
    imagen = cv2.imdecode(np.frombuffer(contenido, dtype=np.uint8), cv2.IMREAD_COLOR)

    rotacion_detectada = detectar_rotacion_tesseract(imagen)
    print(f"\nrotación detectada por OSD: {rotacion_detectada}°")
    assert rotacion_detectada in (90, 270), (
        "Tesseract debería detectar que la imagen está girada 90°/270° "
        f"para enderezarla; detectó {rotacion_detectada}°"
    )


@pytest.mark.parametrize(
    "nombre_archivo", ["baja_calidad_desenfoque.png", "baja_calidad_bajo_contraste.png"]
)
def test_pp06_imagenes_de_baja_calidad_se_informan_ilegibles(nombre_archivo: str) -> None:
    """PP-06: 100 % de las ilegibles se informan como tales, 0 texto
    inventado -- nunca una transcripción con apariencia de resultado
    confiable sobre una imagen que, de hecho, no se puede leer."""
    contenido = (RAIZ_DATASET / nombre_archivo).read_bytes()
    umbrales: Umbrales = umbrales_desde_entorno()

    inicio = time.monotonic()
    paginas = procesar_documento(contenido, tipo_archivo="png")
    segundos = time.monotonic() - inicio

    assert len(paginas) == 1
    pagina = paginas[0]
    print(
        f"\n[{nombre_archivo}] confianza_media={pagina.confianza_media:.1f} "
        f"texto={pagina.texto!r} segundos={segundos:.2f}"
    )

    assert es_pagina_ilegible(pagina, umbrales), (
        f"se esperaba que {nombre_archivo} se marcara ilegible "
        f"(confianza_media={pagina.confianza_media:.1f})"
    )


# --- Bloque 2b: capturas de pantalla (métrica informativa, separada de PP-05) ---

RAIZ_CAPTURAS = RAIZ_DATASET / "capturas"
RUTA_RESPUESTAS_CAPTURAS = RAIZ_CAPTURAS / "respuestas_capturas.json"
CER_INFORMATIVO_CAPTURAS = 0.10


def _cargar_respuestas_capturas() -> dict[str, str]:
    return json.loads(RUTA_RESPUESTAS_CAPTURAS.read_text(encoding="utf-8"))


@pytest.mark.skipif(
    not RUTA_RESPUESTAS_CAPTURAS.exists() or not TESSERACT_DISPONIBLE,
    reason="dataset de capturas de CU-06 o Tesseract no disponibles",
)
@pytest.mark.parametrize(
    "nombre_archivo", ["pagina_web_100.png", "ventana_75.png", "pagina_web_jpg_comprimido.jpg"]
)
def test_capturas_cer_informativo(nombre_archivo: str) -> None:
    """Bloque 2b: meta informativa de CER <= 10 % en capturas de pantalla,
    aparte del umbral oficial de PP-05 (5 %, para documentos escaneados) --
    el texto de interfaz (fuentes muy chicas, antialiased) es un caso más
    difícil a propósito, no se espera el mismo piso que en PP-05."""
    respuestas = _cargar_respuestas_capturas()
    extension = nombre_archivo.rsplit(".", 1)[-1].lower()
    contenido = (RAIZ_CAPTURAS / nombre_archivo).read_bytes()

    inicio = time.monotonic()
    paginas = procesar_documento(contenido, tipo_archivo=extension)
    segundos = time.monotonic() - inicio

    assert len(paginas) == 1
    pagina = paginas[0]
    cer = _cer(respuestas[nombre_archivo], pagina.texto)
    print(
        f"\n[captura {nombre_archivo}] CER={cer:.3f} confianza_media={pagina.confianza_media:.1f} "
        f"segundos={segundos:.2f} texto={pagina.texto!r}"
    )

    assert cer <= CER_INFORMATIVO_CAPTURAS, (
        f"CER {cer:.3f} por encima de la meta informativa de capturas (10 %)"
    )
