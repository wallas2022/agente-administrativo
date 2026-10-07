# P-10 · CU-11 · Revisar estructura de hojas de cálculo

Versión 1.0 · 2026-10-07 · Base: docs/02-analisis/03-analisis-cu11-estructura-hojas-calculo.md

## Prompt

```xml
<tarea>Implementa CU-11 "Revisar estructura" según docs/02-analisis/03-analisis-cu11-estructura-hojas-calculo.md (cópialo al repo si no existe). Responde en español. Detente al final de cada bloque.</tarea>

<contexto>Detectar descuadres de columnas en cualquier hoja SIN depender del nombre de encabezados ni de fórmulas: perfil por contenido (D1), estructura (D2–D6), relaciones/dependencias/atípicos/fórmulas (D7–D10), conciliación (D11), perfil de referencia (D12). Reutiliza de CU-01: parser openpyxl, marcado de Excel, cola, bitácora, CU-07. Todo cálculo por código (RNF-03); LLM solo explica, en segundo plano (patrón CU-05/ADR-008, sin cambiar modelo). Sin librerías nuevas salvo ADR. Asigna los siguientes IDs libres a RF/HU/PP/R provisionales del análisis y actualiza SRS, casos de uso y matriz.</contexto>

<bloque id="1" nombre="Documentación y dataset">
Registra CU-11 en SRS, 02-casos-de-uso, HU (Gherkin del análisis), matriz y plan de pruebas; diagramas en Mermaid dentro de docs/03-diseno.
tests/dataset/cu-11/ generado por script (semilla fija, sin datos reales): 12 archivos con un error sembrado por detector + 2 combinados + 5 limpios + variantes con encabezados renombrados/vacíos/inglés + par para conciliación. Hoja de respuestas JSON (detector, hoja, rango, evidencia esperada). Escribe primero las pruebas (fallan).
</bloque>

<bloque id="2" nombre="Lector y perfilador (D1)">
src/estructura/: lectura streaming (read_only), detección de tabla y fila de encabezado, tipo y "forma" por celda, rol dominante ≥0.80 con confianza, sinónimos de encabezado solo como pista (glosario). Muestreo estratificado para perfil si >50k filas. Persistencia PERFIL_COLUMNA (migración Alembic). Endpoint para que el usuario confirme/corrija roles y re-ejecute.
</bloque>

<bloque id="3" nombre="Estructura y formato (D2–D6)">
Celda fuera de perfil, corrimiento de fila (≥3 celdas encajan en columna vecina ±1/±2), cambio de estructura por bloque (ventana deslizante), encabezado/subtotal intercalado (excluir esas filas de los demás detectores), formatos mixtos (número-texto, fechas, decimal, Q/$). Cada hallazgo: detector, severidad, confianza, hoja, rango, evidencia, sugerencia concreta.
</bloque>

<bloque id="4" nombre="Relaciones y atípicos (D7–D10)">
Relaciones candidatas solo entre columnas numéricas (A±B, A×B, A/B, saldo acumulado) con tope configurable de combinaciones; aceptar si se cumplen en ≥95 % de filas con n≥30 y tolerancia de redondeo; reportar filas que fallan con diferencia. Dependencias código→nombre 1:1, unicidad, orden de fechas. Atípicos con mediana±k·MAD por grupo (detecta ×10/×100). Fórmula inconsistente vía notación R1C1 o valor fijo entre fórmulas.
</bloque>

<bloque id="5" nombre="Conciliación y perfil de referencia (D11–D12)">
Emparejar columnas de dos tablas por contenido (solapamiento de valores y distribución), proponer llave, comparar faltantes y diferencias; el usuario puede ajustar el emparejamiento. PERFIL_REFERENCIA con huella de estructura, versión y aprobación del curador; comparar deriva (columnas faltantes, orden, rango de valores).
</bloque>

<bloque id="6" nombre="Salida e interfaz">
Opción "Revisar estructura" en Nuevo análisis (uno o dos archivos). Vista "Perfil de columnas" (rol, confianza, editable), lista de hallazgos agrupada por detector con filtro por severidad, Excel marcado (color por detector + comentario), JSON, enviar a CU-07. Explicación LLM en segundo plano: una llamada por hoja, texto plano, solo con la evidencia del detector. CU-01: si no encuentra columnas contables, usar D1 para proponer el mapeo automáticamente. CU-06: activar el botón "Revisar estructura" en tablas OCR.
</bloque>

<bloque id="7" nombre="Pruebas y métricas">
PP-21 recall ≥90 %, PP-22 FP ≤10 %, PP-23 encabezados alterados ±5 %, PP-24 conciliación 100 %, PP-25 10k×30 ≤60 s sin LLM, PP-26 cifras 100 % por código. Resultados en docs/04-pruebas/resultados/, actualiza estado-proyecto y demo-guion.
</bloque>

<reglas>TDD. Un commit por bloque (Conventional Commits) y push. Sin secretos ni datos reales. Umbrales en configuración, no en código. No mostrar archivos completos en el chat.</reglas>
<salida_en_chat>Por bloque: tabla ruta · cambio · prueba (ok/falla) · métrica · "¿Continúo con &lt;siguiente&gt;?".</salida_en_chat>
```
