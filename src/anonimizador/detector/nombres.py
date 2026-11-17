"""Detección de nombres de personas y de empresas.

Combina tres fuentes:
1. Reglas de contexto ("el C.", "promovido por", "por su propio derecho", …).
2. NER de spaCy (opcional: si el modelo no está instalado se usan solo las reglas).
3. Sufijos societarios para empresas ("S.A. de C.V.", "S. de R.L.", "A.C.", …).

Los documentos legales escriben muchos nombres en MAYÚSCULAS, y ahí spaCy falla. Por
eso el texto que ve spaCy se normaliza antes (mismas posiciones, otra capitalización).
"""

from __future__ import annotations

import functools
import re
import unicodedata
from typing import Iterator

from .modelo import EMPRESA, NOMBRE, Hallazgo

# --- vocabulario --------------------------------------------------------------

_MAY = "A-ZÁÉÍÓÚÑÜ"
_MIN = "a-záéíóúñü"

TRATAMIENTOS = {
    "c", "c.", "cc", "cc.", "ciudadano", "ciudadana", "ciudadanos", "ciudadanas",
    "señor", "señora", "señores", "señoras", "señorita", "sr", "sr.", "sra", "sra.",
    "srita", "srita.", "don", "doña", "lic", "lic.", "licenciado", "licenciada",
    "licenciados", "licenciadas", "ing", "ing.", "ingeniero", "ingeniera", "dr", "dr.",
    "dra", "dra.", "doctor", "doctora", "mtro", "mtro.", "mtra", "mtra.", "maestro",
    "maestra", "arq", "arq.", "arquitecto", "arquitecta", "c.p.", "contador", "contadora",
}

# Palabras que, capitalizadas, aparecen en textos jurídicos y no son nombres.
NO_NOMBRE = {
    "usted", "ustedes", "juez", "jueza", "juzgado", "magistrado", "magistrada",
    "ministro", "ministra", "secretario", "secretaria", "secretaría", "notario",
    "notaria", "notaría", "público", "pública", "ministerio", "fiscal", "fiscalía",
    "agente", "actuario", "actuaria", "tribunal", "sala", "pleno", "presidente",
    "presidenta", "actor", "actora", "demandado", "demandada", "quejoso", "quejosa",
    "tercero", "tercera", "interesado", "interesada", "arrendador", "arrendadora",
    "arrendatario", "arrendataria", "vendedor", "vendedora", "comprador", "compradora",
    "comodante", "comodatario", "mandante", "mandatario", "fiador", "fiadora", "deudor",
    "deudora", "acreedor", "acreedora", "patrón", "patrona", "trabajador", "trabajadora",
    "contratante", "contratista", "denominará", "denominara", "denomina", "denominado",
    "denominada", "sucesivo", "objeto", "cláusula", "cláusulas", "contrato", "convenio",
    "declaraciones", "declaración", "antecedentes", "resultando", "resultandos",
    "considerando", "considerandos", "resolutivos", "vistos", "primero", "segundo",
    "tercero", "cuarto", "quinto", "sexto", "único", "primera", "segunda", "cuarta",
    "quinta", "sexta", "única", "artículo", "artículos", "fracción", "código", "ley",
    "constitución", "reglamento", "tesis", "jurisprudencia", "amparo", "juicio",
    "expediente", "toca", "acuerdo", "sentencia", "auto", "demanda", "escrito",
    "federal", "civil", "penal", "mercantil", "laboral", "familiar", "administrativo",
    "estado", "estados", "unidos", "mexicanos", "república", "nación", "ciudad",
    "méxico", "municipio", "alcaldía", "colonia", "calle", "avenida", "parte", "partes",
    "partida", "folio", "registro", "propiedad", "comercio", "derecho", "derechos",
    "atentamente", "protesto", "presente", "conforme", "partido", "distrito",
    # ordinales (juzgados, salas, cláusulas) y términos laborales que spaCy toma por nombres
    "séptimo", "séptima", "octavo", "octava", "noveno", "novena", "décimo", "décima",
    "undécimo", "duodécimo", "vigésimo", "vigésima", "trigésimo", "primer", "tercer",
    "salario", "salarios", "vencidos", "caídos", "prestaciones", "aguinaldo", "vacaciones",
    "prima", "vacacional", "antigüedad", "indemnización", "finiquito", "liquidación",
    "testigo", "testigos", "firma", "firmas", "nombre", "puesto", "hoja", "anexo",
}

