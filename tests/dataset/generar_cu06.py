"""Genera el dataset sintético de CU-06 (OCR) -- RF-11, PP-05, PP-06.
Herramienta de datos de prueba, no código de aplicación -- ver
docs/04-pruebas/casos-prueba/PP-05.md, PP-06.md y tests/dataset/README.md.

Texto propio (sin datos reales), con montos ("Q 1,250.00"), fechas y siglas
del glosario interno (SFC, SAT, IVA -- ver kb/glosario/glosario.csv).
Deliberadamente sin tildes: el texto se renderiza con la fuente vectorial de
OpenCV (Hershey), que no soporta acentos Unicode -- una limitación del
generador de pruebas, no del motor de OCR real (ver src/ocr/motor.py, que sí
usa Tesseract spa+eng y reconoce acentos en documentos reales).

Las imágenes "escaneadas" (legible_*, baja_calidad_*) llevan un chunk PNG
`pHYs` a 300 DPI y una textura de fondo leve -- sin esto, `ocr.capturas.
es_captura_de_pantalla` las confundiría con capturas de pantalla (fondo
perfectamente plano, sin DPI), que es exactamente lo que distingue a estas
imágenes de las de `tests/dataset/cu-06/capturas/` (Bloque 2b), generadas
sin DPI y sin textura a propósito. La inserción de DPI se hace a mano
(`_insertar_dpi_png`, duplicado de `ocr.capturas.insertar_dpi_png`) para que
este script siga sin depender de nada del paquete `src/` (igual que
`generar_cu01.py`).

Uso: .venv/Scripts/python.exe tests/dataset/generar_cu06.py
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

import cv2
import numpy as np
import pymupdf

RAIZ = Path(__file__).resolve().parent / "cu-06"
RAIZ_CAPTURAS = RAIZ / "capturas"
DPI_ESCANEO = 300

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
CAPTURA_PAGINA_WEB = [
    "Archivo  Editar  Ver  Ayuda",
    "Bienvenido al portal de Contabilidad",
    "Aqui puede consultar sus reportes mensuales.",
]
CAPTURA_VENTANA = [
    "Archivo  Editar  Ver",
    "Panel de control",
    "Ultima sincronizacion: hoy",
]


def _renderizar(
    lineas: list[str], *, ancho: int = 700, alto: int = 260, textura: bool = False
) -> np.ndarray:
    imagen = np.full((alto, ancho, 3), 255, dtype=np.uint8)
    alto_linea = alto // (len(lineas) + 1)
    for i, linea in enumerate(lineas, start=1):
        y = alto_linea * i
        cv2.putText(imagen, linea, (20, y), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 0), 2)
    if textura:
        imagen = _agregar_textura_papel(imagen)
    return imagen


def _agregar_textura_papel(imagen: np.ndarray) -> np.ndarray:
    """Ruido leve (papel real, incluso limpio, nunca es perfectamente
    uniforme) -- sin esto, `ocr.capturas.fondo_plano` no podría distinguir
    un documento escaneado de una captura de pantalla."""
    rng = np.random.default_rng(1)
    ruido = rng.normal(0, 6, imagen.shape).astype(np.int16)
    return np.clip(imagen.astype(np.int16) + ruido, 0, 255).astype(np.uint8)


def _renderizar_captura(
    lineas: list[str], *, ancho: int, alto: int, escala_fuente: float
) -> np.ndarray:
    """Interfaz de usuario: fondo perfectamente plano (sin textura) y texto
    chico -- lo opuesto de `_renderizar(..., textura=True)`."""
    imagen = np.full((alto, ancho, 3), 255, dtype=np.uint8)
    alto_linea = alto // (len(lineas) + 1)
    for i, linea in enumerate(lineas, start=1):
        y = alto_linea * i
        color = (20, 20, 20)
        cv2.putText(imagen, linea, (10, y), cv2.FONT_HERSHEY_SIMPLEX, escala_fuente, color, 1)
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
    return _agregar_textura_papel(imagen)


def _png_bytes(imagen: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", imagen)
    assert ok
    return buffer.tobytes()


def _insertar_dpi_png(contenido: bytes, dpi: int) -> bytes:
    """Duplicado deliberado de `ocr.capturas.insertar_dpi_png` (este script
    no importa nada de `src/`, igual que `generar_cu01.py`) -- inserta un
    chunk `pHYs` justo después de `IHDR`."""
    longitud_ihdr = int.from_bytes(contenido[8:12], "big")
    fin_ihdr = 8 + 8 + longitud_ihdr + 4
    ppu = round(dpi / 0.0254)
    datos_phys = struct.pack(">IIB", ppu, ppu, 1)
    chunk = (
        struct.pack(">I", len(datos_phys))
        + b"pHYs"
        + datos_phys
        + struct.pack(">I", zlib.crc32(b"pHYs" + datos_phys) & 0xFFFFFFFF)
    )
    return contenido[:fin_ihdr] + chunk + contenido[fin_ihdr:]


def _guardar_escaneo(ruta: Path, imagen: np.ndarray) -> None:
    """Para las imágenes que representan un documento escaneado/fotografiado
    (no una captura de pantalla): siempre con DPI embebido."""
    ruta.write_bytes(_insertar_dpi_png(_png_bytes(imagen), DPI_ESCANEO))


def _construir_pdf_escaneado(paginas_lineas: list[list[str]]) -> bytes:
    """PDF "escaneado": cada página es una imagen insertada, sin ninguna
    capa de texto -- como lo produciría un escáner físico."""
    documento = pymupdf.open()
    for lineas in paginas_lineas:
        pagina = documento.new_page()
        imagen = _renderizar(lineas, ancho=612, alto=300, textura=True)
        pagina.insert_image(pymupdf.Rect(36, 36, 576, 336), stream=_png_bytes(imagen))
    contenido = documento.tobytes()
    documento.close()
    return contenido


def generar() -> None:
    RAIZ.mkdir(parents=True, exist_ok=True)
    RAIZ_CAPTURAS.mkdir(parents=True, exist_ok=True)
    respuestas: dict[str, object] = {}

    # La textura de papel se agrega DESPUÉS de cualquier transformación
    # geométrica (perspectiva, rotación): `_perspectiva_leve` rellena las
    # esquinas que deja el recorte con blanco sólido -- si la textura se
    # aplicara antes, esas esquinas quedarían perfectamente planas y
    # `ocr.capturas.fondo_plano` confundiría la imagen con una captura.
    limpia_sin_textura = _renderizar(FACTURA_A)
    limpia = _agregar_textura_papel(limpia_sin_textura)
    _guardar_escaneo(RAIZ / "legible_render_limpio.png", limpia)
    respuestas["legible_render_limpio.png"] = "\n".join(FACTURA_A)

    perspectiva = _agregar_textura_papel(_perspectiva_leve(limpia_sin_textura))
    _guardar_escaneo(RAIZ / "legible_perspectiva.png", perspectiva)
    respuestas["legible_perspectiva.png"] = "\n".join(FACTURA_A)

    rotada = _agregar_textura_papel(cv2.rotate(limpia_sin_textura, cv2.ROTATE_90_CLOCKWISE))
    _guardar_escaneo(RAIZ / "legible_rotada_90.png", rotada)
    respuestas["legible_rotada_90.png"] = "\n".join(FACTURA_A)

    pdf_bytes = _construir_pdf_escaneado([FACTURA_B, MEMO_SAT])
    (RAIZ / "pdf_escaneado_2paginas.pdf").write_bytes(pdf_bytes)
    respuestas["pdf_escaneado_2paginas.pdf"] = ["\n".join(FACTURA_B), "\n".join(MEMO_SAT)]

    desenfocada = _desenfoque_fuerte(_renderizar(FACTURA_A, textura=True))
    _guardar_escaneo(RAIZ / "baja_calidad_desenfoque.png", desenfocada)

    bajo_contraste = _bajo_contraste(FACTURA_A)
    _guardar_escaneo(RAIZ / "baja_calidad_bajo_contraste.png", bajo_contraste)
    # Las dos de baja calidad no tienen "texto esperado": PP-06 solo exige
    # que se informen ilegibles, nunca que se les invente una transcripción.

    (RAIZ / "respuestas.json").write_text(
        json.dumps(respuestas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # --- Capturas de pantalla (Bloque 2b): sin DPI, fondo plano -------------
    respuestas_capturas: dict[str, str] = {}

    pagina_web = _renderizar_captura(CAPTURA_PAGINA_WEB, ancho=640, alto=140, escala_fuente=0.5)
    (RAIZ_CAPTURAS / "pagina_web_100.png").write_bytes(_png_bytes(pagina_web))
    respuestas_capturas["pagina_web_100.png"] = "\n".join(CAPTURA_PAGINA_WEB)

    ventana_75 = _renderizar_captura(CAPTURA_VENTANA, ancho=420, alto=100, escala_fuente=0.38)
    (RAIZ_CAPTURAS / "ventana_75.png").write_bytes(_png_bytes(ventana_75))
    respuestas_capturas["ventana_75.png"] = "\n".join(CAPTURA_VENTANA)

    ok, jpg_buffer = cv2.imencode(".jpg", pagina_web, [cv2.IMWRITE_JPEG_QUALITY, 35])
    assert ok
    (RAIZ_CAPTURAS / "pagina_web_jpg_comprimido.jpg").write_bytes(jpg_buffer.tobytes())
    respuestas_capturas["pagina_web_jpg_comprimido.jpg"] = "\n".join(CAPTURA_PAGINA_WEB)

    (RAIZ_CAPTURAS / "respuestas_capturas.json").write_text(
        json.dumps(respuestas_capturas, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"Dataset generado en {RAIZ} (+ {RAIZ_CAPTURAS})")


if __name__ == "__main__":
    generar()
