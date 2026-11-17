import random
import string

import pytest

from anonimizador.detector import validadores as v

stdnum_curp = pytest.importorskip("stdnum.mx.curp")
stdnum_rfc = pytest.importorskip("stdnum.mx.rfc")

L, D = string.ascii_uppercase, string.digits


def test_ejemplos_publicos():
    assert v.curp_valida("BOXW310820HNERXN09")  # ejemplo de python-stdnum
    assert v.rfc_valido("GODE561231GR8")
    assert v.rfc_valido("MAB9307148T4")  # persona moral
    assert v.clabe_valida("032180000118359719")
    assert v.tarjeta_valida("4111111111111111")


def test_digito_incorrecto():
    assert not v.curp_valida("BOXW310820HNERXN08")
    assert not v.rfc_valido("GODE561231GR9")
    assert not v.clabe_valida("032180000118359718")
    assert not v.tarjeta_valida("4111111111111112")


def test_fechas():
    assert v.fecha_yymmdd_valida("000229")  # 2000 bisiesto
    assert not v.fecha_yymmdd_valida("850230")
    assert not v.fecha_yymmdd_valida("851301")


def test_curp_coincide_con_stdnum():
    rnd = random.Random(7)
    for _ in range(5000):
        base = (
            "".join(rnd.choice(L) for _ in range(4))
            + f"{rnd.randint(0, 99):02d}{rnd.randint(1, 12):02d}{rnd.randint(1, 31):02d}"
            + rnd.choice("HM") + rnd.choice(["DF", "NE", "JC", "NL", "VZ"])
            + "".join(rnd.choice(L) for _ in range(3)) + rnd.choice(D + "AB")
        )
        if base[:4] in stdnum_curp._name_blacklist:
            continue
        for curp in (base + v.curp_digito(base), base + rnd.choice(D)):
            assert v.curp_valida(curp) == stdnum_curp.is_valid(curp), curp


def test_rfc_coincide_con_stdnum():
    rnd = random.Random(11)
    for _ in range(5000):
        base = (
            "".join(rnd.choice(L) for _ in range(rnd.choice([3, 4])))
            + f"{rnd.randint(0, 99):02d}{rnd.randint(1, 12):02d}{rnd.randint(1, 31):02d}"
            + "".join(rnd.choice(L + D) for _ in range(2))
        )
        if base[:4] in stdnum_rfc._name_blacklist:
            continue
        for rfc in (base + v.rfc_digito(base), base + rnd.choice(D)):
            assert v.rfc_valido(rfc) == stdnum_rfc.is_valid(rfc, validate_check_digits=True), rfc
