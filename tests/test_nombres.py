import pytest

from anonimizador.detector import detectar, ner_disponible
from anonimizador.detector.nombres import normaliza_mayusculas


def nombres(texto, usar_ner=False):
    return [(h.tipo, h.valor) for h in detectar(texto, tipos=["NOMBRE", "EMPRESA"], usar_ner=usar_ner)]


# --- reglas (no requieren spaCy) ----------------------------------------------


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("JUAN PÉREZ GARCÍA, por mi propio derecho, comparezco",
         [("NOMBRE", "JUAN PÉREZ GARCÍA")]),
        ("promovido por MARÍA FERNANDA LÓPEZ RUIZ en contra de ROBERTO SÁNCHEZ MEDINA, y",
         [("NOMBRE", "MARÍA FERNANDA LÓPEZ RUIZ"), ("NOMBRE", "ROBERTO SÁNCHEZ MEDINA")]),
        ("QUE CELEBRAN POR UNA PARTE EL SEÑOR JOSÉ LUIS HERNÁNDEZ DE LA CRUZ, A QUIEN",
         [("NOMBRE", "JOSÉ LUIS HERNÁNDEZ DE LA CRUZ")]),
        ("comparecen los señores Pedro Ramírez Ortiz y Lucía Torres de Ramírez.",
         [("NOMBRE", "Pedro Ramírez Ortiz"), ("NOMBRE", "Lucía Torres de Ramírez")]),
        ("a los licenciados Ana Ruiz Pérez y Carlos Méndez Ochoa, con domicilio",
         [("NOMBRE", "Ana Ruiz Pérez"), ("NOMBRE", "Carlos Méndez Ochoa")]),
        ("Atentamente, Lic. Gabriela Ochoa Ríos. Abogada patrono",
         [("NOMBRE", "Gabriela Ochoa Ríos")]),
        ("El testigo de nombre Ramón Ibarra declaró que conoce a la demandada Sofía Valdés desde",
         [("NOMBRE", "Ramón Ibarra"), ("NOMBRE", "Sofía Valdés")]),
        ("Comparece el trabajador Luis Alberto Domínguez frente a la empresa",
         [("NOMBRE", "Luis Alberto Domínguez")]),
    ],
)
def test_reglas(texto, esperado):
    assert nombres(texto) == esperado


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("reclamó de Inmobiliaria Los Pinos, S. de R.L. de C.V., el pago",
         [("EMPRESA", "Inmobiliaria Los Pinos, S. de R.L. de C.V.")]),
        ("frente a Grupo Industrial Monterrey, S.A.B. de C.V., ante",
         [("EMPRESA", "Grupo Industrial Monterrey, S.A.B. de C.V.")]),
        ("la asociación Amigos del Bosque, A.C. presentó",
         [("EMPRESA", "Amigos del Bosque, A.C.")]),
    ],
)
def test_empresas(texto, esperado):
    assert nombres(texto) == esperado


@pytest.mark.parametrize(
    "texto",
    [
        "El C. Juez Tercero de lo Civil acuerda lo siguiente.",
        "En contra de la Secretaría de Hacienda y Crédito Público.",
        "Ante el C. Agente del Ministerio Público de la Federación.",
        "CONTRATO DE ARRENDAMIENTO QUE CELEBRAN LAS PARTES",
        "con domicilio en la alcaldía Benito Juárez.",
        "promovido por el Instituto Mexicano del Seguro Social",
    ],
)
def test_no_son_nombres(texto):
    assert nombres(texto) == []


def test_normaliza_mayusculas_conserva_longitud():
    t = "CONTRATO QUE CELEBRAN EL SEÑOR JOSÉ LUIS HERNÁNDEZ DE LA CRUZ Y otros"
    n = normaliza_mayusculas(t, {"que", "el", "de", "la", "y"})
    assert len(n) == len(t)
    assert "José Luis Hernández de la Cruz" in n


# --- spaCy ----------------------------------------------------------------------

requiere_ner = pytest.mark.skipif(not ner_disponible(), reason="modelo es_core_news_md no instalado")


@requiere_ner
def test_ner_encuentra_nombre_sin_contexto():
    t = "Mediante escrito presentado ayer, Ernesto Villalobos Cruz exhibió las pruebas."
    assert ("NOMBRE", "Ernesto Villalobos Cruz") in nombres(t, usar_ner=True)


