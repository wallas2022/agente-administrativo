"""Soporte para capturas de pantalla (CU-06, Bloque 2b): son texto nítido
y antialiased, no papel escaneado -- necesitan preprocesado y umbral de
detección distintos del resto del motor.

Sin librerías nuevas (ADR-007 solo cubre Tesseract/OpenCV/PyMuPDF): la
lectura/escritura de DPI se hace con `struct` puro sobre los chunks PNG
(`pHYs`) y segmentos JPEG (JFIF `APP0`), no con Pillow.
"""

from __future__ import annotations

import struct
from dataclasses import replace

import cv2
import numpy as np

from ocr.modelos import ResultadoPagina

ALTURA_MINIMA_LINEA_CAPTURA = 15.0
DPI_MAXIMO_CAPTURA = 96


def _escala_grises(imagen: np.ndarray) -> np.ndarray:
    if imagen.ndim == 2:
        return imagen
    return cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)


# --- DPI embebido (PNG pHYs / JPEG JFIF) ------------------------------------


def _dpi_png(contenido: bytes) -> int | None:
    indice = 8
    while indice + 8 <= len(contenido):
        longitud = int.from_bytes(contenido[indice : indice + 4], "big")
        tipo = contenido[indice + 4 : indice + 8]
        datos = contenido[indice + 8 : indice + 8 + longitud]
        if tipo == b"pHYs" and len(datos) == 9:
            ppu_x, _ppu_y, unidad = struct.unpack(">IIB", datos)
            return round(ppu_x * 0.0254) if unidad == 1 else None
        if tipo == b"IDAT":
            return None  # pHYs, si existe, siempre va antes de IDAT
        indice += 8 + longitud + 4  # tipo+datos + CRC
    return None


def _dpi_jpeg(contenido: bytes) -> int | None:
    indice = 2
    while indice + 4 <= len(contenido) and contenido[indice] == 0xFF:
        marcador = contenido[indice + 1]
        if marcador in (0xD8, 0xD9) or 0xD0 <= marcador <= 0xD7:
            indice += 2
            continue
        longitud = int.from_bytes(contenido[indice + 2 : indice + 4], "big")
        if marcador == 0xE0:  # APP0 (JFIF)
            segmento = contenido[indice + 4 : indice + 2 + longitud]
            if segmento[:5] == b"JFIF\x00" and len(segmento) >= 9:
                unidad = segmento[7]
                densidad_x = int.from_bytes(segmento[8:10], "big")
                if unidad == 1:
                    return densidad_x
                if unidad == 2:
                    return round(densidad_x * 2.54)
            return None
        indice += 2 + longitud
    return None


def leer_dpi(contenido: bytes) -> int | None:
    """DPI embebido en los metadatos del archivo, si lo hay. `None` cuando
    el archivo no lo declara -- una captura de pantalla típica (herramienta
    de recorte, impresión de pantalla) no lleva esta información."""
    if contenido.startswith(b"\x89PNG\r\n\x1a\n"):
        return _dpi_png(contenido)
    if contenido.startswith(b"\xff\xd8"):
        return _dpi_jpeg(contenido)
    return None


def insertar_dpi_png(contenido: bytes, dpi: int) -> bytes:
    """Inserta un chunk `pHYs` (300 DPI, p. ej.) justo después de `IHDR` --
    solo para generar datasets de prueba que simulen un documento escaneado
    de verdad (con DPI), sin depender de Pillow."""
    longitud_ihdr = int.from_bytes(contenido[8:12], "big")
    fin_ihdr = 8 + 8 + longitud_ihdr + 4  # firma + (longitud+tipo) + datos + CRC
    ppu = round(dpi / 0.0254)
    datos_phys = struct.pack(">IIB", ppu, ppu, 1)
    chunk = (
        struct.pack(">I", len(datos_phys))
        + b"pHYs"
        + datos_phys
        + struct.pack(">I", _crc32(b"pHYs" + datos_phys))
    )
    return contenido[:fin_ihdr] + chunk + contenido[fin_ihdr:]


def _crc32(datos: bytes) -> int:
    import zlib

    return zlib.crc32(datos) & 0xFFFFFFFF


# --- Heurísticas de clasificación -------------------------------------------


def fondo_plano(imagen: np.ndarray, *, umbral_desviacion: float = 2.0) -> bool:
    """Una captura de pantalla real tiene un fondo de color sólido (interfaz
    de usuario); papel escaneado, incluso limpio, tiene una textura/ruido
    mínimo. Se mide la desviación estándar de los píxeles de fondo, lejos
    del texto -- la máscara de Otsu se dilata antes de invertirla porque el
    halo de antialiasing alrededor de las letras (grises intermedios, ni
    fondo ni texto) si no se excluye contamina la muestra de "fondo" con
    variación que no es del fondo real (encontrado al probar con texto
    renderizado: sin dilatar, un fondo perfectamente uniforme medía
    desviación ~6 en vez de 0)."""
    gris = _escala_grises(imagen)
    _, mascara_texto = cv2.threshold(gris, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)
    mascara_dilatada = cv2.dilate(mascara_texto, np.ones((5, 5), np.uint8), iterations=2)
    fondo = gris[mascara_dilatada == 0]
    if fondo.size == 0:
        return False
    return float(np.std(fondo)) < umbral_desviacion


