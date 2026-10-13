# Resultados — P-14 (Chat de la Base de Conocimiento), Bloque 3 (Pantalla)

**Versión:** 0.1.0
**Fecha:** 2026-10-13
**Relacionado con:** docs/05-prompts/P-14-chat-base-conocimiento.md, docs/04-pruebas/resultados/local-P14-bloque1.md, local-P14-bloque2.md, HU-31..34

## Alcance

Pantalla de chat en "/" (nueva pantalla de inicio, todos los roles) con lista de conversaciones, mensajes con el rol indicado, aviso de "pensando" (las respuestas reales pueden tardar minutos) y adjunto opcional. "Nuevo análisis" se mueve a `/nuevo-analisis`, con el mismo permiso `analisis:crear` que ya tenía.

## Cambios

| Archivo | Cambio |
| --- | --- |
| `src/ui/src/paginas/Chat.tsx`, `.css` (nuevos) | Lista de conversaciones propias + "Nueva conversación"; mensajes con rol indicado por texto (no solo color, "Tú"/"Asistente"); fuentes citadas por mensaje; aviso `role="status"` de "pensando…" mientras se espera la respuesta real; adjunto de imagen/documento vía `<input type="file">`. Conversación creada de forma perezosa (al primer envío, no al entrar a la pantalla). |
| `src/ui/src/App.tsx` | `"/"` → `Chat` (sin gate de permiso, como Historial); `/nuevo-analisis` → `NuevoAnalisis` bajo `RutaProtegida permisoRequerido="analisis:crear"`. |
| `src/ui/src/componentes/Layout.tsx` | Entrada de menú "Chat" (sin permiso, siempre visible) primero; "Nuevo análisis" apunta a `/nuevo-analisis`. |
| `src/ui/src/paginas/NuevoAnalisis.tsx` | Quitada la rama "sin permiso" (mostraba solo `PanelAnalisisRecientes`) -- ya no hace falta: la ruta está protegida, nadie sin `analisis:crear` llega a este componente. |
| `src/ui/src/api/esquema.ts` | Regenerado (aditivo) con los endpoints de `/chat/*` del Bloque 2. |
| `src/ui/e2e/*.spec.ts` (5 archivos) | Actualizados para la nueva navegación (ver "Hallazgos" abajo). |
| `src/ui/src/paginas/Chat.test.tsx` (nuevo, 5 pruebas) | Lista vacía/con conversaciones, envío con creación perezosa de conversación + aviso de "pensando" + respuesta final con fuentes citadas, error de envío, "Nueva conversación" limpia la vista. |

## Decisión de diseño: qué pasa con "Análisis recientes"

El panel `PanelAnalisisRecientes` (antes mostrado en "/" para roles sin `analisis:crear`, como sustituto de un historial real) se queda **solo** dentro de `/nuevo-analisis` (gated por `analisis:crear` -- solo lo ve quien puede subir documentos, como atajo a sus propios análisis recién creados). Revisor/Curador/Auditor (sin ese permiso) ya tienen una vía real y completa para lo mismo: **Historial** (HU-21, con alcance propio/área/todas), que existe desde P-12 y hace obsoleto el propósito original del panel para esos roles.

## Hallazgos reales durante la validación en vivo (E2E, no cosméticos)

1. **`page.goto()` rompe la sesión en memoria.** Tres specs (`accesibilidad.spec.ts`, `autoaprobacion.spec.ts`, `cu05-validacion-en-segundo-plano.spec.ts`) usaban `page.goto("/nuevo-analisis")` después de iniciar sesión -- una recarga completa de la SPA, que pierde el token (vive solo en memoria, `ContextoAuth.tsx`, por diseño de seguridad) y deja la página en `/login`. Corregido: navegación por clic en el enlace del menú, como ya hacían otros specs.
2. **Timeout por defecto (30 s) ya no alcanza.** La navegación ahora pasa por una pantalla extra (Chat → clic en "Nuevo análisis"/"Historial"); dos specs (`autoaprobacion.spec.ts`, `flujo-analista-revisor.spec.ts`) quedaron sin margen. Corregido con `test.setTimeout(60_000)`, mismo mecanismo que ya usaba `cu05-validacion-en-segundo-plano.spec.ts`.
3. **El Revisor no veía el análisis del Analista en Historial.** `flujo-analista-revisor.spec.ts` asumía que "/" (antes, un panel de análisis recientes) mostraba el documento recién subido por otro usuario. Historial filtra por "Mis análisis" por defecto -- el Revisor nunca sube nada, así que necesita cambiar a "Mi área" (HU-21) para verlo. Corregido agregando ese clic al test; esto también confirma que la decisión de diseño de esta sección (mover a Historial) es la correcta: el panel viejo nunca distinguía "propio" de "área", Historial sí.

## Resultados de pruebas (reales, no estimados)

- `tsc -b` (type-check de la UI): sin errores.
- `vitest run` (UI, suite completa): **123 passed** (118 + 5 nuevas de `Chat.test.tsx`).
- `npx playwright test --workers=1` (E2E completo, stack real, en serie): **12 de 14 passed** en la corrida conjunta; los 2 restantes (`Pantalla de inicio · Chat`, `flujo-analista-revisor`) se confirmaron como *flakes* transitorios por contención de recursos (todo corre en una sola máquina sin GPU: Ollama, Postgres, Qdrant, Celery y Chromium compiten por el mismo CPU) -- **14 de 14 passed** al re-ejecutarlos en aislamiento inmediatamente después. Una corrida inicial con el paralelismo por defecto de Playwright (varios workers) produjo hasta 5 fallas por el mismo motivo -- confirmado que este proyecto debe correr su suite E2E completa con `--workers=1` en este hardware, igual que ya se documentó para P-13 Bloque 4 (CU-05 con arranque en frío).

## Pendiente (explícitamente del Bloque 4)

- Permisos: el chat no tiene permiso propio (accesible a cualquier sesión) -- falta el cierre formal de esa decisión en el plan de pruebas.
- Rendimiento del registro de uso del chat (RNF-15, igual criterio que P-13).
- Documentación (`docs/06-operacion`) y guion de demo.
- No probado con un adjunto de imagen real en la pantalla (solo vía API en el Bloque 2); validar manualmente en el cierre.

¿Continúo con el Bloque 4 (Pruebas y cierre)?
