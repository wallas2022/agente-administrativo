# kb/reglas/

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/02-analisis/02-reglas-de-negocio.md, docs/03-diseno/er/modelo-datos.md (entidad `regla`)

Reglas de negocio parametrizadas que el agente aplica durante la validación (ej. cuadre contable, mezcla de moneda, vigencia normativa). Cada fila referencia un ID `RN-xx` definido en [docs/02-analisis/02-reglas-de-negocio.md](../../docs/02-analisis/02-reglas-de-negocio.md). Ver plantilla en `reglas.csv`.

## Columnas

| Columna | Descripción |
|---|---|
| `id_regla` | ID de la regla (`RN-xx`) |
| `descripcion` | Descripción de la regla |
| `area` | Área responsable de la regla |
| `tipo_documento` | Tipo de documento al que aplica (Excel, Word, PDF, PowerPoint, imagen) |
| `severidad` | Severidad del hallazgo que genera (alta/media/baja) |
| `fuente_id` | Referencia a la fuente normativa que respalda la regla (`kb/fuentes`) |
| `vigente_desde` | Fecha desde la cual la regla es vigente |
| `version` | Versión de la regla (`MAYOR.MENOR.PARCHE`) |
| `estado` | `vigente` u `obsoleta` — una regla obsoleta no se elimina, se conserva para trazabilidad histórica |
| `moneda` | Moneda a la que aplica la regla cuando corresponde (`Q`, `USD`, `ambas` o vacío si no aplica) |
