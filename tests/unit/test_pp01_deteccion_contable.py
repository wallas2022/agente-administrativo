"""PP-01: recall de detección de errores contables ≥ 90 % sobre el dataset de
CU-01 (docs/04-pruebas/casos-prueba/PP-01.md). Corre el parser + validador
reales contra los 10 documentos generados por tests/dataset/generar_cu01.py.
"""

from pathlib import Path

import pytest

from parsers.excel import leer_libro_contable
from validadores.contable.reglas import validar_libro_contable

RAIZ_DATASET = Path(__file__).resolve().parents[1] / "dataset" / "cu-01"
RAIZ_ESCENARIOS_USUARIO = Path(__file__).resolve().parents[1] / "dataset" / "escenarios-usuario"
CATALOGO = {
    "1010", "1020", "1030", "1040", "1050", "1210", "1220", "2010", "2020", "2030",
    "2040", "3010", "3020", "4010", "4020", "5010", "5020", "5030", "5040", "5050",
}
PERIODO = (2026, 1)

# Códigos de regla que cada documento debería disparar (ver tests/dataset/cu-01/respuestas/).
CODIGOS_ESPERADOS: dict[str, set[str]] = {
    "cu01-01-limpio.xlsx": set(),
    "cu01-02-descuadre.xlsx": {"RN-01"},
    "cu01-03-cuenta-inexistente.xlsx": {"RN-02"},
    "cu01-04-formula-reemplazada.xlsx": {"RN-FORMULA"},
    "cu01-05-fecha-fuera-periodo.xlsx": {"RN-03"},
    "cu01-06-duplicado.xlsx": {"RN-04"},
    "cu01-07-mezcla-moneda.xlsx": {"RN-05"},
    "cu01-08-multiples-errores.xlsx": {"RN-01", "RN-02"},
    "cu01-09-limpio-grande.xlsx": set(),
    "cu01-10-multiples-errores-2.xlsx": {"RN-03", "RN-04", "RN-05"},
}


def _codigos_detectados(ruta: Path, *, periodo: tuple[int, int] = PERIODO) -> set[str]:
    libro = leer_libro_contable(str(ruta))
    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=periodo)
    return {h.regla_codigo for h in hallazgos}


@pytest.mark.skipif(not RAIZ_DATASET.exists(), reason="dataset no generado")
@pytest.mark.parametrize("nombre_archivo", sorted(CODIGOS_ESPERADOS))
def test_documento_dispara_exactamente_los_codigos_esperados(nombre_archivo: str) -> None:
    detectados = _codigos_detectados(RAIZ_DATASET / nombre_archivo)
    esperados = CODIGOS_ESPERADOS[nombre_archivo]

    faltantes = esperados - detectados
    inesperados = detectados - esperados

    assert not faltantes, f"{nombre_archivo}: no se detectaron {faltantes}"
    assert not inesperados, (
        f"{nombre_archivo}: hallazgos inesperados {inesperados} (falso positivo)"
    )


@pytest.mark.skipif(not RAIZ_DATASET.exists(), reason="dataset no generado")
def test_pp01_recall_global_es_al_menos_90_por_ciento() -> None:
    total_esperados = 0
    total_detectados_correctamente = 0

    for nombre_archivo, esperados in CODIGOS_ESPERADOS.items():
        detectados = _codigos_detectados(RAIZ_DATASET / nombre_archivo)
        total_esperados += len(esperados)
        total_detectados_correctamente += len(esperados & detectados)

    recall = 1.0 if total_esperados == 0 else total_detectados_correctamente / total_esperados
    assert recall >= 0.90, f"Recall {recall:.2%} por debajo del umbral de PP-01 (≥ 90 %)"


# Escenario real de un usuario (no sintético): PP-01 aplicado también contra
# datos reales, no solo el dataset generado. La hoja de respuestas del propio
# usuario (Respuestas_Escenario_Descuadre_Agosto_2026.xlsx) confirma estas 6
# reglas como las esperadas (E1-E6); el período de cierre es 2026-08, no
# 2026-01 como el resto del dataset sintético.
ARCHIVO_ESCENARIO_USUARIO = "Escenario_Descuadre_Cierre_Agosto_2026.xlsx"
PERIODO_ESCENARIO_USUARIO = (2026, 8)
CODIGOS_ESPERADOS_ESCENARIO_USUARIO = {
    "RN-01", "RN-02", "RN-03", "RN-04", "RN-05", "RN-FORMULA",
}


@pytest.mark.skipif(
    not (RAIZ_ESCENARIOS_USUARIO / ARCHIVO_ESCENARIO_USUARIO).exists(),
    reason="escenario de usuario no disponible",
)
def test_escenario_usuario_descuadre_dispara_las_6_reglas_esperadas() -> None:
    detectados = _codigos_detectados(
        RAIZ_ESCENARIOS_USUARIO / ARCHIVO_ESCENARIO_USUARIO, periodo=PERIODO_ESCENARIO_USUARIO
    )

    faltantes = CODIGOS_ESPERADOS_ESCENARIO_USUARIO - detectados
    inesperados = detectados - CODIGOS_ESPERADOS_ESCENARIO_USUARIO

    assert not faltantes, f"no se detectaron {faltantes}"
    assert not inesperados, f"hallazgos inesperados {inesperados} (falso positivo)"


@pytest.mark.skipif(
    not (RAIZ_ESCENARIOS_USUARIO / ARCHIVO_ESCENARIO_USUARIO).exists(),
    reason="escenario de usuario no disponible",
)
def test_escenario_usuario_rn01_por_asiento_senala_exactamente_el_asiento_0811() -> None:
    """La hoja de respuestas del usuario (E1) señala la fila 28 (asiento
    0811) como la causa exacta del descuadre -- confirma que el cuadre por
    asiento (columna "Asiento" agregada a este archivo) apunta al mismo
    lugar que el análisis manual del usuario, no solo a la fila de totales.
    """
    ruta = RAIZ_ESCENARIOS_USUARIO / ARCHIVO_ESCENARIO_USUARIO
    libro = leer_libro_contable(str(ruta))
    hallazgos = validar_libro_contable(
        libro, catalogo=CATALOGO, periodo=PERIODO_ESCENARIO_USUARIO
    )

    rn01_por_asiento = [
        h for h in hallazgos if h.regla_codigo == "RN-01" and "asiento" in h.descripcion.lower()
    ]

    assert {h.ubicacion for h in rn01_por_asiento} == {"Partidas!A28"}
