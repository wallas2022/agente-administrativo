"""Estados y roles compartidos por api y orquestador.

Relacionado con: docs/03-diseno/estados/estados-analisis.md,
docs/03-diseno/er/modelo-datos.md, docs/03-diseno/seguridad/roles-permisos.md
"""

from enum import Enum


class EstadoDocumento(str, Enum):
    CARGADO = "cargado"
    PROCESANDO = "procesando"
    CON_HALLAZGOS = "con_hallazgos"
    EN_REVISION = "en_revision"
    FALLIDO = "fallido"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"
    CERRADO = "cerrado"


class EstadoAnalisis(str, Enum):
    PROCESANDO = "procesando"
    COMPLETADO = "completado"
    FALLIDO = "fallido"


class RolUsuario(str, Enum):
    ADMINISTRADOR = "administrador"
    CURADOR = "curador"
    REVISOR = "revisor"
    ANALISTA = "analista"
    AUDITOR = "auditor"
