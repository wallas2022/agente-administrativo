"""Autenticación con usuarios locales de prueba (RF-01) y JWT.

No implementa AD/LDAP real (queda [POR CONFIRMAR] para stage); los usuarios
aquí son fixtures de desarrollo, uno por rol del SRS §6 — ver
docs/03-diseno/seguridad/roles-permisos.md. La contraseña de prueba
("cambiar123") es deliberadamente pública: no protege datos reales.
"""

import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from comun.estados import RolUsuario


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


_PASSWORD_DE_PRUEBA_HASH = _hash_password("cambiar123")


@dataclass(frozen=True)
class UsuarioLocal:
    email: str
    nombre: str
    rol: RolUsuario
    password_hash: str


_USUARIOS_DE_PRUEBA: dict[str, UsuarioLocal] = {
    f"{rol.value}@local": UsuarioLocal(
        email=f"{rol.value}@local",
        nombre=rol.value.capitalize(),
        rol=rol,
        password_hash=_PASSWORD_DE_PRUEBA_HASH,
    )
    for rol in RolUsuario
}


def obtener_usuario_de_prueba(email: str) -> UsuarioLocal | None:
    return _USUARIOS_DE_PRUEBA.get(email)


def autenticar_usuario_local(email: str, password: str) -> UsuarioLocal | None:
    usuario = obtener_usuario_de_prueba(email)
    if usuario is None:
        return None
    if not _verificar_password(password, usuario.password_hash):
        return None
    return usuario


def crear_token_acceso(
    *, email: str, rol: RolUsuario, minutos_expiracion: int = 60
) -> str:
    secreto = os.environ.get("API_SECRET_KEY", "")
    ahora = datetime.now(UTC)
    payload = {
        "email": email,
        "rol": rol.value,
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos_expiracion),
    }
    return jwt.encode(payload, secreto, algorithm="HS256")


def decodificar_token_acceso(token: str) -> dict:
    secreto = os.environ.get("API_SECRET_KEY", "")
    return jwt.decode(token, secreto, algorithms=["HS256"])
