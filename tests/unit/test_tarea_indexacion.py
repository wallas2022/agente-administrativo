"""Regresión (hallazgo local 14/10): el worker de indexación fallaba con
ModuleNotFoundError('curaduria') porque Celery quita el directorio de trabajo de sys.path al
terminar de cargar la app, y la tarea importaba curaduria de forma diferida. Además, una falla
inesperada dejaba la fuente en "indexando" para siempre."""

import os
import subprocess
import sys
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from comun.modelos import Area, FuenteConocimiento, Usuario
from curaduria.aprobacion import iniciar_indexacion, marcar_error_indexacion

RAIZ = Path(__file__).resolve().parents[2]


def test_el_modulo_de_tareas_carga_sus_dependencias_al_importarse() -> None:
    codigo = (
        "import sys\n"
        "import orquestador.tareas\n"
        "faltan = [m for m in ('curaduria.aprobacion', 'curaduria.indexacion', "
        "'rag.cliente_embeddings', 'comun.uso_llm', 'qdrant_client') if m not in sys.modules]\n"
        "assert not faltan, faltan\n"
    )
    separador = os.pathsep
    entorno = {
        "PYTHONPATH": f"{RAIZ / 'src'}{separador}{RAIZ / 'src' / 'orquestador'}",
        "API_SECRET_KEY": "x",
    }

    resultado = subprocess.run(
        [sys.executable, "-c", codigo],
        capture_output=True,
        text=True,
        env={**os.environ, **entorno},
        cwd=RAIZ,
        check=False,
    )

    assert resultado.returncode == 0, resultado.stderr


def _fuente_indexando(sesion) -> tuple[FuenteConocimiento, Usuario]:
    usuario = sesion.query(Usuario).first()
    area = sesion.get(Area, usuario.area_id)
    fuente = FuenteConocimiento(
        fuente_id="CONTIT-001",
        titulo="Redes",
        tipo="regla_interna",
        prioridad=1,
        version="1",
        vigente_desde=date(2026, 1, 1),
        estado="borrador",
        area_id=area.id,
        dueno="TI",
        archivo="a/CONTIT-001/1/x.pdf",
        cargado_por=usuario.id,
        fecha_carga=datetime.now(UTC),
    )
    sesion.add(fuente)
    sesion.commit()
    iniciar_indexacion(sesion, fuente, usuario_id=usuario.id)
    sesion.commit()
    return fuente, usuario


def test_marcar_error_indexacion_deja_motivo_y_bitacora(sesion_bd) -> None:
    fuente, usuario = _fuente_indexando(sesion_bd)

    resultado = marcar_error_indexacion(
        sesion_bd, fuente.id, usuario.id, ModuleNotFoundError("No module named 'curaduria'")
    )

    assert resultado.estado == "error_indexacion"
    sesion_bd.refresh(fuente)
    assert fuente.estado == "error_indexacion"
    assert "ModuleNotFoundError" in fuente.motivo_error


def test_marcar_error_indexacion_no_toca_una_fuente_que_ya_no_esta_indexando(sesion_bd) -> None:
    fuente, usuario = _fuente_indexando(sesion_bd)
    fuente.estado = "vigente"
    sesion_bd.commit()

    assert marcar_error_indexacion(sesion_bd, fuente.id, usuario.id, RuntimeError("x")) is None
    sesion_bd.refresh(fuente)
    assert fuente.estado == "vigente"


def test_si_la_tarea_falla_de_forma_inesperada_la_fuente_queda_en_error_indexacion(
    sesion_bd, monkeypatch: pytest.MonkeyPatch
) -> None:
    from orquestador import tareas

    fuente, usuario = _fuente_indexando(sesion_bd)
    fuente_pk = fuente.id

    def _explota(*_a, **_k):
        raise RuntimeError("falla inesperada del worker")

    monkeypatch.setattr(tareas, "obtener_fabrica_sesion", lambda: (lambda: sesion_bd))
    monkeypatch.setattr(tareas.almacenamiento, "obtener_cliente_s3", lambda: object())
    monkeypatch.setattr(tareas, "procesar_indexacion", _explota)

    with pytest.raises(RuntimeError, match="falla inesperada"):
        tareas.indexar_fuente_conocimiento.run(str(fuente.id), str(usuario.id))

    fila = sesion_bd.get(FuenteConocimiento, fuente_pk)
    assert fila.estado == "error_indexacion"
    assert "RuntimeError" in fila.motivo_error
