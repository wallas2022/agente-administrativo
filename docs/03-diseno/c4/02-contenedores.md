# C4 — Nivel 2: Contenedores

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md §9 (stack), infra/compose.yml, docs/03-diseno/c4/01-contexto.md

```mermaid
C4Container
    title Diagrama de contenedores — Agente Administrativo

    Person(usuario, "Usuario (Analista/Revisor/Curador/Admin/Auditor)", "Ver docs/03-diseno/c4/01-contexto.md")
    System_Ext(ad, "Active Directory / LDAP")
    System_Ext(pbs, "Proxmox Backup Server")

    Container_Boundary(agente, "Agente Administrativo") {
        Container(proxy, "proxy", "Traefik", "Único punto de entrada; TLS; enruta a api/grafana/langfuse")
        Container(ui, "ui", "Open WebUI (piloto) / UI propia (React)", "Carga, resultados, revisión")
        Container(api, "api", "FastAPI (Python 3.12)", "Expone endpoints REST: carga, estado, revisión, bitácora")
        Container(orquestador, "orquestador", "LangGraph", "Orquesta el flujo de análisis como grafo de estados")
        Container(worker, "worker", "Celery (≥ 2 réplicas)", "Ejecuta tareas de análisis en paralelo (RNF-05)")
        ContainerDb(redis, "redis", "Redis", "Cola de trabajos y caché de sesión")
        Container(ollama, "ollama", "Ollama / llama.cpp", "Inferencia LLM local (MoE, CPU)")
        ContainerDb(qdrant, "qdrant", "Qdrant", "Base vectorial — fragmentos de conocimiento (RAG)")
        ContainerDb(postgres, "postgres", "PostgreSQL 16", "Usuarios, documentos, análisis, hallazgos, bitácora")
        ContainerDb(minio, "minio", "MinIO", "Documentos originales y corregidos")
        Container(languagetool, "languagetool", "LanguageTool + Hunspell", "Motor de ortografía y gramática es-GT")
        Container(prometheus, "prometheus", "Prometheus", "Métricas de los servicios")
        Container(grafana, "grafana", "Grafana", "Dashboards de monitoreo")
        Container(langfuse, "langfuse", "Langfuse (perfil observabilidad)", "Trazas de prompts y respuestas del LLM")
        ContainerDb(langfuse_postgres, "langfuse_postgres", "PostgreSQL 16", "Base de datos propia de Langfuse")
    }

    Rel(usuario, proxy, "HTTPS")
    Rel(proxy, ui, "enruta")
    Rel(proxy, api, "enruta")
    Rel(proxy, grafana, "enruta")
    Rel(proxy, langfuse, "enruta (perfil observabilidad)")
    Rel(ui, api, "REST/JSON")
    Rel(api, redis, "encola tareas")
    Rel(api, postgres, "lee/escribe")
    Rel(api, minio, "sube/descarga documentos")
    Rel(api, ad, "autentica", "LDAP")
    Rel(worker, redis, "consume tareas")
    Rel(worker, orquestador, "ejecuta análisis")
    Rel(orquestador, ollama, "prompts / completions")
    Rel(orquestador, qdrant, "consulta fragmentos (RAG)")
    Rel(orquestador, languagetool, "revisión ortográfica")
    Rel(orquestador, postgres, "registra hallazgos y bitácora")
    Rel(orquestador, langfuse, "traza de prompts (perfil observabilidad)")
    Rel(prometheus, api, "scrape /metrics")
    Rel(prometheus, orquestador, "scrape /metrics")
    Rel(grafana, prometheus, "consulta métricas")
    Rel(langfuse, langfuse_postgres, "lee/escribe")
    Rel_Back(pbs, postgres, "respaldo diario", "snapshot VM")
```

## Elemento · responsabilidad · tecnología

| Elemento | Responsabilidad | Tecnología |
| --- | --- | --- |
| proxy | Único punto de entrada con TLS; único puerto publicado en stage | Traefik |
| ui | Carga de documentos, visualización de hallazgos, revisión | Open WebUI (piloto) → UI propia (React) |
| api | Contrato REST del sistema; autenticación; encola trabajo | FastAPI |
| orquestador | Grafo de estados del análisis: clasifica, invoca validadores, consulta RAG | LangGraph |
| worker | Ejecución paralela de análisis (≥ 2 réplicas en stage, RNF-05) | Celery |
| redis | Cola de trabajos y caché de sesión | Redis |
| ollama | Inferencia del modelo LLM (MoE) en CPU | Ollama / llama.cpp |
| qdrant | Búsqueda semántica de fragmentos de conocimiento | Qdrant + bge-m3 |
| postgres | Datos transaccionales: usuarios, documentos, análisis, hallazgos, bitácora | PostgreSQL 16 |
| minio | Almacenamiento de documentos originales/corregidos | MinIO |
| languagetool | Corrección ortográfica y gramatical es-GT | LanguageTool + Hunspell |
| prometheus / grafana | Métricas y dashboards de monitoreo | Prometheus / Grafana |
| langfuse / langfuse_postgres | Trazabilidad de prompts (RNF-06, RNF-11), BD propia | Langfuse (self-hosted) / PostgreSQL 16 |

## Supuestos

1. `worker` y `orquestador` son procesos separados en el diagrama pero comparten la misma imagen (`agente-admin/orquestador`), ver infra/compose.yml.
2. Solo `proxy` publica puerto en stage (443); el resto vive en la red interna `red_interna` (ver infra/compose.stage.yml).
3. `langfuse` y `prometheus`/`grafana` están bajo el perfil `observabilidad`; en local es opcional, en stage se asume activo salvo indicación contraria.
4. El modelo LLM cargado en `ollama` difiere por ambiente (pequeño en local, objetivo en stage) — ver docs/03-diseno/despliegue/estrategia-ambientes.md.
5. La UI definitiva (React) reemplaza a Open WebUI cuando el piloto avance; ambas hablan el mismo contrato REST de `api` [POR CONFIRMAR fecha de transición].
