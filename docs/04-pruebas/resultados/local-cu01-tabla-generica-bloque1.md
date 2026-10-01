# Resultados — CU-01 "leer cualquier tabla", Bloque 1 (detector de tabla)

**Versión:** 0.1.0
**Fecha:** 2026-10-01
**Relacionado con:** src/parsers/excel.py, src/validadores/contable/reglas.py (sin cambios, contrato preservado), docs/04-pruebas/casos-prueba/PP-01.md

## Alcance

`leer_libro_contable` detecta la tabla de partidas por encabezado (sinónimos de columna) en vez de asumir una plantilla fija de una sola fila/orden. Recorre todas las hojas del archivo. No incluye todavía la pantalla de mapeo de columnas para casos de baja confianza (Bloque 2).

## Resultados

| Ruta | Cambio | Prueba | Resultado |
| --- | --- | --- | --- |
| `src/parsers/excel.py` | Detección de encabezado por sinónimos (Debe/Haber/Cuenta/Descripción/Fecha/Asiento), filas de título en celdas combinadas ignoradas, fila de totales detectada por texto en cualquier columna, códigos de cuenta normalizados a texto, moneda desde columna dedicada o marca "(Q)"/"($)" en el encabezado o "Q" por defecto, recorrido de todas las hojas | `tests/unit/test_parser_excel.py` (8 casos, 6 nuevos) | 8/8 ✓ |
| — | Regresión: no debía romper el formato fijo existente | `test_parser_excel.py` (2 originales) + `test_pp01_deteccion_contable.py` + `test_validador_contable.py` + `test_pipeline_contable.py` | 36/36 ✓ sin cambios |
| — | Verificación contra un archivo real sin convertir a mano | `test_lee_el_libro_diario_real_sin_convertirlo_a_mano` (nuevo, usa `Libro_Diario_Ejercicio_Contable_con_Errores.xlsx`) | 1/1 ✓ — 9 partidas, moneda "Q", RN-01 detecta el descuadre de Q 10,000.00 en el Asiento 3, igual que la "leyenda de errores" del propio archivo |
| Suite completa | — | `pytest tests/unit -q` | 289/289 ✓; ruff/mypy limpios |

## Hallazgos de este bloque

1. **El archivo real del usuario (`Libro_Diario_Ejercicio_Contable_con_Errores.xlsx`) ya no necesita convertirse a mano.** Antes de este bloque, alguien tenía que reescribirlo al formato fijo (ver `Libro_Diario_Mayo2026_formato_agente.xlsx`, la versión convertida a mano que ya existía). El detector nuevo lo lee directamente: título en celda combinada (fila 1), fila en blanco (fila 2), encabezado en fila 3 con nombres y orden distintos ("Código de Cuenta", "Cuenta / Concepto", sin columna Moneda), código de cuenta como número (1101.0 → "1101"), fila de totales ("SUMA TOTAL") en la columna de descripción, no en la A.
2. **La detección de totales por columna arbitraria era necesaria de verdad**, no solo teórica: en el archivo real, "SUMA TOTAL" aparece en la 4ta columna (la de descripción), no en la primera — el código anterior (que solo miraba la columna A) nunca la habría encontrado.
3. **Ambigüedad "cuenta" resuelta con una señal fuerte/débil**: "Código de Cuenta" (código) y "Cuenta / Concepto" (nombre) ambas contienen el token "cuenta" — se resolvió dando prioridad a "código" como señal fuerte para el rol de código de cuenta, dejando "cuenta" sola como respaldo débil solo si ninguna columna ya trae "código". Documentado como heurística en el propio código.

## Pendiente

- Pantalla de mapeo de columnas para confianza baja (Bloque 2 de la tarea).
- Cuadre por partida/fecha-consecutivo cuando no hay columna de asiento reconocible explícita más allá del fallback ya existente (Bloque 3).
- Revisión "operación vs cuenta" con LLM (Bloque 4).
- Dataset `Test01-Partidas.xlsx` con hoja de respuestas y tests de encabezado en fila 1 y en fila 14 (Bloque 5).
