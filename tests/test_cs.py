"""Paquete checo: identificadores validados, personas declinadas e idioma."""

import pytest

from anonimizador.detector import detectar
from anonimizador.idioma import detectar_idioma
from anonimizador.seudonimos import Sesion


def tipos_valores(texto):
    return [(h.tipo, h.valor) for h in detectar(texto, idioma="cs", usar_ner=False)]


def limpio(texto):
    return Sesion(texto, detectar(texto, idioma="cs", usar_ner=False), idioma="cs").texto_limpio()


@pytest.mark.parametrize("texto,idioma", [
    ("Prodávající se zavazuje převést vlastnické právo k bytu na kupujícího dne 5. května.", "cs"),
    ("El actor demandó a la empresa por el despido injustificado de su trabajadora.", "es"),
    ("The seller agrees to transfer the property to the buyer on the agreed date.", "en"),
])
def test_idioma(texto, idioma):
    assert detectar_idioma(texto) == idioma


def test_rodne_cislo_valido_e_invalido():
    t = "r. č. 800312/1236; chybné r. č. 800312/1239; číslo objednávky 4512345678"
    rc = [(v, h) for v, h in ((h.valor, h.verificado) for h in detectar(t, idioma="cs", usar_ner=False)
                              if h.tipo == "RODNE_CISLO")]
    assert rc == [("800312/1236", True), ("800312/1239", False)]  # el pedido no se toca


def test_ico_dic_cuenta_iban():
    t = ("IČO: 25596641, DIČ CZ25596641, účet č. 19-2000145399/0800, "
         "IBAN CZ65 0800 0000 1920 0014 5399, tel. +420 777 123 456")
    tv = tipos_valores(t)
    assert ("ICO", "25596641") in tv and ("DIC", "CZ25596641") in tv
    assert ("CUENTA", "19-2000145399/0800") in tv and ("CUENTA", "CZ65 0800 0000 1920 0014 5399") in tv
    assert ("TELEFONO", "+420 777 123 456") in tv


def test_ico_con_control_invalido_no_es_ico():
    assert not [v for t, v in tipos_valores("IČO: 25596642") if t == "ICO"]


def test_domicilio_y_empresa():
    t = "Kupující: Eva Bosáková, trvale bytem Husova 1245/7, 110 00 Praha 1\nPřeklady Bohemia, s.r.o., IČO: 25596641"
    tv = tipos_valores(t)
    assert ("DOMICILIO", "Husova 1245/7, 110 00 Praha 1") in tv
    assert ("EMPRESA", "Překlady Bohemia, s.r.o.") in tv


def test_formas_declinadas_son_la_misma_persona():
    t = ("Kupující: Eva Bosáková. Smlouva mezi panem Janem Novákem a paní Bosákovou. "
         "Evou Bosákovou podepsáno. Paní Bosákové děkujeme. Svědek: Jana Nováková.")
    s = Sesion(t, detectar(t, idioma="cs", usar_ner=False), idioma="cs")
    out = s.texto_limpio()
    assert "Bosák" not in out and "Novák" not in out
    eva = next(e for e in s.entidades if e.canonico == "Eva Bosáková")
    assert out.count(eva.marcador) == 4
    # La esposa (Nováková) no es el esposo (Novák).
    jan = next(e for e in s.entidades if "Novákem" in e.variantes or e.canonico.startswith("Janem"))
    assert "Nováková" not in jan.variantes + jan.derivadas


def test_lugares_e_instituciones_no_son_personas():
    t = "Narodila se v Brně, studovala na Univerzitě Karlově a pracovala pro Charta 77 v Praze."
    assert not [v for tp, v in tipos_valores(t) if tp == "NOMBRE"]


def test_rodne_cislo_con_y_sin_diagonal_se_sustituyen():
    t = "Jan Novák, r. č. 800312/1236. Opakuji: RČ 8003121236."
    out = limpio(t)
    assert "800312" not in out


def test_titulos_no_parten_a_la_persona():
    t = "Pronajímatel: JUDr. Artur Bureš. Podpis Artura Bureše. Ing. Artur Bureš souhlasí."
    s = Sesion(t, detectar(t, idioma="cs", usar_ner=False), idioma="cs")
    assert len([e for e in s.entidades if e.tipo == "NOMBRE"]) == 1


@pytest.mark.parametrize("texto,esperado", [
    ("trvale bytem Máchova 1276, Soběslav, PSČ 392 01 odcizila zboží v hodnotě 5 943 885 Kč", "Máchova 1276, Soběslav, PSČ 392 01"),
    ("v obci Olomouc, v ulici Chodská 1590, řídil osobní automobil", "Chodská 1590"),
    ("se sídlem Okružní 12, 370 01 České Budějovice, IČO: 25596641", "Okružní 12, 370 01 České Budějovice"),
])
def test_domicilio_por_contexto_no_se_pasa_de_largo(texto, esperado):
    assert ("DOMICILIO", esperado) in tipos_valores(texto)


def test_op_en_ambos_ordenes():
    tv = tipos_valores("OP č. 953727332, číslo OP: 123456789")
    assert ("FOLIO", "953727332") in tv and ("FOLIO", "123456789") in tv


def test_spisova_znacka_no_se_traga_la_frase():
    t = "zastupoval ve věci sp. zn. 12 C 345/2024 před Okresním soudem v Kolíně."
    assert "12 C 345/2024" not in limpio(t)
    assert ("EXPEDIENTE", "12 C 345/2024") in tipos_valores(t)