# Palabras funcionales: un nombre nunca las contiene (salvo las partículas de apellido).
FUNCIONALES = {
    "que", "por", "para", "una", "uno", "un", "el", "los", "las", "a", "al", "se", "le",
    "les", "lo", "en", "con", "sin", "su", "sus", "quien", "quienes", "cual", "este",
    "esta", "estos", "o", "u", "es", "son", "como", "mi", "mis", "sobre", "ante",
    "desde", "hasta", "entre", "hacia", "otra", "otro", "parte", "y", "e", "no", "si",
    "ya", "muy", "más", "pero", "cuando", "donde", "ni",
}
PARTICULAS = {"de", "del", "la", "las", "los"}

# Nombres de personajes históricos que en México son calles, alcaldías y municipios.
CONMEMORATIVOS = {
    "benito juárez", "miguel hidalgo", "emiliano zapata", "venustiano carranza",
    "gustavo a. madero", "álvaro obregón", "lázaro cárdenas", "vicente guerrero",
    "francisco i. madero", "josé maría morelos", "ignacio zaragoza",
    "adolfo lópez mateos", "miguel hidalgo y costilla", "francisco villa",
    "ignacio allende", "guadalupe victoria", "josé maría pino suárez",
}

# Nombres de pila frecuentes en México (sin acentos, en minúsculas). Sirven para reconocer
# un nombre sin contexto: firmas, bloques de "TESTIGO", tablas ("Nombre | MARÍA ...").
DE_PILA = frozenset("""
abel abigail abraham adela adolfo adrian adriana agustin aida alan alberto alejandra
alejandro alfonso alfredo alicia alma alonso alvaro amanda amelia ana andrea andres
angel angela angelica anselmo antonia antonio araceli ariadna armando arturo aurora
axel barbara beatriz benjamin bernardo berenice blanca brenda carla carlos carmen
carolina catalina cecilia cesar christian cinthia claudia concepcion consuelo cristina
cristian cynthia daniel daniela dario david debora diana diego dolores dulce edgar
eduardo efrain elena elias elisa elizabeth elsa elvira emilio emma enrique erick
erika ernesto esperanza esteban estela esther eugenia eva evelyn everardo fabiola
fatima federico felipe fernanda fernando francisca francisco gabriel gabriela gerardo
german gilberto gloria graciela gregorio guadalupe guillermo gustavo hector heriberto
hilda horacio hugo humberto ignacio ileana irene iris irma isaac isabel ismael israel
itzel ivan ivonne jacqueline jaime javier jazmin jesus jessica joaquin jonathan jorge
jose josefina juan juana julia julian julio karen karina karla laura leonardo leticia
lidia liliana lizbeth lorena lourdes lucia luis luisa luz magdalena manuel marco marcos
margarita maria mariana maricela mario marisol marta martha martin mateo mauricio
maximiliano mayra melissa mercedes miguel minerva miriam mirna monica nadia natalia
nayeli nelly nicolas noe noemi norma octavio olga omar orlando oscar pablo paola
patricia paula paulina pedro perla pilar rafael ramiro ramon raquel raul rebeca
regina reyna ricardo roberto rocio rodolfo rodrigo rogelio rolando rosa rosalba
rosario ruben ruth salvador samuel sandra santiago sara sergio silvia sofia sonia
susana tania teresa tomas ulises valentina valeria vanessa veronica vicente victor
victoria virginia ximena yazmin yolanda yolotl zaira
""".split())


AUTORIDADES = re.compile(
    r"\b(?:juzgado|tribunal|suprema\s+corte|sala|pleno|ministerio\s+p[uú]blico|fiscal[ií]a|"
    r"secretar[ií]a|procuradur[ií]a|instituto|servicio\s+de\s+administraci[oó]n|congreso|"
    r"c[aá]mara|poder\s+judicial|gobierno|ayuntamiento|municipio|comisi[oó]n|consejo|junta|"
    r"centro\s+federal|registro\s+p[uú]blico|notar[ií]a|universidad|banco\s+de\s+m[eé]xico|"
    r"imss|issste|infonavit|sat|condusef|profeco|scjn)\b",
    re.IGNORECASE,
)

