# Rol y lineamientos del proyecto — Agente Administrativo

**Versión:** 0.2.0
**Fecha:** 2026-09-24
**Relacionado con:** N/A (documento raíz de gobierno documental)

## 1. Rol de este documento

Este documento es la **fuente de verdad de gobierno documental** del proyecto. Cualquier persona (o agente de IA) que trabaje sobre este repositorio debe leer primero este archivo y [docs/01-requerimientos/01-requerimiento-formal.md](01-requerimientos/01-requerimiento-formal.md) antes de crear o modificar documentación, y debe **reutilizar los IDs existentes** en lugar de duplicarlos.

## 2. Descripción del proyecto

**Agente Administrativo** es un agente de IA on-premise que valida, analiza y corrige documentos administrativos (Excel contable, Word, PDF, PowerPoint, imágenes) con base en una base de conocimiento controlada, con revisión humana obligatoria y auditoría completa de decisiones.

## 3. Esquema de identificadores (IDs)

Todo requerimiento, artefacto de análisis o diseño debe referenciarse por su ID, nunca duplicarse en texto libre. Los IDs son únicos y no se reutilizan aunque el elemento se elimine.

| Prefijo | Significado | Dónde se define |
|---|---|---|
| OE | Objetivo específico | docs/01-requerimientos/01-requerimiento-formal.md |
| RG | Requerimiento general | docs/01-requerimientos/01-requerimiento-formal.md |
| RF | Requerimiento funcional | docs/01-requerimientos/01-requerimiento-formal.md |
| RNF | Requerimiento no funcional | docs/01-requerimientos/01-requerimiento-formal.md |
| CU | Caso de uso | docs/01-requerimientos/02-casos-de-uso.md |
| HU | Historia de usuario | docs/01-requerimientos/03-historias-de-usuario.md |
| RN | Regla de negocio | docs/02-analisis/02-reglas-de-negocio.md |
| R | Riesgo | docs/02-analisis/03-riesgos.md |
| ADR | Decisión de arquitectura | docs/03-diseno/adr/ |
| PP | Prueba de prototipo | docs/04-pruebas/plan-pruebas-prototipo.md |

La trazabilidad completa OE → RG → RF → CU → HU → PP se mantiene en [docs/01-requerimientos/04-matriz-trazabilidad.md](01-requerimientos/04-matriz-trazabilidad.md).

## 4. Convención de ramas (Git)

- `main`: rama estable, siempre desplegable en el entorno de referencia.
- `develop`: integración de trabajo en curso (opcional según tamaño del equipo; [POR CONFIRMAR] si se adopta).
- `feature/<area>-<slug>`: nueva funcionalidad, ej. `feature/validador-excel-cuadre`.
- `fix/<area>-<slug>`: corrección de defecto, ej. `fix/ocr-rotacion-imagen`.
- `docs/<slug>`: cambios exclusivos de documentación.
- `chore/<slug>`: tareas de mantenimiento (dependencias, configuración, CI).

## 5. Convención de commits

Se sigue [Conventional Commits](https://www.conventionalcommits.org/es/):

```
<tipo>(<alcance opcional>): <resumen en imperativo, minúsculas>
```

Tipos permitidos: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `build`, `ci`.

Ejemplos:
- `feat(validadores-contable): agregar detección de descuadre por partida`
- `docs(requerimientos): agregar RF-12 revisión de checklist`

## 6. Versionado semántico

El proyecto (y cada documento individual) sigue `MAYOR.MENOR.PARCHE`:
- **MAYOR**: cambios que rompen compatibilidad o redefinen alcance/arquitectura.
- **MENOR**: nuevas capacidades o secciones documentales compatibles con lo existente.
- **PARCHE**: correcciones de redacción, enlaces o datos sin cambio de alcance.

Cada archivo de `docs/` declara su propia versión en el encabezado; el `CHANGELOG.md` raíz registra los cambios relevantes a nivel de repositorio.

## 7. Formato obligatorio de cada documento

Todo archivo de `docs/` inicia con:

```
# <Título>

**Versión:** X.Y.Z
**Fecha:** AAAA-MM-DD
**Relacionado con:** <IDs, ej. RG-01, RF-03, CU-02>
```

Los enlaces entre documentos son relativos. Los valores no confirmados se marcan `[POR CONFIRMAR]`; las estimaciones se marcan `aprox.`.

## 8. Roles y segregación de funciones (aplica a todo el diseño)

Fuente: SRS §6 (Interesados y roles). Roles del sistema:

| Rol | Responsabilidad | Restricción clave |
|---|---|---|
| Patrocinador (SFC) | Aprueba alcances y recursos del proyecto | No opera el sistema |
| Administrador (TI) | Gestiona usuarios, roles, servidor, modelos y respaldos | No aprueba contenido de negocio |
| Curador de conocimiento (por área) | Aprueba y mantiene vigentes las fuentes de conocimiento de su área | No aprueba sus propias cargas sin revisión par [POR CONFIRMAR] |
| Revisor/Aprobador | Acepta o rechaza hallazgos y libera documentos | Revisor ≠ quien cargó el documento (segregación de funciones, RNF-02) |
| Analista | Carga documentos y ejecuta el análisis | No aprueba sus propios análisis |
| Auditor / Consulta | Consulta historial y bitácora, solo lectura | Sin permisos de escritura |

Detalle completo en [docs/03-diseno/seguridad/roles-permisos.md](03-diseno/seguridad/roles-permisos.md).

## 9. Idioma y moneda

- Idioma de todo el contenido: español (Guatemala).
- Monedas soportadas: Quetzal (Q) y Dólar estadounidense ($/USD). Ver regla de negocio de mezcla de monedas en [docs/02-analisis/02-reglas-de-negocio.md](02-analisis/02-reglas-de-negocio.md).

## 10. Diagramas

Todos los diagramas del proyecto se expresan **exclusivamente en Mermaid** (`C4Context`/`C4Container`/`C4Component`, `erDiagram`, `sequenceDiagram`, `stateDiagram-v2`, `flowchart`). No se usan PlantUML ni imágenes estáticas de diagramas.

## 11. Ahorro de tokens en el chat

- No mostrar el contenido de los archivos creados/editados en el chat.
- No repetir la petición del usuario.
- No resumir al cierre del turno más allá de lo definido en `<salida_en_chat>`.
- Salida estándar por fase/corrección: tabla `ruta · estado` (o `ruta · cambio`), lista de pendientes `[POR CONFIRMAR]` y, si aplica, pregunta de continuación.

## 12. Fusión con archivos fuente del proyecto

Cuando el usuario pegue o copie a `docs/` archivos fuente propios del proyecto (p. ej. `00-rol-y-lineamientos.md`, `01-requerimientos/*`, `02-analisis/01-analisis-inicial.md`, `04-pruebas/plan-pruebas-prototipo.md`, `05-prompts/*`), esos archivos son la fuente de verdad: se fusionan con el contenido generado aquí conservando convenciones de ramas/commits/semver/formato de encabezado, y adoptando de la fuente del proyecto sus roles, IDs y reglas específicas. No se duplica contenido; se referencia por ruta e ID.