def organizaciones(texto):
    from anonimizador.detector import cs
    return [h.valor for h in cs.organizaciones(texto)]


@pytest.mark.parametrize("texto,esperado", [
    ("Byl členem KSČ a později kandidoval za ANO.", ["KSČ", "ANO"]),
    ("Investiční a poštovní banky (IPB) zkrachovala; IPB pak převzala ČSOB.",
     ["Investiční a poštovní banky", "IPB", "IPB", "ČSOB"]),
    ("Automobilky Toyota, Nissan a Suzuki ohlásily stažení.", ["Toyota", "Nissan", "Suzuki"]),
    ("Působil v Komunistické straně Československa a v Československé sociální demokracii.",
     ["Komunistické straně Československa", "Československé sociální demokracii"]),
    ("Pracoval v Rehabilitační nemocnici Beroun a v Nemocnici Hořovice.",
     ["Rehabilitační nemocnici Beroun", "Nemocnici Hořovice"]),
    ("Byl předsedou Obce spisovatelů.", ["Obce spisovatelů"]),
])
def test_organizaciones_sin_forma_juridica(texto, esperado):
    assert organizaciones(texto) == esperado


@pytest.mark.parametrize("texto", [
    "Roční procentní sazba nákladů (RPSN) činí 12 %.",   # sigla de un término, no de una organización
    "Platba za SMS zprávy.",
    "Druhá strana nesouhlasila. Strany se dohodly na smíru.",
    "Okresní soud v Kolíně rozhodl; Nejvyšší soud dovolání odmítl.",   # órganos públicos: van en instituciones()
    "Na straně Petra Nováka nikdo nestál.",
    "Podle zákona o spotřebitelském úvěru (ZSÚ) je smlouva neplatná.",
])
def test_no_son_organizaciones(texto):
    assert organizaciones(texto) == []


def instituciones(texto):
    from anonimizador.detector import cs
    return [h.valor for h in cs.instituciones(texto)]


@pytest.mark.parametrize("texto,esperado", [
    ("Rozsudkem Okresního soudu v Českých Budějovicích bylo rozhodnuto.", ["Okresního soudu v Českých Budějovicích"]),
    ("Krajský soud v Brně – pobočka v Jihlavě potvrdil rozsudek.", ["Krajský soud v Brně – pobočka v Jihlavě"]),
    ("Proti rozhodnutí Obvodního soudu pro Prahu 1 podal odvolání.", ["Obvodního soudu pro Prahu 1"]),
    ("Nejvyšší soud dovolání odmítl.", ["Nejvyšší soud"]),
    ("Finanční úřad pro Jihomoravský kraj vydal výměr.", ["Finanční úřad pro Jihomoravský kraj"]),
    ("Obrátil se na Ministerstvo práce a sociálních věcí.", ["Ministerstvo práce a sociálních věcí"]),
    ("Česká národní banka zvýšila sazby.", ["Česká národní banka"]),
    ("Věc šetřil Úřad pro ochranu osobních údajů a Policie České republiky.",
     ["Úřad pro ochranu osobních údajů", "Policie České republiky"]),
    ("Soudní dvůr Evropské unie a Evropský soud pro lidská práva.",
     ["Soudní dvůr Evropské unie", "Evropský soud pro lidská práva"]),
])
def test_instituciones_publicas(texto, esperado):
    assert instituciones(texto) == esperado


@pytest.mark.parametrize("texto", [
    "Okresní soud rozhodl takto.",   # sin sede y al inicio de oración: puede ser el genérico
    "Odvolací soud dospěl k závěru, že okresní soud pochybil.",
    "Výzvou soudu ze dne 1. 2. byl vyzván.",
    "Komerční banka a Česká spořitelna.",   # bancos privados: los cubre organizaciones()
])
def test_no_son_instituciones(texto):
    assert instituciones(texto) == []


def test_espacio_duro_y_guiones_de_word():
    """Word mete espacios duros (\xa0): antes el IBAN tumbaba la carga y el IČO y los teléfonos se escapaban."""
    from anonimizador.detector import detectar

    def tipos(t):
        return [(h.tipo, h.valor) for h in detectar(t, idioma="cs", usar_ner=False)]

    assert ("CUENTA", "CZ65\xa00800\xa00000\xa01920\xa00014\xa05399") in tipos("IBAN CZ65\xa00800\xa00000\xa01920\xa00014\xa05399")
    assert ("ICO", "27\xa0074\xa0358") in tipos("IČO 27\xa0074\xa0358")
    assert ("ICO", "270\xa074\xa0358") in tipos("IČO 270\xa074\xa0358")
    t = tipos("tel.\xa0603\xa0123\xa0456, tel. 603-123-456, mobil +420-603-123-457")
    assert {v for k, v in t if k == "TELEFONO"} == {"603\xa0123\xa0456", "603-123-456", "+420-603-123-457"}
    assert not [k for k, _ in tipos("č. j. 603-123-456") if k == "TELEFONO"]  # sin contexto, guiones no es teléfono
    for t in ("rezervace: +420-257314071", "rezervace: +420 257314071"):
        assert [k for k, _ in tipos(t)] == ["TELEFONO"], tipos(t)  # no rodné číslo
    assert not tipos("IČO 27074359")  # dígito de control malo
