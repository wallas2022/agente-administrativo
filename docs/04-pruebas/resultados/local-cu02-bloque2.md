# Resultados — CU-02 "Mejorar redacción", Bloque 2 (Resultado y elección)

**Versión:** 0.1.0
**Fecha:** 2026-10-01
**Relacionado con:** docs/04-pruebas/resultados/local-cu02-bloque1.md (motor de fase 2, 2 opciones de estilo), docs/01-requerimientos/01-requerimiento-formal.md (RF-07, RF-12, RNF-03)

## Alcance

Pantalla de resultado para un análisis de redacción: por párrafo, tarjetas "Original" + "Sin cambio (formato corregido)" + una por cada opción aprobada (Formal/Breve) con sus motivos, radio-button para elegir o editar a mano; selector global "Usar \<estilo\> en todo"; vista "Texto final" con botón Copiar; interruptor "Ver cambios" (resalta por palabra lo que cambió respecto al original); hallazgos de estilo (EST-001, fase 1) listados aparte con el componente ya existente. Cada elección queda en bitácora vía el endpoint de decisión ya existente (`POST /hallazgos/{id}/decision`), reutilizando su campo `comentario` para registrar qué se eligió -- no fue necesario agregar un endpoint ni una columna nueva.

No incluye el conversor de salida .txt/.docx/.xlsx (Bloque 3) ni el dataset con hoja de respuestas (Bloque 4).

## Backend

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `src/api/main.py` | El evento SSE `parrafo` ahora incluye `hallazgo_id` (se hace `flush()` tras persistir el `Hallazgo` para tener su id antes de armar el evento) -- la pantalla lo necesita para poder mandar la decisión del usuario al hallazgo correcto | `test_api_mejorar_redaccion_stream.py` (aserción nueva: `hallazgo_id` coincide con el id real persistido) |

```
tests/unit (suite completa): 303 passed in 67.96s
ruff check src tests / mypy src: sin hallazgos
```

## Frontend

| Ruta | Cambio | Prueba |
| --- | --- | --- |
| `src/ui/src/utils/diffPalabras.ts` (nuevo) | Diff por palabra (LCS) para el interruptor "Ver cambios" -- sin agregar una librería de diff nueva | `diffPalabras.test.ts` (4 casos, nuevo) |
| `src/ui/src/paginas/ResultadoRedaccion.tsx` (nuevo) | Pantalla completa del Bloque 2: consume el stream SSE directo (ya no lo hace `Hallazgos.tsx`), arma por párrafo las tarjetas de opciones, selector global, "Texto final" + Copiar, "Ver cambios", y la lista de hallazgos de estilo (filtrando los de fase 2 por los mismos prefijos de descripción que usa la idempotencia del backend) | `ResultadoRedaccion.test.tsx` (3 casos, nuevo) |
| `src/ui/src/paginas/Hallazgos.tsx` | Simplificado a despachador: si `tipo_revision === "redaccion"`, delega en `ResultadoRedaccion`; se quitó de acá toda la lógica de disparo del stream (se movió a la pantalla nueva) | `Hallazgos.test.tsx` (reescrito, 2 casos: delega vs. no delega) |

```
npx vitest run: 50 passed in 11.90s (10 archivos)
npx tsc --noEmit: sin errores
npm run lint (oxlint): sin hallazgos nuevos (2 warnings preexistentes, no relacionados)
```

## Decisiones de diseño

1. **Elegir una opción guarda en bitácora de inmediato** (no hay un botón "Guardar" aparte): al hacer click en un radio button, se llama `POST /hallazgos/{hallazgo_id}/decision` con `resultado="aceptado"` y `comentario` describiendo la elección ("Opción elegida: Formal", "Editado manualmente: ...", "Se conservó el párrafo con el formato corregido"). Si el usuario no tiene permiso para decidir (Analista, no Revisor/Administrador -- mismo criterio de segregación de funciones que CU-01/CU-05), la selección sigue funcionando para armar el "Texto final" en el navegador, pero no se intenta la llamada al backend (que la rechazaría con 403 de todas formas).
2. **El "Texto final" se arma en el navegador**, no se vuelve a pedir al servidor -- cada párrafo ya tiene en memoria su original, su "párrafo base" (formato corregido) y sus opciones (vía el propio evento SSE), así que no hace falta una ruta nueva solo para ensamblar el documento final. El Bloque 3 (conversor de salida) podrá recibir estos mismos párrafos ya elegidos directamente en el cuerpo de la petición de descarga, sin tener que releerlos de la base de datos.
3. **Sin columna ni endpoint nuevos para "qué opción se eligió"**: se reutiliza `SolicitudDecision.comentario` (ya existente, campo de texto libre) en vez de agregar un campo estructurado -- evita una migración para algo que, en esta primera versión, solo necesita quedar legible en la bitácora, no ser consultado por código.

## Pendiente

- Conversor de salida .txt/.docx/.xlsx (Bloque 3) -- incluye decidir cómo recibe los párrafos elegidos desde el frontend.
- Dataset `tests/dataset/cu-02/` con hoja de respuestas y pruebas de tiempos (Bloque 4).
- Curar EST-001 como fuente vigente (pendiente heredado de bloques anteriores).
- Verificación manual en el navegador (Playwright o a mano) del flujo completo elegir-opción -> Ver cambios -> Copiar -- este bloque se verificó con pruebas unitarias (Vitest + Testing Library) y build Docker real de la API, no con una corrida end-to-end en el navegador real.
