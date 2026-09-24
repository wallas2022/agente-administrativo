# Agente Administrativo

Agente de IA on-premise que valida, analiza y corrige documentos administrativos (Excel contable, Word, PDF, PowerPoint, imágenes) con base en una base de conocimiento controlada, con revisión humana y auditoría.

**Versión:** 1.0.0 · **Fecha:** 2026-09-24 · **Estado:** documentación F1–F5 completa (prototipo); pendiente validación de datos de negocio marcados `[POR CONFIRMAR]` y acceso al ambiente stage

## Documentación

La documentación completa (requerimientos, análisis, diseño, pruebas y operación) vive en [docs/](docs/README.md). Empezar por [docs/00-rol-y-lineamientos.md](docs/00-rol-y-lineamientos.md).

## Casos de uso principales

- Validación de Excel contable descuadrado.
- Redacción y revisión de documentos PDF/Word.
- Actualización normativa en documentos Word.
- Controles y checklists administrativos.
- Corrección ortográfica en texto, Excel, Word, PowerPoint y PDF.
- Extracción de texto desde imágenes (OCR).

## Estructura del repositorio

```
├── docs/          Documentación de requerimientos, análisis, diseño, pruebas y operación
├── src/           Esqueleto de código (API, orquestador, validadores, OCR, RAG, auth, auditoría, UI)
├── infra/         Infraestructura declarada (compose base + overlays local/stage, especificación de VM Proxmox, scripts)
├── kb/            Base de conocimiento controlada (fuentes, glosario, reglas)
└── tests/         Pruebas unitarias, de integración y dataset de errores sembrados
```

## Stack tecnológico

FastAPI + LangGraph · Redis · Ollama/llama.cpp (modelos MoE: gpt-oss, Qwen3-30B-A3B) · bge-m3 · Qdrant · PostgreSQL 16 · MinIO · openpyxl / python-docx / python-pptx / Docling / PyMuPDF · Tesseract + OpenCV · LanguageTool · AD/LDAP · Langfuse + Prometheus + Grafana.

Detalle de decisiones en [docs/03-diseno/adr/](docs/03-diseno/adr/).

## Desarrollo local

El proyecto usa tres ambientes (local, stage, producción) con el mismo artefacto y distinta configuración — ver [docs/03-diseno/despliegue/estrategia-ambientes.md](docs/03-diseno/despliegue/estrategia-ambientes.md) y [ADR-004](docs/03-diseno/adr/ADR-004-ambientes-local-stage.md).

1. Copiar `.env.local.example` a `.env.local` en la raíz del repo y completar valores (sin secretos reales; ver comentarios del archivo).
2. Levantar el ambiente local: `./infra/scripts/levantar-local.sh` (equivalente a `docker compose --env-file .env.local -f infra/compose.yml -f infra/compose.local.yml up -d`). Agregar `--profile observabilidad` para incluir Prometheus y Grafana.
3. Requisitos mínimos sugeridos (aprox.): 16 GB RAM (32 GB recomendado), 8 núcleos, 100 GB libres, WSL2 habilitado.
4. Ver [docs/06-operacion/instalacion.md](docs/06-operacion/instalacion.md) para la guía completa.

## Despliegue en stage

El ambiente stage corre en una VM Proxmox sin salida a internet (paquete offline). Guía paso a paso en [docs/06-operacion/despliegue-stage-proxmox.md](docs/06-operacion/despliegue-stage-proxmox.md).

## Convenciones

Ramas, commits y versionado semántico se describen en [docs/00-rol-y-lineamientos.md](docs/00-rol-y-lineamientos.md).

## Licencia

[POR CONFIRMAR]
