# src/auth

**Versión:** 0.1.0
**Fecha:** 2026-09-24
**Relacionado con:** RF-01, RF-02

## Propósito

Autenticación y autorización: validación de credenciales contra AD/LDAP, emisión de sesión/token y aplicación de control de acceso basado en roles (segregación quien carga no aprueba).

## Entradas

Credenciales de usuario. Definición de roles y permisos (`docs/03-diseno/seguridad/roles-permisos.md`).

## Salidas

Token de sesión con rol asociado. Decisiones de autorización (permitido/denegado) por acción.

## RF que cubre

RF-01, RF-02 (ver [docs/01-requerimientos/04-matriz-trazabilidad.md](../../docs/01-requerimientos/04-matriz-trazabilidad.md)).

Sin lógica de negocio implementada (solo esqueleto/interfaces).
