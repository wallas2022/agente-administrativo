# tests/unit/

**Versión:** 0.2.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/04-pruebas/plan-pruebas-prototipo.md, docs/04-pruebas/resultados/local-L2.md

Pruebas unitarias de `src/comun`, `src/api` y `src/orquestador` (esqueleto de L2): estados/roles, modelos SQLAlchemy, base de datos, seguridad (usuarios locales y JWT), cola (Celery), almacenamiento (MinIO/S3 con `moto`), semillas de datos de prueba, endpoints de la API (`TestClient` con dependencias sobreescritas) y la tarea del orquestador. Sin servicios reales: usan SQLite en memoria, `moto` y dobles de prueba — ver `conftest.py`.

Ejecutar desde la raíz del repo (requiere `uv` o el `.venv` con `requirements-dev.txt` instalado):

```bash
.venv/Scripts/python.exe -m pytest tests/unit -q
```

Cobertura actual: 95 % (mínimo exigido: 70 %). `ruff check src tests` y `mypy src` deben pasar sin errores.

Los validadores de negocio (contable, control, ortografía, OCR, RAG) todavía no tienen pruebas — se agregan junto con su implementación en Sprint 1 y siguientes.
