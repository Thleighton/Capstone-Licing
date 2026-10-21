import pytest

from app.services.ingesta_lote import seleccionar_codigos_nuevos


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