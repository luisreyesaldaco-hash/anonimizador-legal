"""Paquete de inglés: documentos de EE. UU. y Reino Unido, y traducciones al inglés de documentos checos."""

import pytest

from anonimizador.detector import detectar, en
from anonimizador.detector import modelo as m
from anonimizador.idioma import detectar_idioma
from anonimizador.seudonimos import Sesion

CONTRATO = """TENANCY AGREEMENT
This Agreement is made on 5 March 2024 between Mr John Smith (the "Landlord"), residing at 14 Kingsley Road, Didsbury, Manchester M20 6RB, and Ms Jana Nováková, Birth Number: 855312/1234, of Dlouhá 742/12, 110 00 Prague 1 (the "Tenant").
Smith shall repair the boiler. Nováková pays £1,250.00 per month to account 12345678, sort code 20-45-77.
Contact: john.smith@gmail.com, tel. +44 7700 900123. SSN 078-05-1120, NI number AB 12 34 56 C.
Northbridge Logistics Ltd and Alfa Stavby s.r.o., Company ID No.: 27074358, are guarantors.
Signed: John Smith          Passport No. 533380006
Dear Mr Smith, please call Dr. Emily Watson at (555) 123-4567 regarding Case No. 2:23-cv-01234.
"""


def _limpio(texto: str, usar_ner: bool = False) -> str:
    return Sesion(texto, detectar(texto, idioma="en", usar_ner=usar_ner), idioma="en").texto_limpio()


def test_idioma():
    assert detectar_idioma(CONTRATO) == "en"


def test_contrato_sin_datos_visibles():
    limpio = _limpio(CONTRATO)
    for dato in ("John Smith", "Smith", "Jana Nováková", "Nováková", "855312/1234", "Kingsley Road", "M20 6RB",
                 "Dlouhá 742/12", "£1,250.00", "12345678", "20-45-77", "john.smith@gmail.com", "7700 900123",
                 "078-05-1120", "AB 12 34 56 C", "Northbridge Logistics Ltd", "Alfa Stavby", "27074358",
                 "533380006", "Emily Watson", "(555) 123-4567", "2:23-cv-01234", "5 March 2024"):
        assert dato not in limpio, dato
    # Lo que no es dato personal se queda.
    for texto in ("TENANCY AGREEMENT", "Landlord", "Tenant", "shall repair the boiler", "Passport No.", "guarantors"):
        assert texto in limpio, texto


def test_etiquetas_en_ingles():
    s = Sesion(CONTRATO, detectar(CONTRATO, idioma="en", usar_ner=False), idioma="en")
    prefijos = {e.etiqueta.rsplit("_", 1)[0] for e in s.entidades}
    assert {"PERSON", "ADDRESS", "DATE", "COMPANY", "SSN", "NINO", "BIRTH_NO", "COMPANY_ID"} <= prefijos
    assert not prefijos & {"PERSONA", "DOMICILIO", "FECHA", "EMPRESA"}


def test_apellido_suelto_es_de_la_persona():
    s = Sesion(CONTRATO, detectar(CONTRATO, idioma="en", usar_ner=False), idioma="en")
    smith = [e for e in s.entidades if e.tipo == m.NOMBRE and "John Smith" in e.variantes]
    assert len(smith) == 1 and "Mr Smith" in smith[0].variantes + smith[0].derivadas


def test_apellido_compartido_no_queda_visible():
    t = "Petitioner: Sarah Price\nChild: David Price\nThe court awards support to Respondent, Price, monthly."
    assert "Price," not in _limpio(t)


def test_iniciales_y_rotulos():
    t = ("Surname: Černý\nFirst name(s): Tadeáš\n1.1 Surname: Vojtěchová\nRegistrar: A. D.\n"
         "| Child's name | Nikola |\nThe application of P. K. on 03/06/2015.")
    limpio = _limpio(t)
    for dato in ("Černý", "Tadeáš", "Vojtěchová", "A. D.", "Nikola", "P. K."):
        assert dato not in limpio, dato
    assert "Surname:" in limpio and "Registrar:" in limpio


@pytest.mark.parametrize("valido,invalido", [("078-05-1120", "000-12-3456"), ("123-45-6789", "666-12-3456")])
def test_ssn_valida_area(valido, invalido):
    tipos = lambda t: {h.tipo for h in detectar(t, idioma="en", usar_ner=False)}  # noqa: E731
    assert m.SSN in tipos(f"SSN {valido}")
    assert m.SSN not in tipos(f"Order {invalido}")


def test_iban_no_se_confunde_con_tarjeta():
    t = "Pay to IBAN CZ08 0800 0004 6562 4058 4719 by Friday."
    hs = detectar(t, idioma="en", usar_ner=False)
    assert [(h.tipo, h.valor) for h in hs] == [(m.CUENTA, "CZ08 0800 0004 6562 4058 4719")]


def test_leyes_no_son_datos():
    t = "concluded pursuant to Section 33 of Act No. 262/2006 Coll., the Labour Code, and Charles University rules."
    assert _limpio(t) == t


def test_palabras_funcionales_nunca_son_nombres():
    t = "I. The Defendant shall pay. II. The Plaintiff agrees. The end."
    limpio = _limpio(t)
    assert limpio.count("The") == 3


def test_empresa_checa_con_minusculas():
    hs = list(en.empresas("PRIVATE AND CONFIDENTIAL\n\nBezpečnostní agentura Štít s.r.o.\n195 Chester Terrace"))
    assert [h.valor for h in hs] == ["Bezpečnostní agentura Štít s.r.o."]


def test_membrete_y_v_marcan_la_empresa():
    t = "Bluestone Capital Ltd\n12 Park Road\n\nProposed claim: Kestrel Holdings LLP v Redfern Media Inc.\nWe bank with Barclays Bank PLC."
    s = Sesion(t, detectar(t, idioma="en", usar_ner=False), idioma="en")
    marcadas = {e.canonico: e.marcada for e in s.entidades if e.tipo == m.EMPRESA}
    assert marcadas["Bluestone Capital Ltd"] and marcadas["Kestrel Holdings LLP"] and marcadas["Redfern Media Inc."]
    assert not marcadas["Barclays Bank PLC"]


def test_la_otra_parte_del_acuerdo_va_marcada():
    t = ("Dear Mr. Thompson,\n\nI confirm that the settlement agreement with Northbridge Logistics LLC was signed. "
         "We also filed a claim against Harlow Freight Inc. Please wire the payment to Chase Bank, N.A.")
    s = Sesion(t, detectar(t, idioma="en", usar_ner=False), idioma="en")
    marcadas = {e.canonico: e.marcada for e in s.entidades if e.tipo == m.EMPRESA}
    assert marcadas["Northbridge Logistics LLC"] and marcadas["Harlow Freight Inc."]
    assert not marcadas.get("Chase Bank, N.A.", False)  # el banco, mencionado de paso, no


@pytest.mark.skipif(not en.modelo_disponible(), reason="sin en_core_web_md")
def test_modelo_encuentra_nombres_que_no_estan_en_la_lista():
    t = "BEFORE ME personally appeared Philomena Hartley, who stated that her neighbour Rafferty Okafor saw it."
    limpio = _limpio(t, usar_ner=True)
    assert "Hartley" not in limpio and "Okafor" not in limpio
