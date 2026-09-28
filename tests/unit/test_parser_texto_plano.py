from parsers.texto_plano import leer_texto_plano


def test_devuelve_un_solo_segmento_con_ubicacion_texto() -> None:
    segmentos = leer_texto_plano("Estimado equipo: les recuerdo la reunión de mañana.")

    assert len(segmentos) == 1
    assert segmentos[0].ubicacion == "Texto"
    assert segmentos[0].texto == "Estimado equipo: les recuerdo la reunión de mañana."


def test_texto_vacio_no_genera_segmentos() -> None:
    assert leer_texto_plano("") == []
    assert leer_texto_plano("   \n  ") == []
