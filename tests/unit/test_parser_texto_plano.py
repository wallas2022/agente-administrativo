from parsers.correcciones import CorreccionAplicable
from parsers.texto_plano import aplicar_correcciones_texto_plano, leer_texto_plano


def test_devuelve_un_solo_segmento_con_ubicacion_texto() -> None:
    segmentos = leer_texto_plano("Estimado equipo: les recuerdo la reunión de mañana.")

    assert len(segmentos) == 1
    assert segmentos[0].ubicacion == "Texto"
    assert segmentos[0].texto == "Estimado equipo: les recuerdo la reunión de mañana."


def test_texto_vacio_no_genera_segmentos() -> None:
    assert leer_texto_plano("") == []
    assert leer_texto_plano("   \n  ") == []


def test_aplicar_correccion_reemplaza_la_primera_aparicion() -> None:
    corregido = aplicar_correcciones_texto_plano(
        "Porfavor envíen las conciliaciones.",
        [CorreccionAplicable("Texto", "Porfavor", "Por favor")],
    )

    assert corregido == "Por favor envíen las conciliaciones."


def test_correccion_con_ubicacion_distinta_no_se_aplica() -> None:
    corregido = aplicar_correcciones_texto_plano(
        "Texto original", [CorreccionAplicable("Otra ubicación", "original", "cambiado")]
    )

    assert corregido == "Texto original"
