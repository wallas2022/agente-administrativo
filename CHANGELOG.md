# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.
Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/) y este proyecto usa [Versionado Semántico](https://semver.org/lang/es/).
Relacionado con: [docs/00-rol-y-lineamientos.md](docs/00-rol-y-lineamientos.md)

## [Sin publicar]

Sin cambios pendientes de registrar.

## [1.0.0] - 2026-09-24

### Agregado
- F5 (pruebas y operación): 17 casos de prueba individuales `docs/04-pruebas/casos-prueba/PP-01.md` a `PP-19.md` (entrega 1, 6 marcados bloqueantes para la salida del piloto); `tests/dataset/README.md` (30 documentos, 5 complejos, 2 cercanos a 1 GB, hojas de respuesta, línea base de tiempo manual); `docs/06-operacion/instalacion.md`, `respaldo-y-recuperacion.md` (RPO 24 h / RTO 4 h / PBS / retención 90 días), `monitoreo.md` (alerta de disco al 70 %, tiempos por documento).
- `docs/05-prompts/prompts-tecnicos.md` y `docs/03-diseno/despliegue/opcion-nube.md` (fuera de los bloques A/F3/F4/F5, agregados para dejar en 0 los enlaces rotos del repositorio al cierre de F5).

### Verificado
- Enlaces rotos en todo el repositorio (fuera de `docs/_archivo/`, snapshot congelado): **0**.
- `docker compose config` válido para local, stage y stage+gpu.

## [0.7.0] - 2026-09-24

### Agregado
- F4 (diseño, solo Mermaid): `docs/03-diseno/c4/` (contexto, contenedores, componentes del orquestador), `docs/03-diseno/er/modelo-datos.md` (15 entidades, montos con moneda, `fecha_expiracion` para retención), `docs/03-diseno/secuencia/` (CU-01, CU-02, CU-05, CU-07), `docs/03-diseno/estados/estados-analisis.md`, `docs/03-diseno/flujos/` (ingesta de conocimiento, pipeline de validación), `docs/03-diseno/seguridad/roles-permisos.md` (matriz rol × acción), `docs/03-diseno/adr/ADR-001-motor-llm-cpu.md`, `ADR-002-base-vectorial.md`, `ADR-003-orquestacion-agente.md`.
- Los 11 diagramas Mermaid del bloque se validaron renderizándolos con `@mermaid-js/mermaid-cli` (sin errores de sintaxis).

## [0.6.0] - 2026-09-24

### Agregado
- F3 (análisis): `docs/02-analisis/02-reglas-de-negocio.md` (RN-01 a RN-09: cuadre debe/haber, cuentas vs. catálogo, período, duplicados, mezcla de moneda sin tipo de cambio, ortografía con glosario, segregación de funciones, retención 90 días, tamaño máx. 1 GB); `docs/02-analisis/01-analisis-inicial.md` (esqueleto — sin archivo fuente disponible para su contenido real).

### Cambiado
- `docs/02-analisis/03-riesgos.md`: R-07 actualizado a la redacción v0.6 del SRS (capacidad de disco, probabilidad/impacto revisados).
- `docs/01-requerimientos/04-matriz-trazabilidad.md`: agrega columna RN.

## [0.5.0] - 2026-09-24

### Cambiado
- **Integración del SRS v0.6** (reemplaza v0.5): antecedentes cuantitativos (~1,000 documentos/mes, área SFC/Contabilidad), fecha de acceso a stage (28-oct-2026), PC local confirmada (Intel Core Ultra 7, 128 GB RAM, SSD), tamaño máximo de archivo (1 GB) y retención (3 meses), RF-11 (OCR) marcado iteración 2, entrega 1 = CU-01/CU-02/CU-05.
- `02-casos-de-uso.md`: agrega columna/etiqueta "Entrega" (1 o 2) por caso de uso.
- `03-historias-de-usuario.md`: **renumerado a HU-01..14** para coincidir exactamente con las referencias del plan de pruebas v0.2.
- `04-matriz-trazabilidad.md`: agrega columna PP con las 19 pruebas reales del plan (antes `[F5]`), columna Entrega, y tabla de RNF/OE con PP directa.
- `docs/03-diseno/despliegue/estrategia-ambientes.md` y `docs/06-operacion/despliegue-stage-proxmox.md` actualizados a v1.2 (specs de PC local con modelo de CPU y fecha de acceso a stage).
- `docs/00-rol-y-lineamientos.md`: tabla de roles alineada a la redacción del SRS (Analista carga y ejecuta; Curador aprueba fuentes de su área; Revisor ≠ quien cargó).
- `infra/compose.stage.yml`: `worker` con 2 réplicas (antes 1, `[POR CONFIRMAR]`) por RNF-05.
- `infra/compose.yml` + overlays: Langfuse implementado con base de datos propia (`langfuse_postgres`), bajo el perfil `observabilidad` (desactivado por defecto), en vez de quedar completamente comentado.
- `infra/proxmox/vm-spec.md`: agrega sección "PC de desarrollo (ambiente local)"; corrige referencia rota a `onprem-proxmox.md`.
- `.env.example`, `.env.local.example`, `.env.stage.example`: `DOCUMENTO_TAMANO_MAX_MB=1024`, `DOCUMENTO_RETENCION_DIAS=90`; variables de Langfuse self-hosted (`LANGFUSE_POSTGRES_*`, `LANGFUSE_NEXTAUTH_SECRET`, `LANGFUSE_SALT`) en vez de `LANGFUSE_PUBLIC_KEY`/`LANGFUSE_SECRET_KEY`.

### Agregado
- `docs/04-pruebas/plan-pruebas-prototipo.md`: plan de pruebas v0.2 con PP-01 a PP-19.
- `docs/_archivo/fuente-2026-09-24/`: snapshot de los archivos fuente ya integrados (antes `docs/_fuente-proyecto/`).

## [0.4.0] - 2026-09-24

### Cambiado
- **Integración del SRS v0.5** (fuente de verdad del proyecto, autor Rene Rosales) en `docs/01-requerimientos/`: reemplaza el requerimiento formal generado en 0.2.0 con la versión autoritativa (OE-01..07, RG-01..08, RF-01..20 redefinidos, RNF-01..14, CU-01..10, R-01..10). `02-casos-de-uso.md`, `03-historias-de-usuario.md` (HU-01..12) y `04-matriz-trazabilidad.md` reescritos para alinearse; RF en `src/*/README.md` actualizados a la nueva numeración.
- `docs/03-diseno/despliegue/estrategia-ambientes.md` y `docs/06-operacion/despliegue-stage-proxmox.md` actualizados a v1.1 (specs de PC local confirmadas: 128 GB RAM sin GPU; sección de evolución a GPU fase 2).
- `.env.local.example` / `infra/compose.local.yml`: modelo local y límites de Ollama ajustados a la RAM local confirmada (128 GB, WSL2 con 96 GB asignados).

### Agregado
- `docs/02-analisis/03-riesgos.md`: registro completo de riesgos R-01 a R-10.
- `infra/compose.gpu.yml`: esqueleto de soporte GPU (fase 2, servicio `vllm` bajo perfil `gpu` desactivado por defecto).
- Sección "Brechas detectadas en el SRS" en la matriz de trazabilidad (RF sin RG asociado, RG-04 sin OE asociado).

## [0.3.0] - 2026-09-24

### Agregado
- Estrategia de ambientes local/stage/producción: `infra/compose.yml` (base) + `infra/compose.local.yml` + `infra/compose.stage.yml`, `.env.local.example`, `.env.stage.example`, scripts `infra/scripts/{levantar-local,empaquetar-offline,cargar-en-stage}.sh`, `docs/03-diseno/despliegue/estrategia-ambientes.md`, `docs/06-operacion/despliegue-stage-proxmox.md` y `docs/03-diseno/adr/ADR-004-ambientes-local-stage.md`.
- Sección "Desarrollo local" y "Despliegue en stage" en README raíz.

### Corregido
- Ajustes de F1 previos a F2: `infra/docker-compose.yml` (proxy/traefik, worker/celery, red interna, healthchecks, límites de recursos, Redis con contraseña, Langfuse pospuesto a fase 2), `infra/proxmox/vm-spec.md` (CPU host, NUMA 2 sockets, RAM fija, disco SSD), `kb/reglas/reglas.csv` (columnas `version`, `estado`, `moneda`), RF reales en `src/*/README.md`, ID `PP` renombrado a "Prueba de prototipo" en `docs/00-rol-y-lineamientos.md`.

## [0.2.0] - 2026-09-24

### Agregado
- F2: requerimientos completos en `docs/01-requerimientos/` (requerimiento formal, casos de uso CU-01 a CU-07, historias de usuario HU-01 a HU-12 con criterios Gherkin, matriz de trazabilidad OE→RG→RF→CU→HU→PP).

## [0.1.0] - 2026-09-24

### Agregado
- F1: esqueleto de carpetas, convenciones del proyecto, `.env.example` y `docker-compose.yml` con servicios declarados.
