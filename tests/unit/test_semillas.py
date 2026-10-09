from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from comun.estados import RolUsuario
from comun.modelos import Area, Base, Permiso, Rol, Usuario
from comun.permisos import MATRIZ_PERMISOS_DEFECTO
from comun.seguridad import hash_password, verificar_password
from comun.semillas import CONTRASENA_DE_PRUEBA, sembrar_datos_de_prueba


def _sesion() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_sembrar_datos_de_prueba_crea_un_usuario_por_rol() -> None:
    sesion = _sesion()

    usuarios = sembrar_datos_de_prueba(sesion)

    assert set(usuarios.keys()) == {f"{r.value}@local" for r in RolUsuario}
    assert sesion.query(Usuario).count() == len(RolUsuario)


def test_sembrar_datos_de_prueba_es_idempotente() -> None:
    sesion = _sesion()

    sembrar_datos_de_prueba(sesion)
    sembrar_datos_de_prueba(sesion)

    assert sesion.query(Usuario).count() == len(RolUsuario)


def test_usuarios_sembrados_tienen_password_hash_de_la_contrasena_de_prueba() -> None:
    sesion = _sesion()
    usuarios = sembrar_datos_de_prueba(sesion)

    for usuario in usuarios.values():
        assert usuario.password_hash is not None
        assert verificar_password(CONTRASENA_DE_PRUEBA, usuario.password_hash)
        # Conveniencia para E2E/pruebas manuales -- no son contraseñas
        # temporales reales (esas sí obligan a cambiarla, HU-25).
        assert usuario.debe_cambiar_password is False


def test_sembrar_datos_de_prueba_rellena_password_hash_de_un_usuario_ya_existente() -> None:
    """Encontrado en vivo (P-12): una base de datos que ya tenía estos
    usuarios ANTES de este bloque (sin la columna password_hash, o con ella
    en NULL) debe poder iniciar sesión después de correr la migración --
    sembrar_datos_de_prueba corre en cada arranque de la API, así que debe
    completar la contraseña de un usuario preexistente, no solo crear uno
    nuevo."""
    sesion = _sesion()
    area = Area(nombre="Contabilidad")
    rol = Rol(nombre=RolUsuario.ANALISTA.value)
    sesion.add_all([area, rol])
    sesion.flush()
    usuario_preexistente = Usuario(
        nombre="Analista",
        email="analista@local",
        area_id=area.id,
        rol_id=rol.id,
        origen_autenticacion="local",
        activo=True,
        # password_hash sin asignar -- simula una fila de antes de P-12.
    )
    sesion.add(usuario_preexistente)
    sesion.commit()
    assert usuario_preexistente.password_hash is None

    sembrar_datos_de_prueba(sesion)

    sesion.refresh(usuario_preexistente)
    assert usuario_preexistente.password_hash is not None
    assert verificar_password(CONTRASENA_DE_PRUEBA, usuario_preexistente.password_hash)


def test_sembrar_datos_de_prueba_no_pisa_la_contrasena_ya_cambiada() -> None:
    """Si alguien ya cambió su contraseña (HU-25), el siguiente arranque de
    la API no debe revertirla a la de prueba."""
    sesion = _sesion()
    sembrar_datos_de_prueba(sesion)
    usuario = sesion.query(Usuario).filter_by(email="analista@local").one()
    usuario.password_hash = hash_password("OtraClaveDistinta1")
    sesion.commit()

    sembrar_datos_de_prueba(sesion)

    sesion.refresh(usuario)
    assert verificar_password("OtraClaveDistinta1", usuario.password_hash)
    assert not verificar_password(CONTRASENA_DE_PRUEBA, usuario.password_hash)


def test_sembrar_datos_de_prueba_tambien_siembra_los_permisos_por_defecto() -> None:
    sesion = _sesion()
    sembrar_datos_de_prueba(sesion)

    total_esperado = sum(len(p) for p in MATRIZ_PERMISOS_DEFECTO.values())
    assert sesion.query(Permiso).count() == total_esperado