# --- reglas de contexto -------------------------------------------------------

_PALABRA_NOMBRE = rf"(?:[{_MAY}][{_MIN}]+|[{_MAY}]{{2,}})(?:-[{_MAY}][{_MIN}]+)?"
_PARTICULA = r"(?:de[^\S\n]+la|de[^\S\n]+las|de[^\S\n]+los|del|de|la|DE[^\S\n]+LA|DE[^\S\n]+LAS|DE[^\S\n]+LOS|DEL|DE|LA)"
_ESP = r"[^\S\n]+"  # espacio sin salto de línea: un nombre no cruza párrafos
_NOMBRE = rf"(?-i:{_PALABRA_NOMBRE}(?:{_ESP}(?:{_PARTICULA}{_ESP})?{_PALABRA_NOMBRE}){{1,5}})"

_TRAT_RE = (
    r"(?:C\.|CC\.|ciudadan[oa]s?|se[ñn]or(?:a|es|as)?|srita\.|sra?\.|don|doña|lic\.|"
    r"licenciad[oa]s?|ing\.|ingenier[oa]s?|dra?\.|doctor(?:a|es)?|mtr[oa]\.|maestr[oa]|"
    r"arq\.|arquitect[oa])"
)
_ANTES = (
    rf"\b(?:{_TRAT_RE}|promovid[oa]s?\s+por|en\s+contra\s+de|contra|demandad[oa]s?|"
    r"representad[oa]s?\s+por|por\s+conducto\s+de|a\s+favor\s+de|de\s+nombre|"
    r"(?:el|la|los|las|del|al)\s+(?:actor|actora|demandad[oa]s?|quejos[oa]s?|testigos?|albacea|"
    r"apoderad[oa]s?|trabajador(?:a|es)?|arrendador(?:a)?|arrendatari[oa]|vendedor(?:a)?|"
    r"comprador(?:a)?|deudor(?:a)?|acreedor(?:a)?|fiador(?:a)?|menor|finad[oa]|de\s+cujus|"
    r"autor(?:a)?\s+de\s+la\s+sucesi[oó]n|occis[oa]|v[ií]ctima|imputad[oa]|ofendid[oa]|"
    r"inculpad[oa]|sentenciad[oa]|procesad[oa]|c[oó]nyuge|espos[oa]|hij[oa]s?|"
    r"heredero(?:a|s)?|legatari[oa]|tutor(?:a)?|perit[oa])|"
    r"apoderad[oa]\s+(?:legal\s+)?de|que\s+celebran\s+(?:por\s+una\s+parte\s+)?)"
)

_RE_ANTES = re.compile(rf"{_ANTES}(?:(?<=\.)|\b)\s*,?\s*({_NOMBRE})", re.IGNORECASE)
_RE_LISTA = re.compile(rf"\s*,?\s+(?:y|e)\s+({_NOMBRE})")
_RE_DESPUES = re.compile(rf"({_NOMBRE})\s*,?\s+por\s+(?:su|mi|sus)\s+propi[oa]s?\s+derechos?", re.IGNORECASE)


def _palabras(valor: str) -> list[str]:
    return re.findall(rf"[{_MAY}{_MIN}.\-'’]+", valor)  # el apóstrofo no parte la palabra (At'n)


def _es_nombre_plausible(valor: str) -> bool:
    palabras = [p for p in _palabras(valor) if p.lower() not in {"de", "del", "la", "las", "los", "y"}]
    if len(palabras) < 2:
        return False
    if any(p.lower().strip(".") in NO_NOMBRE or p.lower() in NO_NOMBRE for p in palabras):
        return False
    if valor.lower() in CONMEMORATIVOS or AUTORIDADES.search(valor):
        return False
    return True


