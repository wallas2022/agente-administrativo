# kb/ — Base de conocimiento controlada

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF [POR CONFIRMAR] (RAG), docs/03-diseno/flujos/ingesta-conocimiento.md

## Propósito

Contenido curado que el agente usa como fuente de verdad para validar y corregir documentos: normativa/fuentes originales, glosario de términos y reglas de negocio parametrizadas. Carga y mantenimiento a cargo del rol **Curador de conocimiento** (por área), con segregación: quien carga no aprueba (ver [docs/03-diseno/seguridad/roles-permisos.md](../docs/03-diseno/seguridad/roles-permisos.md)).

## Estructura

- `fuentes/` — documentos normativos originales (PDF/Word) que respaldan reglas y glosario.
- `glosario/` — términos y definiciones en tabla CSV.
- `reglas/` — reglas de negocio parametrizadas en tabla CSV, referenciadas por ID `RN-xx` (ver [docs/02-analisis/02-reglas-de-negocio.md](../docs/02-analisis/02-reglas-de-negocio.md)).

Sin lógica de negocio implementada: solo estructura y plantillas.
