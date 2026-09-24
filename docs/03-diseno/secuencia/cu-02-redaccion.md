# Secuencia — CU-02 Revisar redacción PDF/Word

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/02-casos-de-uso.md#cu-02, RF-03,07,12,13,14

```mermaid
sequenceDiagram
    actor AN as Analista
    participant UI as ui
    participant API as api
    participant MN as minio
    participant PG as postgres
    participant RD as redis
    participant WK as worker/orquestador
    participant AR as Adaptador Redacción
    participant RAG as rag (qdrant)
    participant LLM as ollama

    AN->>UI: Cargar PDF/Word + tipo="redacción"
    UI->>API: POST /documentos
    API->>MN: Guardar binario original
    API->>PG: Crear documento + version_documento
    API->>RD: Encolar análisis
    API-->>UI: 202 Aceptado

    RD-->>WK: Desencolar tarea
    WK->>PG: analisis.estado = procesando
    WK->>AR: Ejecutar revisión de redacción
    AR->>RAG: Consultar guía de estilo vigente
    RAG-->>AR: Fragmento de la guía de estilo
    AR->>LLM: Prompt: evaluar tono/estructura vs. guía
    LLM-->>AR: Sugerencia de redacción + justificación
    AR-->>WK: Hallazgos (severidad, ubicación, explicación, corrección sugerida)
    WK->>PG: Guardar hallazgos (documento.estado = con_hallazgos)
    WK-->>API: Notificar análisis completo
    API-->>UI: Estado actualizado
    UI-->>AN: Mostrar sugerencias

    Note over AN,PG: Continúa en CU-07 (Aprobar o rechazar hallazgos)
```

## Elemento · responsabilidad · tecnología

| Elemento | Responsabilidad | Tecnología |
| --- | --- | --- |
| Adaptador Redacción | Evalúa tono, estructura y claridad contra la guía de estilo | Nodo LangGraph |
| rag (qdrant) | Recupera la guía de estilo vigente | Qdrant + bge-m3 |
| ollama | Genera la sugerencia de redacción en lenguaje natural | Ollama / llama.cpp (MoE) |
| postgres | Persiste hallazgos y estado del documento | PostgreSQL 16 |

## Supuestos

1. A diferencia de CU-01, aquí el LLM sí participa directamente en generar el contenido de la sugerencia (no es un cálculo numérico, RNF-03 no aplica).
2. Existe una guía de estilo cargada como fuente de conocimiento vigente; si no existe, `AR` devuelve hallazgos genéricos sin cita de fuente [POR CONFIRMAR comportamiento exacto].
3. Si el PDF es una imagen escaneada, el flujo se desvía primero a CU-06 (OCR, entrega 2) antes de llegar a este diagrama.
4. El documento corregido (RF-14) se genera solo tras la decisión del Revisor en CU-07, no en este diagrama.
5. Este flujo es representativo también de CU-03 (verificar normativa) y CU-04 (checklist), que siguen el mismo patrón cambiando el Adaptador y la fuente consultada (ver docs/01-requerimientos/02-casos-de-uso.md).