def _palabra_de_nombre(p: str) -> bool:
    base = p.lower().strip(".,")
    return (
        p[:1].isupper()
        and base not in NO_NOMBRE
        and base not in FUNCIONALES
        and p.lower() not in TRATAMIENTOS
    )


def _limpia(texto: str, inicio: int, fin: int) -> tuple[int, int] | None:
    """Recorta el tramo al nombre propiamente dicho. None si no queda un nombre.

    Quita tratamientos iniciales ("Lic.", "el C."), y corta en la primera palabra que
    no puede ser parte de un nombre ("… GARCÍA QUE CELEBRAN", "… Valdés desde").
    """
    tokens = [(m.start() + inicio, m.end() + inicio, m.group())
              for m in re.finditer(r"\S+", texto[inicio:fin])]
    i = 0
    while i < len(tokens) and (tokens[i][2].lower() in TRATAMIENTOS or not _palabra_de_nombre(tokens[i][2])):
        i += 1
    elegidos: list[tuple[int, int, str]] = []
    pendientes: list[tuple[int, int, str]] = []  # partículas a la espera de un apellido
    for tok in tokens[i:]:
        palabra = tok[2]
        anterior = (pendientes or elegidos)[-1] if (pendientes or elegidos) else None
        if anterior is not None and "\n" in texto[anterior[1]:tok[0]]:
            break  # un nombre no cruza un salto de línea o de párrafo
        limpia = palabra.rstrip(",.;:")
        if limpia.lower() in PARTICULAS and elegidos:
            pendientes.append(tok)
            continue
        if not _palabra_de_nombre(limpia):
            break
        elegidos += pendientes + [tok]
        pendientes = []
        if limpia != palabra:  # la coma o el punto cierran el nombre
            break
    if not elegidos:
        return None
    ini, fin = elegidos[0][0], elegidos[-1][1]
    while fin > ini and texto[fin - 1] in " ,;:":
        fin -= 1
    if texto[fin - 1] == "." and not re.search(r"\b[A-ZÁÉÍÓÚÑ]\.$", texto[ini:fin]):
        fin -= 1  # punto final de oración, no de inicial ("Francisco I.")
    return (ini, fin) if _es_nombre_plausible(texto[ini:fin]) else None


