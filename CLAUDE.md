# Instrucciones para Claude Code — Agente Administrativo

## Idioma (obligatorio)
- Responde SIEMPRE en español (Guatemala) en el chat, resúmenes, preguntas y reportes, aunque las herramientas, errores o logs estén en inglés.
- Documentación en `docs/` y mensajes de commit: en español.
- Código: identificadores de forma consistente (el proyecto ya usa español en dominio: hallazgo, regla, documento).

## Contexto
- Fuente de verdad: `docs/00-rol-y-lineamientos.md` y `docs/01-requerimientos/01-requerimiento-formal.md`. Referencia por ID (RF, RNF, RN, CU, HU, PP), no copies contenido.
- Ambiente actual: local (Windows + WSL2 + Docker Desktop; Ollama nativo de Windows). Stage/servidor pendiente (ADR-005): no configurar stage.
- Diagramas: solo Mermaid.

## Forma de trabajar
- Por bloques; al terminar cada uno: tabla ruta · cambio · pruebas · métricas y registrar el resumen en `docs/04-pruebas/resultados/`.
- TDD, Conventional Commits, sin secretos en Git, no inventar cifras ([POR CONFIRMAR] o "aprox.").
- Cambios de stack o de modelo LLM respecto a lo documentado: detente y propón un ADR antes de aplicarlos.
