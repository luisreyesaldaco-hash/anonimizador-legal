import pytest

from anonimizador.detector import detectar
from anonimizador.detector.patrones import candidatos
from anonimizador.detector.validadores import curp_digito, rfc_digito

CURP = "PEGJ850315HDFRRN0" + curp_digito("PEGJ850315HDFRRN0")
RFC = "PEGJ850315A1" + rfc_digito("PEGJ850315A1")


def tipos_valores(texto, **kw):
    return [(h.tipo, h.valor) for h in detectar(texto, **kw)]


@pytest.mark.parametrize(
    "texto, esperado",
    [
        (f"con CURP {CURP}, mayor de edad", ("CURP", CURP)),
        (f"RFC: {RFC}.", ("RFC", RFC)),
        ("RFC GODE-561231-GR8 del actor", ("RFC", "GODE-561231-GR8")),
        ("RFC COMG600703 sin homoclave", ("RFC", "COMG600703")),
        ("la persona moral MAB9307148T4", ("RFC", "MAB9307148T4")),
        ("número de seguridad social 12345678903", ("NSS", "12345678903")),
        ("CLABE 032180000118359719", ("CLABE", "032180000118359719")),
        ("CLABE interbancaria 012 180 0012345678 90", ("CLABE", "012 180 0012345678 90")),
        ("tarjeta 4111-1111-1111-1111", ("TARJETA", "4111-1111-1111-1111")),
        ("cuenta bancaria número 0123456789", ("CUENTA", "0123456789")),
        ("escribir a juan.perez@ejemplo.com.mx hoy", ("CORREO", "juan.perez@ejemplo.com.mx")),
        ("Correo: juan.perezOejemplo.com", ("CORREO", "juan.perezOejemplo.com")),
        ("Correo: ana_lopez©despacho.mx", ("CORREO", "ana_lopez©despacho.mx")),
        ("Correo: juan.perezWejemplo.com", ("CORREO", "juan.perezWejemplo.com")),
        ("tel. 55 1234 5678", ("TELEFONO", "55 1234 5678")),
        ("celular +52 33 1234 5678", ("TELEFONO", "+52 33 1234 5678")),
        ("clave de elector PRGRJN85031509H400", ("CLAVE_ELECTOR", "PRGRJN85031509H400")),
        ("en el expediente 1234/2024-II", ("EXPEDIENTE", "1234/2024-II")),
        ("juicio ordinario civil número 567/2023", ("EXPEDIENTE", "567/2023")),
        ("amparo directo 89/2022 promovido", ("EXPEDIENTE", "89/2022")),
        ("con placas de circulación ABC-123-D", ("PLACA", "ABC-123-D")),
        ("el 15 de marzo de 2024 se", ("FECHA", "15 de marzo de 2024")),
        ("fechado el 01/02/2023", ("FECHA", "01/02/2023")),
        ("la suma de $150,000.00 M.N.", ("MONTO", "$150,000.00 M.N.")),
        ("(CIENTO CINCUENTA MIL PESOS 00/100 M.N.)", ("MONTO", "(CIENTO CINCUENTA MIL PESOS 00/100 M.N.)")),
    ],
)
def test_detecta(texto, esperado):
    assert esperado in tipos_valores(texto)


def test_domicilio_hasta_codigo_postal():
    t = ("con domicilio ubicado en Calle Hidalgo número 45, colonia Centro, "
         "alcaldía Cuauhtémoc, C.P. 06000, Ciudad de México; y")
    assert tipos_valores(t) == [
        ("DOMICILIO", "Calle Hidalgo número 45, colonia Centro, alcaldía Cuauhtémoc, C.P. 06000"),
    ]


def test_domicilio_sin_codigo_postal_corta_en_punto_y_coma():
    t = "señalando como domicilio Avenida Juárez 100, Guadalajara; asimismo"
    assert ("DOMICILIO", "Avenida Juárez 100, Guadalajara") in tipos_valores(t)


@pytest.mark.parametrize(
    "texto",
    [
        "Con fundamento en el artículo 1916 del Código Civil Federal y 14 de la Constitución.",
        "El C. Juez Tercero de lo Civil acuerda lo siguiente.",
        "Se promueve juicio de amparo en contra del acto reclamado.",
        "La fracción XXIII del artículo 123 apartado A.",
        "Tesis 2a./J. 58/2010 de la Segunda Sala.",
        "Calle sin número conocido.",
    ],
)
def test_no_marca_texto_juridico_comun(texto):
    assert tipos_valores(texto, tipos=["CURP", "RFC", "NSS", "CLABE", "TARJETA", "TELEFONO",
                                       "CLAVE_ELECTOR", "EXPEDIENTE", "PLACA", "DOMICILIO"]) == []


def test_numero_al_azar_de_18_digitos_no_es_clabe():
    assert tipos_valores("referencia 123456789012345678") == []
    assert ("FOLIO", "123456789012345678") in tipos_valores("folio 123456789012345678")


def test_curp_no_se_parte_en_rfc():
    # El RFC está contenido en la CURP; debe ganar la CURP completa.
    assert tipos_valores(CURP) == [("CURP", CURP)]


def test_clabe_gana_a_telefono_y_tarjeta():
    assert [t for t, _ in tipos_valores("CLABE 032180000118359719")] == ["CLABE"]


