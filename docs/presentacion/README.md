# Presentación a directivos — Agente Administrativo

**Versión:** 0.1.0 · **Fecha:** 2026-10-15
**Estado:** propuesta aprobada en lo general; el PowerPoint se genera cuando haya cifras de capacidad medidas en stage.

## Contenido de la carpeta

| Ruta | Qué es |
| --- | --- |
| `recursos/logo-servicios-compartidos.jpg` | Logo entregado para la portada y los pies de diapositiva |
| `capturas/` | Capturas reales de la interfaz local (1440×900 a 1.5×), generadas con `src/ui/scripts/capturas-presentacion.mjs` |

## Decisiones tomadas

1. Capturas reales del ambiente local (no las pantallas ilustrativas del manual).
2. Demo en vivo: ortografía y chat en vivo; Excel contable iniciado al abrir la diapositiva (los hallazgos de las reglas llegan en segundos y las explicaciones de la IA después); video corto como plan B. Idealmente sobre stage.
3. Detalle técnico mínimo, a nivel directivo; el resto en un anexo.
4. La diapositiva de capacidad se cierra con cifras medidas con usuarios simultáneos en stage (`tests/carga/README.md`).

## Capturas

`01` inicio de sesión · `02`/`03` chat con respuesta y fuentes citadas (POL-001) · `04` nuevo análisis · `05` hallazgos de Excel contable · `06` hallazgos de ortografía · `07` historial · `08` base de conocimiento · `09` dashboard de consumo · `11` configuración · `12` bitácora.

Falta la pantalla de **Recursos** del dashboard: en local Prometheus está apagado ("métricas no disponibles"); se captura en stage.

## Regenerar las capturas

Con el stack local levantado y los usuarios semilla:

```bash
cd src/ui
node scripts/capturas-presentacion.mjs                 # todas (el chat tarda unos minutos)
SOLO=admin node scripts/capturas-presentacion.mjs      # solo el panel de administración
SOLO=chat PREGUNTA_CHAT="..." node scripts/capturas-presentacion.mjs
```

La sesión vive solo en memoria: el script navega dentro de la aplicación (no recarga la página).
