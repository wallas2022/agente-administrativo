"""Genera el dataset sintético de CU-06 (OCR) -- RF-11, PP-05, PP-06.
Herramienta de datos de prueba, no código de aplicación -- ver
docs/04-pruebas/casos-prueba/PP-05.md, PP-06.md y tests/dataset/README.md.

Texto propio (sin datos reales), con montos ("Q 1,250.00"), fechas y siglas
del glosario interno (SFC, SAT, IVA -- ver kb/glosario/glosario.csv).
Deliberadamente sin tildes: el texto se renderiza con la fuente vectorial de
OpenCV (Hershey), que no soporta acentos Unicode -- una limitación del
generador de pruebas, no del motor de OCR real (ver src/ocr/motor.py, que sí
usa Tesseract spa+eng y reconoce acentos en documentos reales).

Uso: .venv/Scripts/python.exe tests/dataset/generar_cu06.py
"""

from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pymupdf

RAIZ = Path(__file__).resolve().parent / "cu-06"

FACTURA_A = [
    "Factura No. 00123",
    "Proveedor: SFC",
    "Fecha: 15 de marzo de 2026",
    "Subtotal: Q 1,250.00",
    "IVA: Q 150.00",
    "Total: Q 1,400.00",
]
FACTURA_B = [
    "Factura No. 00456",
    "Proveedor: Banrural",
    "Fecha: 02 de abril de 2026",
    "Subtotal: Q 2,500.00",
    "IVA: Q 300.00",
    "Total: Q 2,800.00",
]
MEMO_SAT = [
    "Memo interno",
    "Para: Contabilidad",
    "Asunto: Reporte mensual SAT",
    "Fecha: 10 de mayo de 2026",
    "El reporte se presenta sin observaciones.",
]


def _renderizar(lineas: list[str], *, ancho: int = 700, alto: int = 260) -> np.ndarray:
    imagen = np.full((alto, ancho, 3), 255, dtype=np.uint8)
    alto_linea = alto // (len(lineas) + 1)
    for i, linea in enumerate(lineas, start=1):
        y = alto_linea * i
        cv2.putText(imagen, linea, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    return imagen


def _perspectiva_leve(imagen: np.ndarray) -> np.ndarray:
    """Simula una foto tomada en ángulo (no perfectamente de frente), como
    cuando alguien fotografía un documento con el celular en vez de
    escanearlo."""
    alto, ancho = imagen.shape[:2]
    desplazamiento = ancho * 0.03
    origen = np.float32([[0, 0], [ancho, 0], [ancho, alto], [0, alto]])
    destino = np.float32(
        [
            [desplazamiento, 0],
            [ancho, desplazamiento * 0.5],
            [ancho - desplazamiento * 0.5, alto],
            [0, alto - desplazamiento],
        ]
    )
    matriz = cv2.getPerspectiveTransform(origen, destino)
    return cv2.warpPerspective(
        imagen, matriz, (ancho, alto), borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255)
    )


def _desenfoque_fuerte(imagen: np.ndarray) -> np.ndarray:
    """Foto desenfocada/movida -- ni una persona podría leerla con
    confianza; el motor debe informarla ilegible, no inventar texto."""
    rng = np.random.default_rng(42)
    borrosa = cv2.GaussianBlur(imagen, (31, 31), 18)
    ruido = rng.integers(0, 90, size=borrosa.shape, dtype=np.uint8)
    return cv2.subtract(borrosa, ruido)


def _bajo_contraste(lineas: list[str], *, ancho: int = 700, alto: int = 260) -> np.ndarray:
    """Texto casi del mismo tono que el fondo (fotocopia muy clara/mal
    expuesta) -- otro caso real de "no se puede confiar en esto", distinto
    del desenfoque."""
    imagen = np.full((alto, ancho, 3), 210, dtype=np.uint8)
    alto_linea = alto // (len(lineas) + 1)
    for i, linea in enumerate(lineas, start=1):
        y = alto_linea * i
        cv2.putText(imagen, linea, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (190, 190, 190), 2)
    return imagen


def _png_bytes(imagen: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", imagen)
    assert ok
    return buffer.tobytes()


def _construir_pdf_escaneado(paginas_lineas: list[list[str]]) -> bytes:
    """PDF "escaneado": cada página es una imagen insertada, sin ninguna
    capa de texto -- como lo produciría un escáner físico."""
    documento = pymupdf.open()
    for lineas in paginas_lineas:
        pagina = documento.new_page()
        imagen = _renderizar(lineas, ancho=612, alto=300)
        pagina.insert_image(pymupdf.Rect(36, 36, 576, 336), stream=_png_bytes(imagen))
    contenido = documento.tobytes()
    documento.close()
    return contenido


def generar() -> None:
    RAIZ.mkdir(parents=True, exist_ok=True)
    respuestas: dict[str, object] = {}

    limpia = _renderizar(FACTURA_A)
    cv2.imwrite(str(RAIZ / "legible_render_limpio.png"), limpia)
    respuestas["legible_render_limpio.png"] = "\n".join(FACTURA_A)

    perspectiva = _perspectiva_leve(limpia)
    cv2.imwrite(str(RAIZ / "legible_perspectiva.png"), perspectiva)
    respuestas["legible_perspectiva.png"] = "\n".join(FACTURA_A)

    rotada = cv2.rotate(limpia, cv2.ROTATE_90_CLOCKWISE)
    cv2.imwrite(str(RAIZ / "legible_rotada_90.png"), rotada)
    respuestas["legible_rotada_90.png"] = "\n".join(FACTURA_A)

    pdf_bytes = _construir_pdf_escaneado([FACTURA_B, MEMO_SAT])
    (RAIZ / "pdf_escaneado_2paginas.pdf").write_bytes(pdf_bytes)
    respuestas["pdf_escaneado_2paginas.pdf"] = ["\n".join(FACTURA_B), "\n".join(MEMO_SAT)]

    desenfocada = _desenfoque_fuerte(_renderizar(FACTURA_A))
    cv2.imwrite(str(RAIZ / "baja_calidad_desenfoque.png"), desenfocada)

    bajo_contraste = _bajo_contraste(FACTURA_A)
    cv2.imwrite(str(RAIZ / "baja_calidad_bajo_contraste.png"), bajo_contraste)
    # Las dos de baja calidad no tienen "texto esperado": PP-06 solo exige
    # que se informen ilegibles, nunca que se les invente una transcripción.

    (RAIZ / "respuestas.json").write_text(
        json.dumps(respuestas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Dataset generado en {RAIZ}")


if __name__ == "__main__":
    generar()