@requiere_ner
def test_ner_no_marca_instituciones():
    t = ("El Ministerio Público adscrito y la Suprema Corte de Justicia de la Nación sostuvieron "
         "en la Tesis 2a./J. 58/2010 que el artículo 14 de la Constitución Política")
    assert nombres(t, usar_ner=True) == []


@pytest.mark.parametrize("texto,esperado", [
    ("Nombre\nMARÍA FERNANDA RÍOS CALDERÓN\nCURP", ["MARÍA FERNANDA RÍOS CALDERÓN"]),
    ("TESTIGO\n\nSANDRA LUZ PERALTA GÓMEZ\nRUBÉN DARÍO SALGADO FRÍAS\n\nIMV\nINDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V.",
     ["SANDRA LUZ PERALTA GÓMEZ", "RUBÉN DARÍO SALGADO FRÍAS"]),
    ("tiempo extra.\nNorma Elena Villagrán Soto\nCuentas por Pagar", ["Norma Elena Villagrán Soto"]),
])
def test_nombre_de_pila_sin_contexto(texto, esperado):
    assert [h.valor for h in detectar(texto, usar_ner=False) if h.tipo == "NOMBRE"] == esperado


@pytest.mark.parametrize("texto", ["Santa María la Ribera", "Avenida Juan Pablo II", "Escuela Benito Juárez",
                                   "Alcaldía Miguel Hidalgo", "Juzgado Décimo Séptimo Laboral", "pago de SALARIOS VENCIDOS",
                                   "Col. Guadalupe Tepeyac", "At'n: Gerencia"])
def test_lugares_y_terminos_no_son_personas(texto):
    assert not any(h.tipo == "NOMBRE" for h in detectar(texto))


def test_empresa_no_se_traga_las_firmas_de_arriba():
    t = "TESTIGO\n\nSANDRA LUZ PERALTA GÓMEZ\n\nIMV\nINDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V."
    empresas = [h.valor for h in detectar(t, usar_ner=False) if h.tipo == "EMPRESA"]
    assert empresas == ["INDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V."]


@pytest.mark.parametrize("texto", [
    "QUE CELEBRAN, POR UNA PARTE, INDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V., REPRESENTADA",
    "Gerencia de Recursos Humanos de INDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V., ubicada",
    "Empresa: INDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V. · Sucursal",
])
def test_empresa_no_arrastra_lo_que_la_antecede(texto):
    empresas = [h.valor for h in detectar(texto, usar_ner=False) if h.tipo == "EMPRESA"]
    assert empresas == ["INDUSTRIAS METÁLICAS DEL VALLE, S.A. DE C.V."]


def test_letras_espaciadas_no_son_empresa():
    t = "D E C L A R A C I O N E S\n\nP R E S T A C I O N E S"
    assert not [h for h in detectar(t, usar_ner=False) if h.tipo == "EMPRESA"]


@pytest.mark.parametrize("valor,esperado", [
    ("Juan Pérez García", True), ("JUAN PÉREZ", True), ("María de la Luz", True), ("O'Higgins", True),
    ("WQZ4+cKaozuu", False), ("P382W", False), ("CNC-2026-031877", False), ("VjIAMLggpkw9qW", False),
])
def test_filtro_de_nombres_del_modelo(valor, esperado):
    from anonimizador.detector.nombres import _parece_nombre_escrito

    assert _parece_nombre_escrito(valor) is esperado


def test_trozos_cubren_todo_y_cortan_en_parrafo():
    from anonimizador.detector.nombres import _trozos

    texto = ("Párrafo con el C. Juan Pérez García.\n\n" * 5000)
    trozos = list(_trozos(texto, tam=10_000))
    assert "".join(t for _, t in trozos) == texto
    assert all(t.endswith("\n") for _, t in trozos[:-1])
    assert all(texto[b:b + len(t)] == t for b, t in trozos)


def test_documento_de_mas_de_un_millon_de_caracteres(monkeypatch):
    """spaCy rechaza textos de más de 1 000 000 de caracteres: nunca le llega uno así."""
    from anonimizador.detector import nombres

    largos = []

    class Doc:
        ents = ()

    monkeypatch.setattr(nombres, "_nlp", lambda: ((lambda t: largos.append(len(t)) or Doc()), set()))
    texto = "Comparece el C. Juan Pérez García ante la autoridad.\n\n" * 22_000  # ~1.2 M
    list(nombres._por_ner(texto))
    assert sum(largos) == len(texto) and max(largos) <= nombres.TROZO_NER
