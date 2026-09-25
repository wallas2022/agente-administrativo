from comun.estados import EstadoAnalisis, EstadoDocumento, RolUsuario


def test_estados_documento_cubren_el_ciclo_de_vida_documentado() -> None:
    valores = {e.value for e in EstadoDocumento}
    esperados = {
        "cargado",
        "procesando",
        "con_hallazgos",
        "en_revision",
        "fallido",
        "aprobado",
        "rechazado",
        "cerrado",
    }
    assert valores == esperados


def test_estados_analisis_incluye_procesando_y_terminales() -> None:
    valores = {e.value for e in EstadoAnalisis}
    assert "procesando" in valores
    assert "completado" in valores
    assert "fallido" in valores


def test_rol_usuario_cubre_los_cinco_roles_del_srs() -> None:
    valores = {r.value for r in RolUsuario}
    assert valores == {"administrador", "curador", "revisor", "analista", "auditor"}