def test_filtro_por_tipos():
    t = f"CURP {CURP}, el 15 de marzo de 2024"
    assert [x for x, _ in tipos_valores(t, tipos=["FECHA"])] == ["FECHA"]


def test_posiciones_corresponden_al_texto():
    t = f"PRIMERO. CURP {CURP}, correo a@b.mx, tel. 55 1234 5678."
    for h in detectar(t):
        assert t[h.inicio:h.fin] == h.valor


@pytest.mark.parametrize("texto", ["Visita www.ejemplo.com", "MEXICO.com", "La marca FOO.com", "Oficio 2.0 del juzgado",
                                   "Compré en MercadoLibre.com", "Ver Art.123 del CFF"])
def test_correo_ocr_sin_falsos_positivos(texto):
    assert not any(h.tipo == "CORREO" for h in candidatos(texto)), texto


@pytest.mark.parametrize("texto,esperado", [
    ("con cédulas profesionales 98417203 y 98652914, respectivamente", [("FOLIO", "98417203"), ("FOLIO", "98652914")]),
    ("No. empleado: IMV-0347 Puesto", [("FOLIO", "IMV-0347")]),
    ("Registro patronal IMSS (según CFDI)\nY64-18027-10-3", [("FOLIO", "Y64-18027-10-3")]),
    ("(céd. 98105447); Lic.", [("FOLIO", "98105447")]),
    ("Clave interna CLA-LAB-2026-009 · Despido", [("FOLIO", "CLA-LAB-2026-009")]),
])
def test_folios(texto, esperado):
    assert [x for x in tipos_valores(texto) if x[0] == "FOLIO"] == esperado


def test_nss_con_seguridad_social_aunque_el_digito_no_cuadre():
    assert ("NSS", "41089012766") in tipos_valores("número de seguridad social 41089012766.")


@pytest.mark.parametrize("texto,esperado", [
    ("www.asm-abogados.mx · litigio", "www.asm-abogados.mx"),
    ("https://correo.buzonmx.net/mail/u/0 ok", "https://correo.buzonmx.net/mail/u/0"),
    ("facturas a metalicasdelvalle.com.mx hoy", "metalicasdelvalle.com.mx"),
])
def test_web_privada(texto, esperado):
    assert ("WEB", esperado) in tipos_valores(texto)


@pytest.mark.parametrize("texto", ["Fuente: https://sjf2.scjn.gob.mx/detalle/tesis/2027", "ver www.dof.gob.mx",
                                   "correo a juan@ejemplo.com"])
def test_web_publica_o_correo_no_es_web(texto):
    assert not any(t == "WEB" for t, _ in tipos_valores(texto))


@pytest.mark.parametrize("rotulo", ["Domicilio particular", "Domicilio", "Domicilio para emplazar", "Domicilio fiscal:"])
def test_domicilio_en_tabla_no_incluye_el_rotulo(rotulo):
    t = f"{rotulo}\nCerrada de los Tejedores número 48, Col. Arcos del Sur, C.P. 09867, Ciudad de México\nCelular"
    doms = [x for x in tipos_valores(t) if x[0] == "DOMICILIO"]
    assert doms == [("DOMICILIO", "Cerrada de los Tejedores número 48, Col. Arcos del Sur, C.P. 09867")]


def test_mencionar_el_domicilio_no_es_un_domicilio():
    t = ("tener por señalado el domicilio procesal y el correo electrónico indicados, en términos "
         "del artículo 692, fracción II, de la Ley Federal del Trabajo.")
    assert not any(tp == "DOMICILIO" for tp, _ in tipos_valores(t))


@pytest.mark.parametrize("texto,fecha", [
    ("Entrevista 1: 8-sep-2026, 17:00", "8-sep-2026"),
    ("la metimos el 15-sep porque", "15-sep"),
    ("la promovieron en ene-2022.", "ene-2022"),
    ("desde el 4-mar-2019 como", "4-mar-2019"),
    ("el viernes 17 de julio se presentó", "17 de julio"),
    ("firmado el 4 mar 2019", "4 mar 2019"),
    ("recibos de mayo 2025 y", "mayo 2025"),
    ("llegó hasta el 8-sep. Hay que", "8-sep"),
    ("firmó el 4 mar. 2019 ante", "4 mar. 2019"),
])
def test_fechas_abreviadas_y_sin_anio(texto, fecha):
    assert ("FECHA", fecha) in tipos_valores(texto)


@pytest.mark.parametrize("texto", [
    "clave D02-01 · 01/03", "en el mar 20 barcos", "el art. 48 de la ley", "Mayo Hernández firmó",
])
def test_no_son_fechas(texto):
    assert not any(t == "FECHA" for t, _ in tipos_valores(texto))


def test_vialidad_como_palabra_comun_no_es_domicilio():
    t = "la prolongación diaria de su jornada durante 52 semanas (del 14 al 23 de julio)"
    assert not any(tp == "DOMICILIO" for tp, _ in tipos_valores(t))
    assert ("FECHA", "23 de julio") in tipos_valores(t)


def test_vialidad_con_nombre_sigue_siendo_domicilio():
    t = "vive en Prolongación Reforma 120, Col. Centro, C.P. 06000"
    assert any(tp == "DOMICILIO" for tp, _ in tipos_valores(t))
