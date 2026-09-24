# tests/dataset/

**Versión:** 0.2.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/04-pruebas/plan-pruebas-prototipo.md §1, docs/04-pruebas/casos-prueba/PP-01.md, PP-03.md, PP-12.md, PP-17.md, PP-18.md

Dataset de documentos anonimizados del área de Contabilidad, con errores **sembrados y conocidos**, usado para medir precisión/recall del agente (OE-01 a OE-07) antes de escalar el piloto. Sin lógica de negocio: esta carpeta contiene datos de prueba y su documentación, no código.

## Composición (mínimo 30 documentos)

| Tipo | Cantidad | Carpeta | Notas |
| --- | --- | --- | --- |
| Excel contable | 10 | `excel/` | Errores de cuadre, cuentas, período, duplicados, mezcla de moneda (RN-01..05) |
| Word | 8 | `word/` | Errores de redacción y/o ortográficos |
| PowerPoint | 4 | `powerpoint/` | Errores ortográficos en diapositivas y notas |
| PDF digital | 4 | `pdf/digital/` | Con capa de texto |
| PDF escaneado | 2 | `pdf/escaneado/` | Sin capa de texto (requiere OCR, iteración 2) |
| Imágenes (.jpg/.png/.tiff) | 2 | `imagenes/` | Iteración 2 (RF-11) |

**Total: 30 documentos.** De estos:
- Al menos **5 "complejos"**: varias hojas (Excel), > 5,000 filas (Excel) o > 50 páginas (Word/PDF). Marcados con el sufijo `-complejo` en el nombre de archivo.
- **2 archivos cercanos a 1 GB** (uno Excel y uno PDF, sugerido), para probar la carga máxima y reanudable (RF-03, PP-18). Marcados con el sufijo `-1gb`.

## Hoja de respuestas

Cada documento tiene un archivo hermano en `respuestas/<mismo-nombre>.respuestas.md` con la lista de errores sembrados esperados:

```markdown
# Hoja de respuestas — <nombre-del-documento>

| # | Tipo de error | Ubicación | Descripción | Severidad esperada |
|---|---|---|---|---|
| 1 | descuadre | Hoja1!C15 | Débito no coincide con crédito | alta |
| 2 | ortografía | párrafo 3 | "administracion" sin tilde | media |
```

Esta hoja es la referencia contra la que se comparan los hallazgos del agente en PP-01, PP-03 y PP-05/PP-06 (recall y falsos positivos).

## Línea base de tiempo manual

Para cada documento se registra el tiempo que toma revisarlo manualmente (hasta 60 min, según el tipo y complejidad), usado como referencia en PP-17 (ahorro de tiempo). Se documenta en `respuestas/linea-base-tiempos.csv` con columnas `documento,tipo,minutos_revision_manual`.

## Anonimización

Todos los documentos son **sintéticos o anonimizados**: sin nombres reales de personas, cuentas bancarias reales, montos reales de la organización ni datos que permitan identificar a un tercero. Los errores se siembran deliberadamente sobre plantillas genéricas o datos ficticios (R-08: falta de datos reales para pruebas, mitigado con este dataset).

## Estructura de carpetas

```
tests/dataset/
├── excel/
├── word/
├── powerpoint/
├── pdf/
│   ├── digital/
│   └── escaneado/
├── imagenes/
└── respuestas/
    ├── <documento>.respuestas.md   (uno por cada documento)
    └── linea-base-tiempos.csv
```

## Pendiente

- Carga real de los 30 documentos y sus hojas de respuesta — [POR CONFIRMAR] responsable y fecha (Área usuaria de Contabilidad, ver R-08 en docs/02-analisis/03-riesgos.md).
- Tamaño exacto de los 2 archivos cercanos a 1 GB — deben acercarse al límite sin excederlo (RF-03: máx. 1 GB).
