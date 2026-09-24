# ADR-001 — Motor de inferencia LLM en CPU (Ollama/llama.cpp, modelos MoE)

**Versión:** 1.0
**Fecha:** 2026-09-24
**Relacionado con:** RNF-04, RNF-05, RNF-10, RNF-14, R-02, docs/01-requerimientos/01-requerimiento-formal.md §9

## Estado

Aceptado (para la primera entrega; revisión prevista en fase 2 con GPU).

## Contexto

El servidor físico de stage tiene 2 CPU, 384–512 GB de RAM y **sin GPU** en la primera entrega (SRS §7); la PC de desarrollo local (Intel Core Ultra 7, 128 GB RAM) tampoco tiene GPU dedicada. El sistema necesita un motor de inferencia LLM que:
1. Corra completamente on-premise, sin salida a internet (RNF-01).
2. Ofrezca calidad de razonamiento/redacción aceptable ejecutando solo en CPU.
3. Permita cambiar de modelo sin modificar código (RNF-10) y evolucionar a GPU en fase 2 sin rediseño (RNF-14).

## Decisión

Se usa **Ollama / llama.cpp** como motor de inferencia, con **modelos MoE (Mixture of Experts)** — `gpt-oss-120b` y `gpt-oss-20b`, `Qwen3-30B-A3B` — por activar solo una fracción de sus parámetros por token, lo que los hace más viables en CPU que un modelo denso equivalente. Configuración por ambiente (ver docs/03-diseno/despliegue/estrategia-ambientes.md):
- Local: `gpt-oss-20b` / `Qwen3-30B-A3B` para el día a día; `gpt-oss-120b` solo para pruebas puntuales de calidad.
- Stage: modelo objetivo aprobado tras la comparación de PP-01/PP-03/PP-07/PP-12 (ver docs/04-pruebas/plan-pruebas-prototipo.md §3).

El modelo se selecciona por variable de entorno (`LLM_MODEL_PRINCIPAL`), nunca hardcodeado, para permitir el cambio sin tocar código.

## Alternativas consideradas

| Alternativa | Por qué se descarta (para la primera entrega) |
| --- | --- |
| vLLM | Optimizado para GPU; sin GPU no aporta ventaja sobre llama.cpp y tiene mayor huella operativa. Queda reservado para fase 2 (`infra/compose.gpu.yml`, `LLM_PROVIDER=vllm`). |
| Modelos densos más pequeños (Llama 3.x 8B, Mistral, Gemma) | Menor calidad de razonamiento esperada para tareas de validación contable/normativa; se mantienen como alternativa de respaldo (ver stack tecnológico, SRS §9). |
| Servicio LLM en la nube (API de terceros) | Contradice RNF-01 (sin salida a internet) y el requisito de privacidad de documentos institucionales. |

## Consecuencias

- El rendimiento medido en local **no es representativo** (RNF-04 se valida solo en stage); ver R-02.
- Se requiere memoria RAM considerable dedicada a `ollama` (ver límites en `infra/compose.local.yml` y `infra/compose.stage.yml`).
- Todo cálculo numérico (cuadre contable, totales) se implementa en código determinista, **no** se delega al LLM (RNF-03) — el LLM se usa para razonamiento textual y redacción, no aritmética.
- La migración a GPU en fase 2 se limita a cambiar `LLM_PROVIDER`, `LLM_BASE_URL` y activar `infra/compose.gpu.yml`, sin tocar el código de negocio (ver docs/06-operacion/despliegue-stage-proxmox.md §11).
- Pendiente: registrar en este ADR el modelo finalmente aprobado para stage tras la comparación de PP-01/03/07/12 [POR CONFIRMAR].
