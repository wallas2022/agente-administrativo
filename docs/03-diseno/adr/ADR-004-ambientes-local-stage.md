# ADR-004 — Estrategia de ambientes: local → stage → producción

**Versión:** 1.0
**Fecha:** 2026-09-24
**Relacionado con:** RNF-01, RNF-02, RNF-07, RNF-14 (Portabilidad), R-02, R-10, [docs/03-diseno/despliegue/estrategia-ambientes.md](../despliegue/estrategia-ambientes.md), [docs/06-operacion/despliegue-stage-proxmox.md](../../06-operacion/despliegue-stage-proxmox.md)

## Estado

Aceptado.

## Contexto

El servidor físico donde se instalará Proxmox VE y la VM de stage/producción **no está disponible aún** [POR CONFIRMAR: fecha de acceso]. El desarrollo del agente no puede detenerse hasta que TI otorgue ese acceso, y la VM de stage —una vez disponible— **no tendrá salida a internet** (RNF-01), por lo que todo despliegue en ella depende de un paquete offline (imágenes Docker + modelos) construido previamente.

Se necesita una estrategia que permita:
1. Desarrollar y probar de forma productiva sin depender del servidor físico.
2. Garantizar que el mismo artefacto (código e imágenes) que se prueba en desarrollo sea el que se despliega en stage y, eventualmente, en producción.
3. Documentar de antemano el procedimiento de despliegue en stage para ejecutarlo en cuanto exista acceso.

## Decisión

Se adoptan **tres ambientes** con el principio de 12-factor "mismo artefacto, distinta configuración":

| Ambiente | Dónde corre | Configuración |
|---|---|---|
| Local (dev) | PC del desarrollador (Windows + WSL2 + Docker Desktop) | `compose.yml` + `compose.local.yml` + `.env.local` |
| Stage | VM en Proxmox VE sobre el servidor físico | `compose.yml` + `compose.stage.yml` + `.env.stage` |
| Producción (futuro) | VM(s) en Proxmox, mismo servidor u otro [POR CONFIRMAR] | A definir cuando se planifique la promoción a producción |

Consecuencias directas de la decisión:

- **Infraestructura como código dividida** en `infra/compose.yml` (base, servicios sin puertos ni límites de recursos) más un overlay por ambiente (`infra/compose.local.yml`, `infra/compose.stage.yml`) que ajusta puertos, límites de recursos, volúmenes y variables.
- **Sin llamadas salientes a internet en stage/producción**: el traslado de imágenes y modelos se hace mediante paquete offline verificado con SHA256 (`infra/scripts/empaquetar-offline.sh`, `infra/scripts/cargar-en-stage.sh`).
- **Modelos LLM distintos por ambiente**: modelo pequeño en local (velocidad de iteración), modelo objetivo aprobado en ADR-001 en stage/producción (representatividad de resultados).
- **El rendimiento medido en local no es representativo**: las metas de RNF-04 (rendimiento) solo se validan en stage.
- **Evolución a GPU (fase 2, fuera de la primera entrega)**: `infra/compose.gpu.yml` agrega un motor de inferencia alternativo (vLLM) bajo el perfil `gpu`, desactivado por defecto; no modifica el servicio `ollama` de la primera entrega. Ver [docs/03-diseno/despliegue/estrategia-ambientes.md](../despliegue/estrategia-ambientes.md) §8 y [docs/06-operacion/despliegue-stage-proxmox.md](../../06-operacion/despliegue-stage-proxmox.md) §11.
- Detalle operativo completo en [docs/03-diseno/despliegue/estrategia-ambientes.md](../despliegue/estrategia-ambientes.md) (diseño) y [docs/06-operacion/despliegue-stage-proxmox.md](../../06-operacion/despliegue-stage-proxmox.md) (procedimiento paso a paso).

## Alternativas consideradas

| Alternativa | Por qué se descarta |
|---|---|
| Desarrollar directamente contra un único ambiente (stage) | El servidor físico no está disponible; bloquearía todo el desarrollo hasta que TI otorgue acceso. |
| Un solo `docker-compose.yml` con variables de entorno condicionando todo | Mezcla configuración de puertos/recursos/volúmenes específica de cada ambiente en un solo archivo, dificultando auditar qué cambia entre local y stage; se prefiere la separación explícita en archivos overlay. |
| Depender de acceso a internet también en stage (sin paquete offline) | Contradice RNF-01 (sin salida a internet) y el requisito de TI de una VM aislada. |

## Consecuencias

- Se agregan `infra/compose.local.yml`, `infra/compose.stage.yml`, `.env.local.example`, `.env.stage.example` y los scripts de empaquetado/carga como parte del esqueleto de infraestructura.
- Toda futura decisión de despliegue en producción debe partir de esta misma base de tres capas, extendiendo con un eventual `compose.prod.yml` en lugar de crear una estrategia nueva.
- Pendiente: definir en un ADR posterior [POR CONFIRMAR] si producción reutiliza la misma VM de stage u otra independiente.