def _sin_acentos(p: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", p.lower()) if not unicodedata.combining(c))


_RE_NOMBRE_LIBRE = re.compile(_NOMBRE)
# Un nombre de pila después de estas palabras suele ser un lugar, no una persona.
_LUGAR_ANTES = re.compile(
    r"\b(?:san|santa|santo|santos|av|avenida|calle|calz|calzada|cerrada|privada|prolongaci[oó]n|"
    r"boulevard|blvd|bulevar|eje|perif[eé]rico|circuito|andador|callej[oó]n|paseo|retorno|col|colonia|"
    r"fraccionamiento|fracc|barrio|pueblo|unidad|parque|plaza|jard[ií]n|mercado|escuela|colegio|"
    r"instituto|hospital|cl[ií]nica|sanatorio|templo|parroquia|iglesia|estadio|teatro|museo|"
    r"metro|estaci[oó]n|puente|presa|fundaci[oó]n|premio|beca|programa)\.?[^\S\n]+$",
    re.IGNORECASE,
)
_ROMANO_FINAL = re.compile(r"\s+[IVXL]+$")


def _por_nombre_de_pila(texto: str) -> Iterator[tuple[int, int]]:
    """Secuencias que empiezan con un nombre de pila conocido y siguen con otra palabra
    de nombre ("SANDRA LUZ PERALTA GÓMEZ", "Norma Elena Villagrán Soto")."""
    for m in _RE_NOMBRE_LIBRE.finditer(texto):
        for w in re.finditer(r"\S+", m.group()):
            if _sin_acentos(w.group().strip(".,")) in DE_PILA:
                ini = m.start() + w.start()
                if len(texto[ini:m.end()].split()) >= 2:
                    yield ini, m.end()
                break


def _parece_lugar(texto: str, ini: int, fin: int) -> bool:
    """Escuela Benito Juárez, Avenida Juan Pablo II, Santa María la Ribera…"""
    valor = texto[ini:fin]
    if _LUGAR_ANTES.search(texto[max(0, ini - 30):ini]) or _ROMANO_FINAL.search(valor):
        return True
    primera, _, resto = valor.partition(" ")
    if _LUGAR_ANTES.search(primera + " "):
        return True
    bajo = valor.lower()
    return any(bajo.endswith(c) for c in CONMEMORATIVOS) and len(resto.split()) <= 3


def _por_reglas(texto: str) -> Iterator[tuple[int, int]]:
    yield from _por_nombre_de_pila(texto)
    for m in _RE_ANTES.finditer(texto):
        yield m.start(1), m.end(1)
        pos = m.end(1)
        while (sig := _RE_LISTA.match(texto, pos)) is not None:  # "señores X y Y"
            yield sig.start(1), sig.end(1)
            pos = sig.end(1)
    for m in _RE_DESPUES.finditer(texto):
        yield m.start(1), m.end(1)


# --- spaCy --------------------------------------------------------------------

_RE_TRAMO_MAYUS = re.compile(rf"\b[{_MAY}]{{2,}}(?:[\s,.\-]+[{_MAY}]+)+\b")
_RE_PALABRA_MAYUS = re.compile(rf"[{_MAY}]+")


@functools.lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy
        from spacy.lang.es.stop_words import STOP_WORDS
    except ImportError:
        return None
    try:
        nlp = spacy.load(
            "es_core_news_md",
            exclude=["parser", "lemmatizer", "morphologizer", "attribute_ruler", "senter"],
        )
    except OSError:
        return None
    nlp.max_length = 5_000_000
    return nlp, STOP_WORDS


def ner_disponible() -> bool:
    return _nlp() is not None


def normaliza_mayusculas(texto: str, stop_words) -> str:
    """Tramos en MAYÚSCULAS → Título, con palabras funcionales en minúscula.

    Conserva la longitud exacta del texto para que las posiciones sigan valiendo.
    """

    def palabra(m: re.Match) -> str:
        w = m.group()
        return w.lower() if w.lower() in stop_words else w.capitalize()

    def tramo(m: re.Match) -> str:
        nuevo = _RE_PALABRA_MAYUS.sub(palabra, m.group())
        return nuevo if len(nuevo) == len(m.group()) else m.group()

    return _RE_TRAMO_MAYUS.sub(tramo, texto)


def _por_ner(texto: str) -> Iterator[tuple[int, int]]:
    cargado = _nlp()
    if cargado is None:
        return
    nlp, stop_words = cargado
    normal = normaliza_mayusculas(texto, stop_words)
    for base, trozo in _trozos(normal):
        for ent in nlp(trozo).ents:
            ini, fin = base + ent.start_char, base + ent.end_char
            if ent.label_ == "PER" and _parece_nombre_escrito(texto[ini:fin]):
                yield ini, fin


TROZO_NER = 100_000  # spaCy no acepta más de 1 000 000 de caracteres por llamada (y la memoria crece)


def _trozos(texto: str, tam: int = TROZO_NER) -> Iterator[tuple[int, str]]:
    """Corta en un salto de párrafo (o de línea) para no partir un nombre a la mitad."""
    i = 0
    while i < len(texto):
        fin = min(len(texto), i + tam)
        if fin < len(texto):
            corte = texto.rfind("\n\n", i + tam // 2, fin)
            if corte == -1:
                corte = texto.rfind("\n", i + tam // 2, fin)
            fin = corte + 1 if corte != -1 else fin
        yield i, texto[i:fin]
        i = fin


# Cada palabra: "Pérez", "PÉREZ", "de", "O'Higgins". Fuera cadenas internas de los PDF
# ("WQZ4+cKaozuu", "P382W") y folios ("CNC-2026-031877") que el modelo toma por personas.
_RE_PALABRA_NOMBRE = re.compile(r"[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]*(?:['-][A-ZÁÉÍÓÚÑa-záéíóúñü]+)+|[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+(?:['-][A-ZÁÉÍÓÚÑa-záéíóúñü]+)*|[A-ZÁÉÍÓÚÑÜ'-]{2,}|[a-z]{1,3}\.?")


def _parece_nombre_escrito(valor: str) -> bool:
    palabras = valor.split()
    return bool(palabras) and all(_RE_PALABRA_NOMBRE.fullmatch(p.strip(".,")) for p in palabras) \
        and any(len(p) >= 3 for p in palabras)


# --- empresas -----------------------------------------------------------------

_SUFIJO = (
    r"S\.?\s?A\.?\s?P\.?\s?I\.?(?:\s+de\s+C\.?\s?V\.?)?|S\.?\s?A\.?\s?B\.?(?:\s+de\s+C\.?\s?V\.?)?|"
    r"S\.?\s?A\.?(?:\s+de\s+C\.?\s?V\.?)?|S\.?\s+de\s+R\.?\s?L\.?(?:\s+de\s+C\.?\s?V\.?)?|"
    r"S\.?\s?A\.?\s?S\.?|S\.?\s?C\.?|A\.?\s?C\.?|I\.?\s?A\.?\s?P\.?|S\.?\s?N\.?\s?C\.?"
)
_RE_SUFIJO = re.compile(rf",?\s+(?:{_SUFIJO})(?![A-Za-z])", re.IGNORECASE)
_CONECTORES_EMPRESA = {"de", "del", "la", "las", "los", "y", "e", "el", "en"}
# Palabras que, escritas en mayúsculas, anteceden a la razón social sin ser parte de ella
# ("QUE CELEBRAN, POR UNA PARTE, INDUSTRIAS…", "Gerencia de Recursos Humanos de INDUSTRIAS…").
_ANTES_DE_EMPRESA = {
    "que", "celebran", "celebra", "por", "una", "otra", "parte", "partes", "entre", "con", "ante", "contra",
    "gerencia", "direccion", "departamento", "area", "recursos", "humanos", "empresa", "patron",
    "persona", "citada", "citado", "demandada", "demandado", "actora", "presente", "representada",
    "c", "cc", "lic", "sr", "sra", "ing", "at'n", "atn",
}


def _empresas(texto: str) -> Iterator[tuple[int, int]]:
    for m in _RE_SUFIJO.finditer(texto):
        # Camina hacia atrás por palabras capitalizadas (y conectores entre ellas).
        palabras = list(re.finditer(r"\S+", texto[max(0, m.start() - 200):m.start()]))
        base = max(0, m.start() - 200)
        inicio = None
        for p in reversed(palabras):
            w = p.group().strip(",")
            if "\n" in texto[base + p.end():m.start()]:
                break  # la razón social no cruza un salto de línea (si no, se traga firmas)
            if w.endswith(":") or _sin_acentos(w).strip(".:,") in _ANTES_DE_EMPRESA:
                break
            if w[:1].isupper() or w[:1].isdigit() or w in {"&"}:
                inicio = base + p.start()
            elif w.lower() in _CONECTORES_EMPRESA and inicio is not None:
                continue
            else:
                break
        if inicio is None:
            continue
        # No empezar con conector.
        while (c := re.match(r"(\S+)\s+", texto[inicio:m.start()])) and c.group(1).lower() in _CONECTORES_EMPRESA:
            inicio += c.end()
        if not re.search(r"\w{3}", texto[inicio:m.start()]):
            continue  # "D E C L A R A C I O N E S": letras sueltas, el "A C" no es un sufijo
        if not AUTORIDADES.match(texto[inicio:m.end()]):
            yield inicio, m.end()


# --- API ----------------------------------------------------------------------


def detectar_nombres(texto: str, usar_ner: bool = True) -> list[Hallazgo]:
    hallazgos: list[Hallazgo] = []
    for ini, fin in _empresas(texto):
        hallazgos.append(Hallazgo(EMPRESA, texto[ini:fin], ini, fin))
    fuentes = list(_por_reglas(texto))
    if usar_ner:
        fuentes += list(_por_ner(texto))
    vistos = set()
    for ini, fin in fuentes:
        limpio = _limpia(texto, ini, fin)
        if limpio and _parece_lugar(texto, *limpio):
            continue
        if limpio and limpio not in vistos:
            vistos.add(limpio)
            hallazgos.append(Hallazgo(NOMBRE, texto[limpio[0]:limpio[1]], *limpio))
    return hallazgos
