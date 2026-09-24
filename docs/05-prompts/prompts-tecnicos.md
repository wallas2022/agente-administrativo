# Prompts técnicos

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/03-diseno/c4/03-componentes-orquestador.md (Cliente LLM), RNF-06, RNF-11

> Estado: esqueleto. El texto exacto de cada prompt es trabajo de implementación (ingeniería de prompts) pendiente; este documento fija la estructura y el punto de versionado exigido por RNF-06 (cada hallazgo guarda la versión del prompt usado).

## Convención de versionado

Cada prompt se identifica como `<adaptador>.v<N>` (p. ej. `redaccion.v1`). El `analisis.version_prompt` (ver docs/03-diseno/er/modelo-datos.md) referencia este identificador. Un cambio de contenido del prompt exige incrementar `N`; nunca se sobrescribe un prompt ya usado en análisis históricos (trazabilidad, RNF-06).

## Prompts por adaptador (entrega 1)

| Adaptador | Prompt | Entrada | Salida esperada | Estado |
| --- | --- | --- | --- | --- |
| Redacción (CU-02) | `redaccion.v1` | Párrafo/sección + fragmento de guía de estilo (RAG) | Sugerencia de redacción + justificación breve | [POR CONFIRMAR] texto exacto |
| Normativa (CU-03, iteración 2) | `normativa.v1` | Referencia normativa del documento + fragmento de fuente vigente (RAG) | Indicación de desactualización + cita | [POR CONFIRMAR] texto exacto |

Los adaptadores Contable (CU-01) y Ortografía (CU-05) de la entrega 1 **no usan el LLM para generar cifras ni para decidir errores ortográficos** (RNF-03; el cálculo es determinista y la ortografía la resuelve LanguageTool/Hunspell). El LLM puede usarse ahí únicamente para redactar la explicación en lenguaje natural de un hallazgo ya determinado por código, si se decide incorporarlo [POR CONFIRMAR alcance].

## Principios (aplican a todo prompt)

1. El prompt nunca debe pedirle al modelo que calcule o invente cifras (RNF-03); las cifras se inyectan ya calculadas por código.
2. Todo prompt que genere una afirmación de hallazgo debe exigir cita de fuente (fragmento RAG) en la salida, para cumplir RF-12.
3. El idioma de entrada y salida es español (es-GT).
4. Cada prompt se traza en Langfuse (perfil `observabilidad`) con su identificador de versión.

## Pendientes

- Texto exacto de cada prompt — [POR CONFIRMAR], pendiente de ingeniería de prompts e iteración con el modelo aprobado en ADR-001.
- Formato de salida estructurada (JSON schema) esperado del LLM para cada adaptador — [POR CONFIRMAR].
- Prompts de los adaptadores de entrega 2 (Control, OCR) — se agregan cuando se implementen esos casos de uso.