def texto_disperso(imagen_binaria: np.ndarray) -> bool:
    """True si el contenido ocupa solo una porción chica del lienzo (texto
    de interfaz esparcido entre iconos/espacios vacíos) -- decide `--psm 11`
    vs. `--psm 3` en `ocr.motor.procesar_imagen_captura`."""
    coordenadas = cv2.findNonZero(imagen_binaria)
    if coordenadas is None:
        return True
    _x, _y, ancho, alto = cv2.boundingRect(coordenadas)
    area_total = imagen_binaria.shape[0] * imagen_binaria.shape[1]
    if area_total == 0:
        return True
    cobertura = (ancho * alto) / area_total
    return cobertura < 0.5


def es_captura_de_pantalla(*, dpi: int | None, imagen: np.ndarray) -> bool:
    """RF-11 (Bloque 2b): sin DPI o DPI bajo (típico de una herramienta de
    captura) o fondo perfectamente uniforme (interfaz real, no papel)."""
    if dpi is None or dpi <= DPI_MAXIMO_CAPTURA:
        return True
    return fondo_plano(imagen)


# --- Preprocesado y limpieza específicos de capturas ------------------------


def preprocesar_captura(imagen: np.ndarray) -> np.ndarray:
    """Escala x3 (el texto de interfaz suele ser muy chico en píxeles
    reales) con interpolación cúbica, escala de grises y un enfoque suave
    (unsharp mask) -- sin binarización adaptativa ni reducción de ruido: el
    texto ya es nítido y antialiased, no tiene el ruido de un escaneo
    (mismo espíritu que el hallazgo del deskew en el Bloque 4: preprocesar
    de más daña más de lo que ayuda cuando la imagen ya es buena)."""
    gris = _escala_grises(imagen)
    escalada = cv2.resize(gris, None, fx=3.0, fy=3.0, interpolation=cv2.INTER_CUBIC)
    desenfocada = cv2.GaussianBlur(escalada, (0, 0), sigmaX=1.0)
    return cv2.addWeighted(escalada, 1.5, desenfocada, -0.5, 0)


def elegir_psm(imagen_preprocesada: np.ndarray) -> int:
    """`--psm 11` (texto disperso) si el contenido ocupa poco del lienzo
    (interfaz con iconos/espacios), si no `--psm 3` (automático, el mismo
    que ya usa el resto del motor por defecto)."""
    _, binaria = cv2.threshold(
        imagen_preprocesada, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU
    )
    return 11 if texto_disperso(binaria) else 3


def altura_media_linea(resultado: ResultadoPagina) -> float:
    """Promedio de la palabra más alta de cada línea -- una página con
    letra consistentemente chica (< `ALTURA_MINIMA_LINEA_CAPTURA`) sugiere
    una captura de pantalla que no se detectó por DPI/fondo (p. ej. una
    captura con textura de fondo no del todo plana)."""
    alturas = [
        max((palabra.alto for palabra in linea.palabras), default=0) for linea in resultado.lineas
    ]
    alturas_validas = [a for a in alturas if a > 0]
    return sum(alturas_validas) / len(alturas_validas) if alturas_validas else 0.0


def filtrar_lineas_basura(
    resultado: ResultadoPagina, *, umbral_confianza: float
) -> ResultadoPagina:
    """Descarta líneas con menos de 3 caracteres alfanuméricos o confianza
    media por debajo de `umbral_confianza` (`OCR_CONF_DUDOSA`) -- ruido
    típico de capturas (bordes de ventana, iconos) que Tesseract confunde
    con texto. Nunca inventa ni corrige: solo quita lo que ya es basura."""
    lineas_buenas = []
    palabras_buenas: list = []
    for linea in resultado.lineas:
        alfanumericos = sum(1 for c in linea.texto if c.isalnum())
        confianza_linea = (
            sum(p.confianza for p in linea.palabras) / len(linea.palabras)
            if linea.palabras
            else 0.0
        )
        if alfanumericos < 3 or confianza_linea < umbral_confianza:
            continue
        lineas_buenas.append(linea)
        palabras_buenas.extend(linea.palabras)

    confianza_media = (
        sum(p.confianza for p in palabras_buenas) / len(palabras_buenas) if palabras_buenas else 0.0
    )
    return replace(
        resultado,
        lineas=tuple(lineas_buenas),
        palabras=tuple(palabras_buenas),
        confianza_media=confianza_media,
    )
