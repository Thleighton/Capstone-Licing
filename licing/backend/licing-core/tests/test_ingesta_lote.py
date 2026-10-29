import pytest

from app.services.ingesta_lote import priorizar_nuevas_oportunidades, seleccionar_codigos_nuevos


def test_prioriza_salon_y_eventos_sin_omitir_otras_licitaciones():
    listado = [
        {"CodigoExterno": "AJENO", "Nombre": "Compra de material de aseo"},
        {"CodigoExterno": "CATERING", "Nombre": "Servicio de banquetería"},
        {"CodigoExterno": "MIXTO", "Nombre": "Servicio de salón y cafetería para capacitación"},
        {"CodigoExterno": "ARRIENDO", "Nombre": "Contratación de salón para capacitación"},
        {"CodigoExterno": "MAQUINAS", "Nombre": "Arriendo de espacios para máquinas dispensadoras"},
        {"CodigoExterno": "JORNADA", "Nombre": "Jornada de trabajo PLADECO"},
    ]
    codigos = ["AJENO", "CATERING", "MIXTO", "ARRIENDO", "MAQUINAS", "JORNADA"]

    assert priorizar_nuevas_oportunidades(listado, codigos) == [
        "ARRIENDO", "MIXTO", "CATERING", "JORNADA", "AJENO", "MAQUINAS"
    ]


def test_excluye_codigos_ya_procesados():
    listado = [
        {"CodigoExterno": "CODIGO-A"},
        {"CodigoExterno": "CODIGO-B"},
        {"CodigoExterno": "CODIGO-C"},
    ]

    resultado = seleccionar_codigos_nuevos(
        listado,
        codigos_existentes={"CODIGO-A"},
    )

    assert resultado == ["CODIGO-B", "CODIGO-C"]


def test_respeta_limite():
    listado = [
        {"CodigoExterno": "CODIGO-A"},
        {"CodigoExterno": "CODIGO-B"},
        {"CodigoExterno": "CODIGO-C"},
    ]

    resultado = seleccionar_codigos_nuevos(
        listado,
        codigos_existentes=set(),
        limite=2,
    )

    assert resultado == ["CODIGO-A", "CODIGO-B"]


def test_no_repite_codigos_del_listado():
    listado = [
        {"CodigoExterno": "CODIGO-A"},
        {"CodigoExterno": " CODIGO-A "},
        {"CodigoExterno": "CODIGO-B"},
    ]

    resultado = seleccionar_codigos_nuevos(
        listado,
        codigos_existentes=set(),
    )

    assert resultado == ["CODIGO-A", "CODIGO-B"]


def test_ignora_codigos_vacios_o_invalidos():
    listado = [
        {},
        {"CodigoExterno": None},
        {"CodigoExterno": " "},
        {"CodigoExterno": 123},
        {"CodigoExterno": "CODIGO-A"},
    ]

    resultado = seleccionar_codigos_nuevos(
        listado,
        codigos_existentes=set(),
    )

    assert resultado == ["CODIGO-A"]


def test_listado_vacio():
    resultado = seleccionar_codigos_nuevos(
        [],
        codigos_existentes=set(),
    )

    assert resultado == []


def test_rechaza_limite_invalido():
    with pytest.raises(ValueError):
        seleccionar_codigos_nuevos(
            [],
            codigos_existentes=set(),
            limite=0,
        )
