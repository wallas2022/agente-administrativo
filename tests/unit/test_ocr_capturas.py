"""Pruebas de soporte para capturas de pantalla (CU-06, Bloque 2b): lectura/
escritura de DPI embebido, detección de fondo plano/texto disperso,
clasificación "es captura", y descarte de líneas basura. Todo con imágenes
sintéticas -- no requiere el binario de Tesseract."""

import cv2
import numpy as np

from ocr.capturas import (
    altura_media_linea,
    es_captura_de_pantalla,
    filtrar_lineas_basura,
    fondo_plano,
    insertar_dpi_png,
    leer_dpi,
    preprocesar_captura,
    texto_disperso,
)
from ocr.modelos import Linea, Palabra, ResultadoPagina


def _png_bytes(imagen: np.ndarray) -> bytes:
    ok, buffer = cv2.imencode(".png", imagen)
    assert ok
    return buffer.tobytes()


# --- leer_dpi / insertar_dpi_png --------------------------------------------


def test_leer_dpi_png_sin_chunk_phys_da_none() -> None:
    contenido = _png_bytes(np.full((20, 20, 3), 255, dtype=np.uint8))
    assert leer_dpi(contenido) is None


def test_insertar_dpi_png_y_releerlo_da_el_mismo_valor() -> None:
    contenido = _png_bytes(np.full((20, 20, 3), 255, dtype=np.uint8))
    con_dpi = insertar_dpi_png(contenido, 300)
    assert leer_dpi(con_dpi) == 300
    # Sigue siendo un PNG válido -- se puede volver a decodificar.
    decodificada = cv2.imdecode(np.frombuffer(con_dpi, dtype=np.uint8), cv2.IMREAD_COLOR)
    assert decodificada.shape == (20, 20, 3)


def test_leer_dpi_de_contenido_no_imagen_da_none() -> None:
    assert leer_dpi(b"esto no es ni png ni jpeg") is None


# --- fondo_plano / texto_disperso -------------------------------------------


