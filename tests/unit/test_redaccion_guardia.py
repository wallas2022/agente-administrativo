from validadores.redaccion.guardia import verificar_integridad


def test_aprueba_una_reescritura_que_conserva_cifras_fechas_y_nombres() -> None:
    original = "El 28 de septiembre de 2026, Juan Pérez aprobó un gasto de Q 1,250.00."
    sugerido = "El gasto de Q 1,250.00 lo aprobó Juan Pérez el 28 de septiembre de 2026."

    resultado = verificar_integridad(original, sugerido)

    assert resultado.aprobado is True
    assert resultado.razon is None


def test_rechaza_si_el_monto_cambio() -> None:
    original = "El gasto fue de Q 1,250.00."
    sugerido = "El gasto fue de Q 1,500.00."

    resultado = verificar_integridad(original, sugerido)

    assert resultado.aprobado is False
    assert "cifras" in resultado.razon.lower()


def test_rechaza_si_la_fecha_cambio() -> None:
    original = "La reunión fue el 28 de septiembre de 2026."
    sugerido = "La reunión fue el 29 de septiembre de 2026."

    resultado = verificar_integridad(original, sugerido)

    assert resultado.aprobado is False
    assert "fecha" in resultado.razon.lower()


def test_rechaza_si_el_nombre_propio_cambio() -> None:
    original = "Juan Pérez aprobó el documento."
    sugerido = "María López aprobó el documento."

    resultado = verificar_integridad(original, sugerido)

    assert resultado.aprobado is False
    assert "nombres propios" in resultado.razon.lower()


def test_nombre_propio_al_inicio_de_oracion_no_se_compara_por_limitacion_conocida() -> None:
    """Limitación documentada (§2.3 del análisis): un nombre propio que abre
    una oración no se detecta como tal en ninguno de los dos lados, así que
    si cambia, la guardia no lo nota -- se deja como prueba de la
    limitación conocida, no como comportamiento deseado."""
    original = "Juan aprobó el documento."
    sugerido = "Pedro aprobó el documento."

    resultado = verificar_integridad(original, sugerido)

    assert resultado.aprobado is True  # limitación conocida, no una garantía


def test_reescritura_sin_cifras_fechas_ni_nombres_siempre_se_aprueba() -> None:
    original = "El procedimiento debe revisarse con cuidado."
    sugerido = "Se debe revisar el procedimiento con cuidado."

    resultado = verificar_integridad(original, sugerido)

    assert resultado.aprobado is True
