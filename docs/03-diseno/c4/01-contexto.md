# C4 — Nivel 1: Contexto

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** docs/01-requerimientos/01-requerimiento-formal.md §6 (roles), §7 (supuestos)

```mermaid
C4Context
    title Diagrama de contexto — Agente Administrativo

    Person(analista, "Analista", "Carga documentos y ejecuta el análisis (CU-01..06)")
    Person(revisor, "Revisor/Aprobador", "Acepta o rechaza hallazgos y libera documentos (CU-07)")
    Person(curador, "Curador de conocimiento", "Aprueba y mantiene vigentes las fuentes de su área (CU-08)")
    Person(admin, "Administrador (TI)", "Gestiona usuarios, roles, servidor, modelos y respaldos (CU-09)")
    Person(auditor, "Auditor", "Consulta historial y bitácora, solo lectura (CU-10)")

    System(agente, "Agente Administrativo", "Valida, analiza y corrige documentos administrativos (Excel, Word, PowerPoint, PDF, imágenes) con IA on-premise, revisión humana obligatoria y auditoría")

    System_Ext(ad, "Active Directory / LDAP", "Autenticación de usuarios y grupos [POR CONFIRMAR: existencia confirmada]")
    System_Ext(pbs, "Proxmox Backup Server", "Respaldo diario de la VM (snapshot)")

    Rel(analista, agente, "Carga documentos, selecciona revisión, ve sugerencias")
    Rel(revisor, agente, "Revisa evidencia, aprueba/rechaza hallazgos")
    Rel(curador, agente, "Carga y versiona fuentes, glosario")
    Rel(admin, agente, "Administra usuarios, roles, monitoreo")
    Rel(auditor, agente, "Consulta bitácora e historial")
    Rel(agente, ad, "Autentica usuarios", "LDAP")
    Rel(agente, pbs, "Respaldo diario", "Snapshot")

    UpdateRelStyle(agente, ad, $offsetY="-10")
```

## Elemento · responsabilidad · tecnología

| Elemento | Responsabilidad | Tecnología |
| --- | --- | --- |
| Agente Administrativo | Sistema central: validación, análisis, corrección y auditoría de documentos | FastAPI + LangGraph + Ollama/llama.cpp (ver docs/03-diseno/c4/02-contenedores.md) |
| Active Directory / LDAP | Fuente de identidad y grupos de la organización | LDAP / AD |
| Proxmox Backup Server | Respaldo a nivel de VM | Proxmox Backup Server |
| Analista / Revisor / Curador / Administrador / Auditor | Roles humanos que interactúan con el sistema | Interfaz web (Open WebUI piloto → UI propia) |

## Supuestos

1. Todos los roles acceden por la misma interfaz web interna, sin salida a internet (RNF-01).
2. La existencia real de Active Directory está [POR CONFIRMAR] (SRS §17.3); si no existe, RF-01 usa únicamente usuarios locales.
3. El sistema no tiene otros sistemas externos en el alcance del piloto (sin integración ERP, sin acceso móvil — ver SRS §5 Out-of-Scope).
4. Proxmox Backup Server aplica solo al ambiente stage; el ambiente local no tiene respaldo formal (es descartable y reproducible).
5. Los cinco roles son mutuamente excluyentes en el modelo de permisos del piloto (un usuario tiene un rol activo a la vez) — ver docs/03-diseno/seguridad/roles-permisos.md.
