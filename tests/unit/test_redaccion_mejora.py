import pytest

from ortografia.cliente_languagetool import CoincidenciaLT
from validadores.redaccion.mejora import (
    calcular_motivos,
    generar_opcion,
    mejorar_parrafo,
    preparar_parrafo,
    puede_omitir_llm,
)


def _sin_coincidencias_lt(_texto: str) -> list:
    return []


# --- preparar_parrafo -------------------------------------------------------


def test_preparar_parrafo_aplica_formato_sin_llm() -> None:
    preparado = preparar_parrafo(
        "el pago fue por Q1250 el 5/10/2026",
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert preparado.parrafo_base == "el pago fue por Q 1,250.00 el 5 de octubre de 2026"
    assert preparado.fuente_citada is None


# --- puede_omitir_llm (Bloque 4) --------------------------------------------


def test_omite_llm_en_parrafo_corto_sin_hallazgos() -> None:
    parrafo = "Todo quedó en orden y sin pendientes."
    assert (
        puede_omitir_llm(parrafo, coincidencias_lt=[], tipo_documento="Correo") is True
    )


def test_no_omite_llm_si_el_parrafo_es_largo() -> None:
    parrafo = " ".join(["palabra"] * 30)
    assert puede_omitir_llm(parrafo, coincidencias_lt=[], tipo_documento="Correo") is False


def test_no_omite_llm_si_hay_coincidencias_de_languagetool() -> None:
    coincidencia = CoincidenciaLT(
        texto="dia", offset=0, longitud=3, mensaje="x", sugerencias=["día"],
        regla_id="ES_SIMPLE_REPLACE_SIMPLE_DIA", categoria="TYPOS",
    )
    resultado = puede_omitir_llm(
        "Todo salio bien hoy.", coincidencias_lt=[coincidencia], tipo_documento="Correo"
    )
    assert resultado is False


def test_no_omite_llm_si_hay_hallazgos_est001() -> None:
    parrafo = "El monto fue Q1250."  # formato de monto incorrecto -> RD-02
    assert puede_omitir_llm(parrafo, coincidencias_lt=[], tipo_documento="Correo") is False


# --- calcular_motivos --------------------------------------------------------


def test_calcular_motivos_detecta_correccion_de_acentos() -> None:
    motivos = calcular_motivos("el dia de hoy", "el día de hoy")
    assert "acentos" in " ".join(motivos).lower()


def test_calcular_motivos_detecta_texto_mas_corto() -> None:
    motivos = calcular_motivos(
        "El pago fue aprobado por el cual se procedió a realizar el registro contable",
        "El pago fue aprobado",
    )
    assert any("acortó" in m for m in motivos)


def test_calcular_motivos_detecta_oracion_dividida() -> None:
    motivos = calcular_motivos(
        "El pago fue aprobado y revisado por el área correspondiente",
        "El pago fue aprobado. Fue revisado por el área correspondiente.",
    )
    assert any("dividió" in m for m in motivos)


def test_calcular_motivos_nunca_devuelve_lista_vacia() -> None:
    motivos = calcular_motivos("Texto corto.", "Texto breve.")
    assert len(motivos) >= 1


# --- generar_opcion ----------------------------------------------------------


def test_generar_opcion_exitosa() -> None:
    opcion = generar_opcion(
        "hola, este es un parrafo de prueba.",
        accion="corregir",
        estilo="Formal",
        funcion_llm=lambda _p: "Hola, este es un párrafo de prueba corregido.",
    )

    assert opcion is not None
    assert opcion.estilo == "Formal"
    assert opcion.aprobada_guardia is True
    assert opcion.razon_descarte is None
    assert len(opcion.motivos) >= 1


def test_generar_opcion_ninguna_si_el_llm_devuelve_el_mismo_parrafo() -> None:
    base = "texto original sin cambios."
    opcion = generar_opcion(
        base, accion="corregir", estilo="Formal", funcion_llm=lambda _p: base
    )

    assert opcion is None


def test_generar_opcion_descartada_por_la_guardia() -> None:
    opcion = generar_opcion(
        "el gasto fue de Q 1,250.00.",
        accion="corregir",
        estilo="Breve",
        funcion_llm=lambda _p: "El gasto fue de Q 1,500.00.",
    )

    assert opcion is not None
    assert opcion.aprobada_guardia is False
    assert opcion.razon_descarte is not None
    assert opcion.motivos == []


def test_generar_opcion_limpia_comillas_envolventes() -> None:
    opcion = generar_opcion(
        "texto original.",
        accion="corregir",
        estilo="Formal",
        funcion_llm=lambda _p: '"Texto reescrito."',
    )

    assert opcion is not None
    assert opcion.texto == "Texto reescrito."


def test_generar_opcion_accion_invalida_lanza_key_error() -> None:
    """`generar_opcion` es la pieza de bajo nivel que usa la ruta SSE
    directamente (Bloque 3, streaming escalonado) -- no vuelve a validar
    `accion` porque quien la llama (api/main.py) ya lo valida una sola vez,
    al completar la carga (ver SolicitudCompletarCarga). Acá no es
    `ValueError` como en `mejorar_parrafo`, es el `KeyError` del diccionario
    de instrucciones -- documentado, no un contrato nuevo a mantener."""
    with pytest.raises(KeyError):
        generar_opcion(
            "texto", accion="inventada", estilo="Formal", funcion_llm=lambda _p: "x"
        )


# --- mejorar_parrafo (envoltorio de conveniencia) ---------------------------


def test_mejorar_parrafo_arma_las_dos_opciones() -> None:
    respuestas = iter(
        [
            "Hola, este es un párrafo de prueba corregido, versión formal.",
            "Párrafo de prueba corregido.",
        ]
    )

    resultado = mejorar_parrafo(
        "hola, este es un parrafo de prueba.",
        ubicacion="Párrafo 1",
        accion="corregir",
        funcion_llm=lambda _p: next(respuestas),
        funcion_revisar_lt=_sin_coincidencias_lt,
        glosario=set(),
    )

    assert len(resultado.opciones) == 2
    assert {o.estilo for o in resultado.opciones} == {"Formal", "Breve"}
    assert resultado.tiene_opciones_aprobadas is True


def test_mejorar_parrafo_accion_invalida_lanza_value_error() -> None:
    with pytest.raises(ValueError, match="acción inválida"):
        mejorar_parrafo(
            "texto",
            ubicacion="Párrafo 1",
            accion="inventada",
            funcion_llm=lambda _p: "x",
            funcion_revisar_lt=_sin_coincidencias_lt,
            glosario=set(),
        )
