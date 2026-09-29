# tests/integration/

**Versión:** 0.2.0
**Fecha:** 2026-09-29
**Relacionado con:** docs/04-pruebas/plan-pruebas-prototipo.md

Pruebas de integración de extremo a extremo (carga → análisis → revisión → aprobación) contra los servicios declarados en `infra/compose.yml`, con el stack local levantado. Todas se saltan automáticamente (`pytest.mark.skipif`) si los servicios que necesitan (LanguageTool, Ollama, Qdrant) no están arriba.

- `test_cu05_pp03_pp04.py`: PP-03 (recall/falsos positivos) y PP-04 (preservación de formato) de CU-05, contra LanguageTool y Ollama reales — mide también el umbral RNF-04 (≤ 5 min/documento, SRS v0.8).
- `test_pp14_modo_offline.py`: PP-14 adaptado al ambiente local (Bloque K6) — confirma que CU-01 (RN-02), CU-05 y la ingesta de conocimiento (Bloque K3) no necesitan resolver ningún host fuera de loopback.

Correr desde el host (no dentro de un contenedor — la imagen de `api` no incluye pytest) necesita apuntar los clientes a los puertos publicados en `infra/compose.local.yml`, por ejemplo:
```bash
LANGUAGETOOL_HOST=127.0.0.1 LLM_BASE_URL=http://127.0.0.1:11434 \
    .venv/Scripts/python.exe -m pytest tests/integration/ -v --no-cov
```

En L2 se verificó manualmente (no como test reproducible) que `worker` consume la cola real (Redis) y transiciona `documento`/`analisis`/`bitacora` en el Postgres real del stack local — ver docs/04-pruebas/resultados/local-L2.md. Formalizar esa verificación como prueba de pytest queda pendiente.