def test_fondo_plano_detecta_fondo_perfectamente_uniforme() -> None:
    imagen = np.full((100, 200, 3), 255, dtype=np.uint8)
    cv2.putText(imagen, "Menu", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    assert fondo_plano(imagen) is True


def test_fondo_plano_no_se_activa_con_ruido_de_escaneo() -> None:
    rng = np.random.default_rng(3)
    imagen = np.full((100, 200, 3), 255, dtype=np.uint8)
    cv2.putText(imagen, "Factura", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    ruido = rng.normal(0, 12, imagen.shape).astype(np.int16)
    imagen = np.clip(imagen.astype(np.int16) + ruido, 0, 255).astype(np.uint8)
    assert fondo_plano(imagen) is False


def test_texto_disperso_con_contenido_concentrado_en_poco_espacio() -> None:
    imagen = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(imagen, (10, 10), (60, 25), 255, -1)
    assert texto_disperso(imagen) is True


def test_texto_disperso_falso_si_el_contenido_llena_el_lienzo() -> None:
    imagen = np.zeros((300, 300), dtype=np.uint8)
    cv2.rectangle(imagen, (0, 0), (300, 300), 255, -1)
    assert texto_disperso(imagen) is False


def test_texto_disperso_sin_contenido_da_true() -> None:
    assert texto_disperso(np.zeros((50, 50), dtype=np.uint8)) is True


# --- es_captura_de_pantalla --------------------------------------------------


def _imagen_cualquiera() -> np.ndarray:
    imagen = np.full((100, 200, 3), 255, dtype=np.uint8)
    cv2.putText(imagen, "Hola", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    return imagen


def test_es_captura_sin_dpi_es_true() -> None:
    assert es_captura_de_pantalla(dpi=None, imagen=_imagen_cualquiera()) is True


def test_es_captura_con_dpi_bajo_es_true() -> None:
    assert es_captura_de_pantalla(dpi=96, imagen=_imagen_cualquiera()) is True
    assert es_captura_de_pantalla(dpi=72, imagen=_imagen_cualquiera()) is True


def test_es_captura_con_dpi_alto_y_fondo_con_textura_es_false() -> None:
    rng = np.random.default_rng(5)
    imagen = np.full((100, 200, 3), 255, dtype=np.uint8)
    cv2.putText(imagen, "Factura", (10, 50), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2)
    ruido = rng.normal(0, 12, imagen.shape).astype(np.int16)
    imagen = np.clip(imagen.astype(np.int16) + ruido, 0, 255).astype(np.uint8)
    assert es_captura_de_pantalla(dpi=300, imagen=imagen) is False


def test_es_captura_con_dpi_alto_pero_fondo_plano_es_true() -> None:
    # DPI alto no basta si el fondo es perfectamente uniforme (UI real).
    assert es_captura_de_pantalla(dpi=300, imagen=_imagen_cualquiera()) is True


# --- preprocesar_captura -----------------------------------------------------


def test_preprocesar_captura_escala_x3_y_devuelve_un_canal() -> None:
    imagen = _imagen_cualquiera()
    resultado = preprocesar_captura(imagen)
    assert resultado.shape == (300, 600)  # x3 en cada eje, un solo canal


# --- altura_media_linea / filtrar_lineas_basura -----------------------------


def _pagina_con_lineas(lineas: list[Linea]) -> ResultadoPagina:
    palabras = tuple(p for linea in lineas for p in linea.palabras)
    confianza = sum(p.confianza for p in palabras) / len(palabras) if palabras else 0.0
    return ResultadoPagina(
        numero=1,
        ancho_px=100,
        alto_px=100,
        lineas=tuple(lineas),
        palabras=palabras,
        confianza_media=confianza,
    )


def _palabra(texto: str, confianza: float, alto: int = 20) -> Palabra:
    return Palabra(texto=texto, izquierda=0, arriba=0, ancho=10, alto=alto, confianza=confianza)


def test_altura_media_linea_promedia_la_palabra_mas_alta_de_cada_linea() -> None:
    linea1 = Linea(
        texto="Hola Mundo",
        palabras=(_palabra("Hola", 90, alto=10), _palabra("Mundo", 90, alto=20)),
    )
    linea2 = Linea(texto="Chau", palabras=(_palabra("Chau", 90, alto=30),))
    pagina = _pagina_con_lineas([linea1, linea2])
    assert altura_media_linea(pagina) == 25.0  # (20 + 30) / 2


def test_altura_media_linea_sin_palabras_da_cero() -> None:
    assert altura_media_linea(_pagina_con_lineas([])) == 0.0


def test_filtrar_lineas_basura_descarta_linea_con_pocos_alfanumericos() -> None:
    buena = Linea(texto="Hola mundo", palabras=(_palabra("Hola", 90), _palabra("mundo", 90)))
    basura = Linea(texto="--", palabras=(_palabra("--", 90),))
    pagina = _pagina_con_lineas([buena, basura])

    filtrada = filtrar_lineas_basura(pagina, umbral_confianza=60.0)

    assert filtrada.lineas == (buena,)
    assert filtrada.palabras == buena.palabras


def test_filtrar_lineas_basura_descarta_linea_de_confianza_baja() -> None:
    buena = Linea(texto="Hola mundo", palabras=(_palabra("Hola", 90), _palabra("mundo", 90)))
    dudosa = Linea(texto="xyzabc", palabras=(_palabra("xyzabc", 40),))
    pagina = _pagina_con_lineas([buena, dudosa])

    filtrada = filtrar_lineas_basura(pagina, umbral_confianza=60.0)

    assert filtrada.lineas == (buena,)


def test_filtrar_lineas_basura_recalcula_la_confianza_media() -> None:
    buena = Linea(texto="Hola mundo", palabras=(_palabra("Hola", 80), _palabra("mundo", 100)))
    basura = Linea(texto="##", palabras=(_palabra("##", 10),))
    pagina = _pagina_con_lineas([buena, basura])

    filtrada = filtrar_lineas_basura(pagina, umbral_confianza=60.0)

    assert filtrada.confianza_media == 90.0  # (80 + 100) / 2, sin la basura
