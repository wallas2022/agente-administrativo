"""PP-01: recall de detección de errores contables ≥ 90 % sobre el dataset de
CU-01 (docs/04-pruebas/casos-prueba/PP-01.md). Corre el parser + validador
reales contra los 10 documentos generados por tests/dataset/generar_cu01.py.
"""

from pathlib import Path

import pytest

from parsers.excel import leer_libro_contable
from validadores.contable.reglas import validar_libro_contable

RAIZ_DATASET = Path(__file__).resolve().parents[1] / "dataset" / "cu-01"
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


def _codigos_detectados(nombre_archivo: str) -> set[str]:
    ruta = RAIZ_DATASET / nombre_archivo
    libro = leer_libro_contable(str(ruta))
    hallazgos = validar_libro_contable(libro, catalogo=CATALOGO, periodo=PERIODO)
    return {h.regla_codigo for h in hallazgos}


@pytest.mark.skipif(not RAIZ_DATASET.exists(), reason="dataset no generado")
@pytest.mark.parametrize("nombre_archivo", sorted(CODIGOS_ESPERADOS))
def test_documento_dispara_exactamente_los_codigos_esperados(nombre_archivo: str) -> None:
    detectados = _codigos_detectados(nombre_archivo)
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
        detectados = _codigos_detectados(nombre_archivo)
        total_esperados += len(esperados)
        total_detectados_correctamente += len(esperados & detectados)

    recall = 1.0 if total_esperados == 0 else total_detectados_correctamente / total_esperados
    assert recall >= 0.90, f"Recall {recall:.2%} por debajo del umbral de PP-01 (≥ 90 %)"
