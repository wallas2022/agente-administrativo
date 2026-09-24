# Opción nube (evaluación futura)

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md §5 (Out-of-Scope), §7 (supuestos), RNF-01

> Estado: **fuera del alcance del piloto**. Este documento existe como marcador de una evaluación futura, no como una decisión tomada.

## Por qué no aplica al piloto

El SRS es explícito: el sistema es **on-premise, sin envío de documentos a servicios externos** (§7) y **RNF-01** exige que la VM no tenga salida a internet en operación. "Acceso desde internet o aplicación móvil" está listado como Out-of-Scope (§5). Toda la arquitectura (docs/03-diseno/despliegue/estrategia-ambientes.md, ADR-001 a ADR-004) se diseñó bajo esa restricción.

## Cuándo reconsiderar

Una opción de nube (o híbrida) podría evaluarse en el futuro si:
- El volumen de documentos o la concurrencia superan la capacidad de la infraestructura física disponible (ver R-02, R-07).
- La organización cambia su política de privacidad de datos institucionales.
- Se requiere disponibilidad fuera del horario laboral / alta disponibilidad multi-servidor (explícitamente Out-of-Scope del piloto, §5).

## Qué habría que revisar si se reconsidera

- Clasificación de datos: qué documentos podrían salir de la infraestructura propia y cuáles no (posible arquitectura híbrida).
- Costo de licenciamiento de LLM administrados vs. modelos open source auto-alojados (ver ADR-001).
- Cumplimiento normativo/contractual de SFC-Team sobre datos financieros en la nube [POR CONFIRMAR].
- Todo el diseño de portabilidad (RNF-14, `compose.<ambiente>.yml`) ya facilita agregar un ambiente adicional (`compose.cloud.yml` [POR CONFIRMAR]) sin rediseñar la aplicación, si se decidiera en el futuro.

## Pendientes

- [POR CONFIRMAR] Si existe interés real de la organización en esta opción, o si este documento puede eliminarse de la estructura.
