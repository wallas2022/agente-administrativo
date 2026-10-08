"""Pruebas del pipeline CU-06 (fase 1/MVP): motor de OCR + publicación del
texto reconocido como nueva versión del documento."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import EstadoAnalisis, EstadoDocumento
from comun.modelos import (
    Analisis,
    Area,
    Base,
    Documento,
    Hallazgo,
    Rol,
    TipoRevision,
    Usuario,
    VersionDocumento,
)
from orquestador.pipeline_ocr import procesar_documento_ocr


def _sesion_con_documento_y_analisis(
    contenido: bytes, *, tipo_archivo: str
) -> tuple[Session, Analisis, VersionDocumento]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sesion = Session(engine)

    area = Area(nombre="Contabilidad")
    rol = Rol(nombre="analista")
    sesion.add_all([area, rol])
    sesion.flush()

    usuario = Usuario(nombre="Ana Lista", email="ana@ejemplo.gt", area_id=area.id, rol_id=rol.id)
    sesion.add(usuario)
    sesion.flush()

    documento = Documento(
        nombre_original="escaneo.png",
        tipo_archivo=tipo_archivo,
        tamano_bytes=len(contenido),
        area_id=area.id,
        usuario_carga_id=usuario.id,
        fecha_carga=datetime.now(UTC),
        fecha_expiracion=date.today() + timedelta(days=90),
        estado=EstadoDocumento.CARGADO.value,
    )
    tipo_revision = TipoRevision(nombre="ocr")
    sesion.add_all([documento, tipo_revision])
    sesion.flush()

    analisis = Analisis(
        documento_id=documento.id,
        tipo_revision_id=tipo_revision.id,
        usuario_id=usuario.id,
        fecha_inicio=datetime.now(UTC),
        estado=EstadoAnalisis.PROCESANDO.value,
    )
    sesion.add(analisis)
    sesion.flush()

    version = VersionDocumento(
        documento_id=documento.id,
        numero_version=1,
        ruta_almacenamiento=f"{area.id}/{documento.id}/escaneo.png",
        es_corregida=False,
        fecha_creacion=datetime.now(UTC),
    )
    sesion.add(version)
    sesion.commit()

    return sesion, analisis, version


def _png_bytes() -> bytes:
    import cv2
    import numpy as np

    imagen = np.full((30, 40, 3), 255, dtype=np.uint8)
    ok, buffer = cv2.imencode(".png", imagen)
    assert ok
    return buffer.tobytes()


def _datos_ocr_falsos(texto: str) -> dict[str, list[Any]]:
    return {
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [5],
        "top": [5],
        "width": [30],
        "height": [10],
        "conf": [90.0],
        "text": [texto],
    }


def test_procesar_documento_ocr_publica_una_nueva_version_con_el_texto() -> None:
    contenido = _png_bytes()
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="png")
    subidas: list[tuple[str, bytes]] = []

    hallazgos, paginas = procesar_documento_ocr(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="png",
        subir_version_texto=lambda llave, datos: subidas.append((llave, datos)),
        funcion_ocr=lambda _img: _datos_ocr_falsos("Texto reconocido"),
        funcion_osd=lambda _img: 0,
    )

    assert hallazgos == []
    assert len(paginas) == 1
    assert paginas[0].texto == "Texto reconocido"

    assert len(subidas) == 1
    llave, datos = subidas[0]
    assert llave == version.ruta_almacenamiento.rsplit(".", 1)[0] + ".ocr.txt"
    assert datos == b"Texto reconocido"

    nuevas_versiones = (
        sesion.query(VersionDocumento)
        .filter_by(documento_id=version.documento_id)
        .order_by(VersionDocumento.numero_version)
        .all()
    )
    assert len(nuevas_versiones) == 2
    assert nuevas_versiones[1].es_corregida is True
    assert nuevas_versiones[1].numero_version == 2
    assert nuevas_versiones[1].ruta_almacenamiento == llave


def test_procesar_documento_ocr_tipo_no_soportado_no_persiste_nada() -> None:
    contenido = b"no es ni imagen ni pdf"
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="xlsx")

    with pytest.raises(ValueError, match="no soportado"):
        procesar_documento_ocr(
            sesion,
            analisis=analisis,
            version_original=version,
            contenido_original=contenido,
            tipo_archivo="xlsx",
            subir_version_texto=lambda _llave, _datos: pytest.fail("no debía subir nada"),
        )

    assert sesion.query(VersionDocumento).filter_by(documento_id=version.documento_id).count() == 1


# --- Bloque 2: calidad sin inventar (RN-06) --------------------------------


def _datos_ocr_pagina_ilegible() -> dict[str, list[Any]]:
    return {
        "block_num": [1],
        "par_num": [1],
        "line_num": [1],
        "left": [5],
        "top": [5],
        "width": [30],
        "height": [10],
        "conf": [20.0],  # < OCR_PAGINA_ILEGIBLE (50 por defecto)
        "text": ["##!!garabato"],
    }


def test_pagina_ilegible_publica_aviso_en_vez_de_texto_y_hallazgo_de_documento() -> None:
    contenido = _png_bytes()
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="png")
    subidas: list[tuple[str, bytes]] = []

    hallazgos, paginas = procesar_documento_ocr(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="png",
        subir_version_texto=lambda llave, datos: subidas.append((llave, datos)),
        funcion_ocr=lambda _img: _datos_ocr_pagina_ilegible(),
        funcion_osd=lambda _img: 0,
    )

    assert len(paginas) == 1
    assert paginas[0].confianza_media < 50.0

    # Cero texto publicado para la página ilegible -- solo un aviso, nunca
    # el texto (poco confiable) que reconoció Tesseract (RN-06, PP-06).
    _llave, texto_publicado = subidas[0]
    assert b"ilegible" in texto_publicado
    assert b"garabato" not in texto_publicado

    assert len(hallazgos) == 1
    assert isinstance(hallazgos[0], Hallazgo)
    assert hallazgos[0].severidad == "alta"
    assert hallazgos[0].ubicacion == "Documento completo"
    assert "ilegible" in hallazgos[0].descripcion

    persistidos = sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).all()
    assert len(persistidos) == 1


def test_palabra_dudosa_se_persiste_como_hallazgo_individual() -> None:
    contenido = _png_bytes()
    sesion, analisis, version = _sesion_con_documento_y_analisis(contenido, tipo_archivo="png")

    def _datos_con_una_dudosa() -> dict[str, list[Any]]:
        return {
            "block_num": [1, 1],
            "par_num": [1, 1],
            "line_num": [1, 1],
            "left": [5, 40],
            "top": [5, 5],
            "width": [30, 30],
            "height": [10, 10],
            "conf": [95.0, 55.0],  # media 75 -- página legible, 2da palabra dudosa
            "text": ["Hola", "mllndo"],
        }

    hallazgos, _paginas = procesar_documento_ocr(
        sesion,
        analisis=analisis,
        version_original=version,
        contenido_original=contenido,
        tipo_archivo="png",
        subir_version_texto=lambda _llave, _datos: None,
        funcion_ocr=lambda _img: _datos_con_una_dudosa(),
        funcion_osd=lambda _img: 0,
    )

    assert len(hallazgos) == 1
    assert hallazgos[0].texto_original == "mllndo"
    assert hallazgos[0].ubicacion == "Página 1"
    assert hallazgos[0].severidad == "alta"  # nivel "dudosa" (confianza < OCR_CONF_DUDOSA=60)

    persistidos = sesion.query(Hallazgo).filter_by(analisis_id=analisis.id).all()
    assert len(persistidos) == 1
