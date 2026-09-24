# Registro de riesgos — Agente Administrativo

**Versión:** 0.6
**Fecha:** 2026-09-24
**Relacionado con:** [docs/01-requerimientos/01-requerimiento-formal.md](../01-requerimientos/01-requerimiento-formal.md) §15, [docs/02-analisis/02-reglas-de-negocio.md](02-reglas-de-negocio.md)

Registro completo de riesgos (R-01 a R-10), fuente: requerimiento formal v0.6. El resumen embebido en el SRS ([01-requerimiento-formal.md](../01-requerimientos/01-requerimiento-formal.md) §15) enlaza aquí para el detalle y seguimiento.

| ID | Riesgo | Probabilidad | Impacto | Mitigación | Responsable | Estado |
| --- | --- | --- | --- | --- | --- | --- |
| R-01 | El LLM inventa cifras o reglas | Media | Alto | RNF-03 + citas obligatorias (RF-12) | Líder técnico | Abierto |
| R-02 | Rendimiento insuficiente solo con CPU | Media | Medio | Modelos MoE, NUMA, cola; GPU ≥ 128 GB VRAM en fase 2 | TI | Abierto |
| R-03 | Base de conocimiento desactualizada | Media | Alto | RF-16, curadores, revisión trimestral | Curadores | Abierto |
| R-04 | Fuga de información sensible | Baja | Alto | RNF-01, RNF-02, segmentación de red | TI / Seguridad | Abierto |
| R-05 | OCR de baja calidad en imágenes deficientes | Alta | Medio | Umbral de confianza, marcar texto dudoso | Líder técnico | Abierto |
| R-06 | Corrección ortográfica altera formato del archivo | Media | Medio | Editar a nivel de texto sin tocar estilos; PP-04 | Líder técnico | Abierto |
| R-07 | Capacidad de disco (4 TB) insuficiente: archivos de hasta 1 GB × ~3,000 documentos en 3 meses podrían superar la capacidad en el peor caso | Media | Alto | Retención de 3 meses (RNF-12), monitoreo de uso, alerta al 70 %, compresión de originales, medir tamaño promedio real | TI | Abierto |
| R-08 | Falta de datos reales para pruebas | Media | Alto | Dataset anonimizado con errores sembrados | Áreas usuarias | Abierto |
| R-09 | Baja adopción | Media | Medio | Usuarios clave en piloto, métricas visibles | Patrocinador | Abierto |
| R-10 | Acceso tardío al stage o diferencias local vs. stage | Alta | Medio | Paridad por contenedores (RNF-14), modelos parametrizados, guía de despliegue lista, PP de rendimiento solo en stage | Patrocinador / TI | Abierto |

## Riesgos por categoría

| Categoría | Riesgos |
| --- | --- |
| Calidad del modelo / resultados | R-01, R-05, R-06 |
| Infraestructura / rendimiento | R-02, R-07, R-10 |
| Gobierno de datos | R-03, R-08 |
| Seguridad | R-04 |
| Adopción / negocio | R-09 |

## Supuestos

1. "Estado" se agrega en este registro (no está en el SRS original) para dar seguimiento operativo; todos parten en `Abierto` hasta que el responsable confirme mitigación aplicada.
2. R-02 y R-10 están directamente ligados a la estrategia de ambientes ([docs/03-diseno/despliegue/estrategia-ambientes.md](../03-diseno/despliegue/estrategia-ambientes.md), [ADR-004](../03-diseno/adr/ADR-004-ambientes-local-stage.md)).
3. Revisión de este registro sugerida junto con cada actualización del SRS o al cierre de cada fase del piloto (ver §16 del SRS).
