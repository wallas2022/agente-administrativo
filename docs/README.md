# Documentación — Agente Administrativo

**Versión:** 1.0.0
**Fecha:** 2026-09-24
**Relacionado con:** N/A (índice documental)

Punto de entrada a toda la documentación del proyecto. Leer primero [00-rol-y-lineamientos.md](00-rol-y-lineamientos.md).

## 00 — Rol y lineamientos
- [00-rol-y-lineamientos.md](00-rol-y-lineamientos.md) — gobierno documental, IDs, convenciones.

## 01 — Requerimientos
- [01-requerimiento-formal.md](01-requerimientos/01-requerimiento-formal.md)
- [02-casos-de-uso.md](01-requerimientos/02-casos-de-uso.md)
- [03-historias-de-usuario.md](01-requerimientos/03-historias-de-usuario.md)
- [04-matriz-trazabilidad.md](01-requerimientos/04-matriz-trazabilidad.md)

## 02 — Análisis
- [01-analisis-inicial.md](02-analisis/01-analisis-inicial.md)
- [02-reglas-de-negocio.md](02-analisis/02-reglas-de-negocio.md)
- [03-riesgos.md](02-analisis/03-riesgos.md)

## 03 — Diseño
- C4: [01-contexto.md](03-diseno/c4/01-contexto.md) · [02-contenedores.md](03-diseno/c4/02-contenedores.md) · [03-componentes-orquestador.md](03-diseno/c4/03-componentes-orquestador.md)
- Modelo de datos: [er/modelo-datos.md](03-diseno/er/modelo-datos.md)
- Secuencia: [cu-01-excel-contable.md](03-diseno/secuencia/cu-01-excel-contable.md) · [cu-02-redaccion.md](03-diseno/secuencia/cu-02-redaccion.md) · [cu-05-ortografia.md](03-diseno/secuencia/cu-05-ortografia.md) · [cu-07-aprobacion.md](03-diseno/secuencia/cu-07-aprobacion.md)
- Estados: [estados-analisis.md](03-diseno/estados/estados-analisis.md)
- Flujos: [ingesta-conocimiento.md](03-diseno/flujos/ingesta-conocimiento.md) · [pipeline-validacion.md](03-diseno/flujos/pipeline-validacion.md)
- Despliegue: [estrategia-ambientes.md](03-diseno/despliegue/estrategia-ambientes.md) · [opcion-nube.md](03-diseno/despliegue/opcion-nube.md)
- Seguridad: [roles-permisos.md](03-diseno/seguridad/roles-permisos.md)
- ADR: [ADR-001-motor-llm-cpu.md](03-diseno/adr/ADR-001-motor-llm-cpu.md) · [ADR-002-base-vectorial.md](03-diseno/adr/ADR-002-base-vectorial.md) · [ADR-003-orquestacion-agente.md](03-diseno/adr/ADR-003-orquestacion-agente.md) · [ADR-004-ambientes-local-stage.md](03-diseno/adr/ADR-004-ambientes-local-stage.md)

## 04 — Pruebas
- [plan-pruebas-prototipo.md](04-pruebas/plan-pruebas-prototipo.md)
- [casos-prueba/](04-pruebas/casos-prueba/)

## 05 — Prompts
- [prompts-tecnicos.md](05-prompts/prompts-tecnicos.md)

## 06 — Operación
- [instalacion.md](06-operacion/instalacion.md)
- [despliegue-stage-proxmox.md](06-operacion/despliegue-stage-proxmox.md)
- [respaldo-y-recuperacion.md](06-operacion/respaldo-y-recuperacion.md)
- [monitoreo.md](06-operacion/monitoreo.md)

## Estado por fase

| Fase | Contenido | Estado |
|---|---|---|
| F1 | Esqueleto de repositorio | Creado |
| F2 | Requerimientos (01-requerimientos/) | Creado — SRS v0.6, fuente de verdad integrada |
| F3 | Análisis (02-analisis/) | Creado — 01-analisis-inicial.md es esqueleto (sin fuente disponible), 02-reglas-de-negocio.md y 03-riesgos.md completos |
| F4 | Diseño (03-diseno/) | Creado — C4 (3 niveles), ER, secuencia (CU-01/02/05/07), estados, flujos, roles-permisos, ADR-001 a ADR-004 |
| F5 | Pruebas y operación (04-pruebas/, 05-prompts/, 06-operacion/) | Creado — 17 PP de entrega 1, dataset (esqueleto), instalación, respaldo y monitoreo |
