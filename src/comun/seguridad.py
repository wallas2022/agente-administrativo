"""Autenticación local contra la base de datos (P-12, Bloque 1, RF-01):
contraseña propia por usuario (bcrypt), bloqueo tras intentos fallidos, JWT
con `usuario_id` (no email/rol -- el rol se resuelve siempre desde la base,
nunca desde el token, para que un cambio de rol surta efecto de inmediato).

No implementa AD/LDAP real (queda [POR CONFIRMAR] para stage, ver
`Usuario.origen_autenticacion`).
"""

import os
import secrets
import string
import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from sqlalchemy.orm import Session

from comun.modelos import Usuario

LIMITE_INTENTOS_FALLIDOS = 5
MINUTOS_BLOQUEO = 15
LONGITUD_MINIMA_PASSWORD = 10


def password_valida(password: str) -> bool:
    """Regla única de fortaleza (HU-25): al menos LONGITUD_MINIMA_PASSWORD
    caracteres, con letras y números -- usada tanto al cambiar la propia
    contraseña (api/main.py) como al crear/rescatar un Administrador
    (comun/crear_admin.py), para no duplicar la regla en varios lugares."""
    return (
        len(password) >= LONGITUD_MINIMA_PASSWORD
        and any(c.isalpha() for c in password)
        and any(c.isdigit() for c in password)
    )


def generar_password_temporal(longitud: int = 12) -> str:
    """P-12 (Bloque 4, HU-22): contraseña temporal para un usuario nuevo o
    restablecido -- se muestra una sola vez en la respuesta, nunca se
    guarda en texto plano. Siempre cumple password_valida()."""
    letras = string.ascii_letters
    digitos = string.digits
    resto = letras + digitos
    caracteres = [secrets.choice(letras), secrets.choice(digitos)]
    caracteres += [secrets.choice(resto) for _ in range(longitud - 2)]
    secrets.SystemRandom().shuffle(caracteres)
    return "".join(caracteres)


class CredencialesInvalidasError(Exception):
    """Email inexistente, contraseña incorrecta, usuario inactivo o sin
    contraseña local -- deliberadamente el mismo error en los cuatro casos
    (no revelar qué emails existen)."""


class UsuarioBloqueadoError(Exception):
    def __init__(self, bloqueado_hasta: datetime) -> None:
        self.bloqueado_hasta = bloqueado_hasta
        super().__init__(f"Usuario bloqueado hasta {bloqueado_hasta.isoformat()}")


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def _vencido(momento: datetime, ahora: datetime) -> bool:
    """SQLite (solo en pruebas con sesión en memoria; Postgres sí preserva
    la zona horaria) puede devolver un datetime "naive" tras recargar la
    fila -- se normaliza a UTC antes de comparar para no reventar con
    "can't compare offset-naive and offset-aware datetimes"."""
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=UTC)
    return momento <= ahora


def autenticar_usuario(sesion: Session, email: str, password: str) -> Usuario:
    """RF-01/HU-25: bloquea 15 min tras 5 intentos fallidos seguidos. El
    bloqueo se revisa ANTES de verificar la contraseña -- ni siquiera la
    correcta entra mientras dure (si no, "probar hasta acertar" nunca
    bloquearía nada)."""
    usuario = sesion.query(Usuario).filter_by(email=email).one_or_none()
    ahora = datetime.now(UTC)

    if usuario is not None and usuario.bloqueado_hasta is not None:
        if not _vencido(usuario.bloqueado_hasta, ahora):
            raise UsuarioBloqueadoError(usuario.bloqueado_hasta)
        # El bloqueo ya venció: se limpia acá para que la próxima
        # verificación de contraseña (abajo) decida normalmente.
        usuario.intentos_fallidos = 0
        usuario.bloqueado_hasta = None

    credenciales_validas = (
        usuario is not None
        and usuario.activo
        and usuario.password_hash is not None
        and verificar_password(password, usuario.password_hash)
    )
    if not credenciales_validas:
        if usuario is not None and usuario.activo:
            usuario.intentos_fallidos += 1
            if usuario.intentos_fallidos >= LIMITE_INTENTOS_FALLIDOS:
                usuario.bloqueado_hasta = ahora + timedelta(minutes=MINUTOS_BLOQUEO)
        sesion.commit()
        raise CredencialesInvalidasError()

    assert usuario is not None  # para mypy: credenciales_validas ya lo garantiza
    usuario.intentos_fallidos = 0
    usuario.bloqueado_hasta = None
    usuario.ultimo_acceso = ahora
    sesion.commit()
    return usuario


def crear_token_acceso(*, usuario_id: uuid.UUID, minutos_expiracion: int = 60) -> str:
    secreto = os.environ.get("API_SECRET_KEY", "")
    ahora = datetime.now(UTC)
    payload = {
        "sub": str(usuario_id),
        "iat": ahora,
        "exp": ahora + timedelta(minutes=minutos_expiracion),
    }
    return jwt.encode(payload, secreto, algorithm="HS256")


def decodificar_token_acceso(token: str) -> dict:
    secreto = os.environ.get("API_SECRET_KEY", "")
    return jwt.decode(token, secreto, algorithms=["HS256"])
