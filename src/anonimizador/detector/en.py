"""Paquete de inglés: documentos de EE. UU. y Reino Unido, y traducciones al inglés de documentos
checos (lo que recibe un traductor checo-inglés: personas, rodné číslo e IČO checos en inglés).

Personas: el modelo en_core_web de spaCy + reglas (tratamientos, nombres de pila conocidos,
rótulos como "Name:" o "Tenant:"). Lo demás, con patrones y dígitos de control.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from . import cs, patrones
from . import validadores as v
from .modelo import (CORREO, CUENTA, DOMICILIO, EMPRESA, EXPEDIENTE, FECHA, FOLIO, ICO, MONTO, NINO, NOMBRE, PLACA,
                     SSN, TARJETA, TELEFONO, WEB, Hallazgo)

AQUI = Path(__file__).parent
MAY = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽÄÖÜÀÂÇÈÊËÎÏÔÙÛŁŚŻŹĆŃ"
MIN = "a-záčďéěíňóřšťúůýžäöüßàâçèêëîïôùûłśżźćń"
# "Smith", "O'Brien", "McDonald", "Nováková", "Smith-Jones"
APELLIDO = rf"(?:O'|D'|Mc|Mac)?[{MAY}][{MIN}]+(?:-[{MAY}][{MIN}]+)?"
PALABRA_MAYUS = rf"[{MAY}][{MAY}'\-]+"  # SMITH en encabezados y firmas
_I = re.IGNORECASE

TRATAMIENTOS = (r"Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Sir|Dame|Lord|Lady|Rev|Judge|Justice|Hon|"
                r"Mgr|Ing|JUDr|MUDr|MVDr|PhDr|RNDr|PaedDr|Bc|doc|MgA|BcA|Ph\.D")


@lru_cache(maxsize=1)
def _nombres() -> tuple[frozenset[str], frozenset[str]]:
    """(nombres de pila conocidos, ambiguos). Incluye los checos en nominativo."""
    d = json.loads((AQUI / "datos_en" / "nombres.json").read_text(encoding="utf-8"))
    pila = set(d["masculinos"]) | set(d["femeninos"])
    checos = json.loads((AQUI / "datos_cs" / "nombres.json").read_text(encoding="utf-8"))
    pila |= {fila["nom"] for g in checos.values() for fila in g["jmena"]}
    ambiguos = set(d["ambiguos"]) | cs.AMBIGUOS
    return frozenset(pila), frozenset(ambiguos)


@lru_cache(maxsize=1)
def _nlp():
    try:
        import spacy
    except ImportError:
        return None
    import os

    preferido = os.environ.get("ANONIMIZADOR_MODELO_EN")
    for nombre in ([preferido] if preferido else []) + ["en_core_web_md", "en_core_web_sm"]:
        try:
            nlp = spacy.load(nombre, exclude=["parser", "lemmatizer", "attribute_ruler", "tagger", "senter"])
        except OSError:
            continue
        nlp.max_length = 5_000_000
        return nlp
    return None


def modelo_disponible() -> bool:
    return _nlp() is not None


# --- personas ---------------------------------------------------------------------

_NO_PERSONA = {
    # Palabras que el modelo a veces toma por nombres o que arrancan una frase.
    "Dear", "Re", "Attn", "Date", "Signed", "Signature", "Witness", "Tenant", "Landlord", "Employer", "Employee",
    "Seller", "Buyer", "Client", "Patient", "Court", "Plaintiff", "Defendant", "Claimant", "Respondent", "Petitioner",
    "Applicant", "Notary", "Translator", "Registrar", "Mother", "Father", "Child", "Husband", "Wife", "Party",
    "Parties", "Agreement", "Contract", "Section", "Article", "Clause", "Schedule", "Annex", "Exhibit", "Page",
    "Total", "Amount", "Address", "Birth", "Name", "Surname", "Republic", "Czech", "Prague", "Praha", "Brno",
    "Ostrava", "District", "Regional", "Municipal", "Office", "Ministry", "Police", "Hospital", "University",
    "Faculty", "Street", "Road", "Avenue", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday",
    "Sunday", "January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
    "November", "December", "Hereinafter", "Whereas", "Witnesseth", "Company", "Ltd", "Limited", "Inc", "LLC",
    "Stamp", "Seal", "Sincerely", "Regards", "Kind", "Best", "Yours", "Thank", "Thanks", "Hello", "Hi",
    "God", "Christ", "Jesus", "Holy", "Saint", "St", "Lord", "Lady",
    "Passport", "No", "Number", "ID", "Tel", "Phone", "Email", "E-mail", "Mobile", "Fax", "Born", "Dated", "Date",
    "SSN", "NI", "Account", "Sort", "Code", "Ref", "Reference", "Case", "Licence", "License", "Card", "Policy",
    "Coll", "Sb", "Public", "Dean", "Vice-Dean", "Rector", "Executor", "Executrix", "Trustee", "Affiant", "Deponent",
    "Registry", "Register", "Municipal", "Town", "Hall", "Biennale", "Gallery", "Museum", "Theatre", "Festival",
}
try:
    from spacy.lang.en.stop_words import STOP_WORDS as _STOP
except ImportError:  # sin spaCy: lo mínimo
    _STOP = {"the", "a", "an", "and", "or", "of", "in", "on", "at", "by", "for", "to", "this", "that", "with", "from"}
PALABRAS_FUNCIONALES = frozenset(w.lower() for w in _STOP)
_INSTITUCION = {"University", "Bridge", "Square", "Street", "Avenue", "Hospital", "School", "College", "Institute",
                "Hall", "Park", "Museum", "Gallery", "Theatre", "Foundation", "Prize", "Award", "Station", "Airport",
                "Stadium", "Centre", "Center", "Library", "Road", "Lane", "Embankment", "Quay", "Gymnasium", "Faculty",
                "Palace", "Castle", "Cathedral", "Church", "Monastery", "River", "Lake", "Mountains", "Region"}
# Lugares checos que el modelo inglés toma por personas.
_LUGARES = {
    "Vltava", "Vltavou", "Vltavy", "Labe", "Morava", "Moravia", "Bohemia", "Silesia", "Šumava", "Krkonoše", "Jeseníky",
    "Telč", "Poruba", "Karlštejn", "Hradčany", "Vyšehrad", "Rudolfinum", "Petřín", "Smíchov", "Žižkov", "Vinohrady",
    "Karlín", "Holešovice", "Dejvice", "Letná", "Kampa", "Lednice", "Kutná Hora", "Třeboň", "Mikulov", "Znojmo",
    "Olomouc", "Ostrava", "Plzeň", "Liberec", "Pardubice", "Zlín", "Jihlava", "Kladno", "Opava", "Tábor", "Písek",
    "Brno", "Praha", "Prague", "Karlovy Vary", "České Budějovice", "Hradec Králové", "Ústí nad Labem", "Český Krumlov",
}
# "Charles University", "Masaryk Hospital": el nombre es parte de una institución o un lugar.
_SIGUE_INSTITUCION = re.compile(r"^[ \t]+(?:University|Bridge|Square|Street|Avenue|Hospital|School|College|Institute|"
                                r"Hall|Park|Museum|Gallery|Theatre|Foundation|Prize|Award|Station|Airport|Stadium|Centre|"
                                r"Center|Library|Road|Lane|Embankment|Quay|Gymnasium|Grammar|Faculty)\b")
_ROMANO = re.compile(r"^(?:[IVX]+|\d+)\.$")
_ROTULO = re.compile(
    r"(?:^|\n)[ \t]*(?:full\s+)?(?:name(?:\s+and\s+surname)?|surname|first\s+name|given\s+names?|patient|employee|"
    r"tenant|landlord|applicant|claimant|defendant|plaintiff|witness|child|mother|father|husband|wife|seller|buyer|"
    r"client|signed|signature|print\s+name|attention|attn|to|from|deceased|testator|beneficiary|guardian|"
    r"statutory\s+representative|managing\s+director|director|executive|authorised\s+person|translator|"
    r"jméno(?:\s+a\s+příjmení)?|příjmení)\s*[:\-–][ \t]*",
    _I,
)
_NOMBRE_TRAS_ROTULO = re.compile(
    rf"(?:(?:{TRATAMIENTOS})\.?[ \t])*((?:{APELLIDO}|{PALABRA_MAYUS}|[{MAY}]\.)(?:[ \t](?:{APELLIDO}|{PALABRA_MAYUS}|[{MAY}]\.|"
    rf"van|von|de|der|da|di|del|la|le)){{1,4}})"
)
_RE_TRATAMIENTO = re.compile(
    rf"(?<![\w.])(?:{TRATAMIENTOS})\.?(?:,?[ \t](?:{TRATAMIENTOS})\.?)*[ \t]"
    rf"((?:[{MAY}]\.[ \t]?)*(?:{APELLIDO}|{PALABRA_MAYUS})(?:[ \t](?:[{MAY}]\.[ \t]?)*(?:{APELLIDO}|{PALABRA_MAYUS})){{0,3}})"
)
# Rótulos que llevan SOLO un nombre (aunque sea de una palabra): "Surname: Černý", "| First name(s) | Tadeáš |".
_ROTULO_NOMBRE = re.compile(
    r"(?:^|\n|\|)[ \t]*(?:\d+(?:\.\d+)*\.?[ \t]+)?(?:(?:full|first|given|maiden|birth|family|middle|child's|father's|mother's|spouse's|"
    r"previous|former)\s+)?(?:name|names|name\(s\)|surname|forenames?|first\s+names?(?:\(s\))?|"
    r"name\s+of\s+(?:the\s+)?(?:child|father|mother|deceased|holder|applicant))[ \t]*(?:[:\-–|][ \t]*)",
    _I,
)
_UN_NOMBRE = re.compile(rf"(?:(?:{TRATAMIENTOS})\.?[ \t])*((?:{APELLIDO}|{PALABRA_MAYUS})(?:[ \t](?:{APELLIDO}|{PALABRA_MAYUS}|[{MAY}]\.)){{0,3}})"
                        rf"(?=[ \t]*(?:\||\n|,|;|$|\())")
_RE_DECLARA = re.compile(
    rf"(?:\b(?:[Mm]y\s+name\s+is|personally\s+appeared|appeared\s+before\s+me|undersigned|known\s+as|"
    rf"[Ii]ssued\s+to|[Ss]igned\s+by|[Pp]repared\s+by|[Ii]nstructed\s+by|[Rr]epresented\s+by|[Ss]ubmitted\s+by)|"
    rf"(?:^|\n)[ \t]*I,)[ \t]+((?:{APELLIDO}|{PALABRA_MAYUS})(?:[ \t](?:{APELLIDO}|{PALABRA_MAYUS}|[{MAY}]\.)){{1,3}})"
)
_RE_CALIDAD = re.compile(rf"((?:{APELLIDO}|{PALABRA_MAYUS})(?:[ \t](?:{APELLIDO}|{PALABRA_MAYUS}|[{MAY}]\.)){{1,3}}),[ \t]*"
                         r"(?:Affiant|Deponent|Declarant|Applicant|Claimant|Testator|Testatrix|Executor|Notary\s+Public|"
                         r"Sworn\s+translator|Court\s+interpreter|Attorney|Solicitor|Director|Witness|Principal|Agent)\b")
_RE_INICIALES = re.compile(rf"(?<![\w.])[{MAY}]\.[ ]?[{MAY}]\.(?:[ ]?[{MAY}]\.)?(?![\w])")
# Siglas de dos letras con punto que no son iniciales de una persona (con espacio, "A. D.", sí lo son).
_NO_INICIALES = {"U.S.", "U.K.", "P.O.", "E.U.", "A.M.", "P.M.", "N.B.", "I.E.", "E.G.", "R.I.P.", "S.A.", "N.V.", "B.V.",
                 "L.P.", "C.V.", "D.C.", "N.Y.", "L.A.", "U.N."}
_RE_SALUDO = re.compile(rf"\bDear[ \t]+((?:{APELLIDO})(?:[ \t]+{APELLIDO}){{0,2}})[,:!]")
_RE_FIRMA_POSGRADO = re.compile(rf"((?:{APELLIDO})(?:[ \t]+{APELLIDO}){{1,3}}),?[ \t]+(?:Ph\.?D\.?|CSc\.|MBA|LL\.?M\.?|Esq\.?|MD|DiS\.)")


def _corta_no_persona(texto: str, a: int, b: int) -> tuple[int, int] | None:
    """Quita del borde palabras que no son nombre ("Tenant John Smith" → "John Smith") y corta
    en la primera que aparezca en medio ("John Smith Passport No" → "John Smith")."""
    palabras = list(re.finditer(r"\S+", texto[a:b]))
    def fuera(w: str) -> bool:
        if re.fullmatch(rf"[{MAY}]\.,?", w):
            return False  # una inicial ("A.", "I."), no el artículo "a"
        w = w.strip(".,:;'’")
        return w in _NO_PERSONA or w.lower() in PALABRAS_FUNCIONALES

    def numeral(i: int) -> bool:  # "I. The…", pero no la "V." de "V. P."
        return bool(_ROMANO.match(palabras[i].group())) and not (
            i + 1 < len(palabras) and re.fullmatch(rf"[{MAY}]\.", palabras[i + 1].group()))

    while palabras and (fuera(palabras[0].group()) or numeral(0)):
        palabras.pop(0)
    for i, p in enumerate(palabras[1:], 1):
        w = p.group().strip(".,:;'’")
        if w in _NO_PERSONA or w in _INSTITUCION or re.search(r"\d", w) or (w.islower() and w.lower() in PALABRAS_FUNCIONALES
                                                                            and w not in {"van", "von", "de", "der", "da", "di", "la", "le"}):
            palabras = palabras[:i]
            break
    while palabras and palabras[0].group().strip(".,:;'’") in _NO_PERSONA:
        palabras.pop(0)
    while palabras and (palabras[-1].group().strip(".,:;") in _NO_PERSONA or palabras[-1].group() in {"and", "&"}):
        palabras.pop()
    if not palabras:
        return None
    ini, fin = a + palabras[0].start(), a + palabras[-1].end()
    valor = texto[ini:fin]
    # Posesivo y puntuación final: "Smith's" → "Smith"
    valor2 = re.sub(r"(?:['’]s|['’])$", "", valor)
    valor2 = valor2.rstrip(",;:") if re.search(rf"(?:^|\s)[{MAY}]\.$", valor2) else valor2.rstrip(".,;:")
    fin = ini + len(valor2)
    ok = re.search(rf"[{MAY}][{MIN}{MAY}]", valor2) or _RE_INICIALES.fullmatch(texto[ini:fin])
    return (ini, fin) if fin > ini and ok else None


def _por_reglas(texto: str) -> list[tuple[int, int]]:
    pila, ambiguos = _nombres()
    tramos = []
    # Nombre de pila conocido + apellido(s): "John Smith", "Jana Nováková", "Mary Ann O'Brien".
    for m in re.finditer(rf"(?<![\w.'])({APELLIDO})((?:[ \t](?:[{MAY}]\.|{APELLIDO})){{1,3}})", texto):
        primero = m.group(1)
        if primero not in pila or primero in ambiguos:
            continue
        tramos.append((m.start(), m.end()))
    for m in re.finditer(rf"(?<![\w.'’-])[{MAY}][{MIN}]+(?![\w'’-])", texto):
        w = m.group()
        if w in pila and w not in ambiguos and w.lower() not in PALABRAS_FUNCIONALES and len(w) >= 4:
            tramos.append((m.start(), m.end()))  # "Hynek was thrilled", "Zuzana, trainee"
    for m in re.finditer(rf"(?<![\w.'])({PALABRA_MAYUS})((?:[ \t]{PALABRA_MAYUS}){{1,2}})(?![\w])", texto):
        if m.group(1).capitalize() in pila and m.group(1).capitalize() not in ambiguos:
            tramos.append((m.start(), m.end()))
    for rx in (_RE_TRATAMIENTO, _RE_SALUDO, _RE_FIRMA_POSGRADO):
        for m in rx.finditer(texto):
            tramos.append((m.start(1), m.end(1)))
    for m in _ROTULO.finditer(texto):
        n = _NOMBRE_TRAS_ROTULO.match(texto, m.end())
        if n:
            tramos.append((n.start(1), n.end(1)))
    for m in _ROTULO_NOMBRE.finditer(texto):
        n = _UN_NOMBRE.match(texto, m.end())
        if n and n.group(1).strip(".") not in _NO_PERSONA:
            tramos.append((n.start(1), n.end(1)))
    for rx in (_RE_DECLARA, _RE_CALIDAD):
        for m in rx.finditer(texto):
            tramos.append((m.start(1), m.end(1)))
    for m in _RE_INICIALES.finditer(texto):
        if " " in m.group() or m.group().upper() not in _NO_INICIALES:
            tramos.append((m.start(), m.end()))
    return tramos


def _mayusculas_creible(texto: str, a: int, b: int) -> bool:
    """Un nombre en MAYÚSCULAS que dio el modelo: vale si empieza con un nombre de pila conocido o
    si ocupa su renglón (firmas, encabezados de partes) sin pinta de título ("ARTICLE III - …")."""
    valor = texto[a:b]
    palabras = valor.split()
    if not 2 <= len(palabras) <= 4 or not all(re.fullmatch(r"[^\W\d_][^\W\d_'’\-]*", w) for w in palabras):
        return False
    if any(_ROMANO.match(w + ".") or w.capitalize() in _NO_PERSONA or w.capitalize() in _INSTITUCION for w in palabras):
        return False
    if palabras[0].capitalize() in _nombres()[0]:
        return True
    inicio = texto.rfind("\n", 0, a) + 1
    fin = texto.find("\n", b)
    linea = texto[inicio:fin if fin != -1 else len(texto)].strip()
    # En su propio renglón (firma) o en medio de texto normal ("her sister, PHILOMENA NICHOLSON, who…");
    # no en un renglón todo en mayúsculas, que es un título.
    return linea.rstrip(",") == valor or bool(re.search(rf"[{MIN}]", linea))


def personas(texto: str, usar_modelo: bool = True) -> list[Hallazgo]:
    tramos = _por_reglas(texto)
    nlp = _nlp() if usar_modelo else None
    if nlp is not None:
        from .nombres import normaliza_mayusculas

        normal = normaliza_mayusculas(texto, PALABRAS_FUNCIONALES)
        for base, trozo in _trozos(normal):
            for e in nlp(trozo).ents:
                if e.label_ != "PERSON" or "\n" in e.text or not re.search(rf"[{MAY}]", e.text[:1]):
                    continue
                if len(e) == 1 and e.text.isupper():
                    continue  # "BIOGRAPHY", "NOTICE": encabezados; los apellidos en mayúsculas los dan las reglas
                if _SIGUE_INSTITUCION.match(trozo[e.end_char:e.end_char + 20]):
                    continue
                a, b = base + e.start_char, base + e.end_char
                if texto[a:b].isupper() and not _mayusculas_creible(texto, a, b):
                    continue
                tramos.append((a, b))
    salida = []
    for a, b in cs._unir(tramos):
        r = _corta_no_persona(texto, a, b)
        if r is None:
            continue
        valor = texto[r[0]:r[1]]
        if _RE_INICIALES.fullmatch(valor):
            salida.append(Hallazgo(NOMBRE, valor, *r))
            continue
        if valor in _LUGARES or valor.rstrip("'’s") in _LUGARES:
            continue
        siguiente = re.match(r"[ \t]+([A-Z][a-z]+)", texto[r[1]:r[1] + 20])
        if siguiente and siguiente.group(1) in _INSTITUCION:
            continue  # "Charles University", "Masaryk Hospital"
        if len(valor) < 3 or valor.isupper() and len(valor.split()) == 1 and len(valor) <= 4:
            continue  # "USA", "NHS": siglas
        salida.append(Hallazgo(NOMBRE, valor, *r))
    return salida


def _trozos(texto: str, tam: int = 100_000):
    from .nombres import _trozos as t

    return t(texto, tam)


# --- empresas ---------------------------------------------------------------------

_FORMA = (r"(?:Ltd\.?|Limited|LLC|L\.L\.C\.|LLP|L\.L\.P\.|Inc\.?|Incorporated|Corp\.?|Corporation|PLC|plc|"
          r"L\.P\.|LP|GmbH|AG|S\.A\.|N\.V\.|B\.V\.|Pty\.?\s+Ltd\.?|Co\.,?\s+Ltd\.?|& Co\.?|"
          r"spol\.\s?s\s?r\.\s?o\.|s\.\s?r\.\s?o\.|a\.\s?s\.|v\.\s?o\.\s?s\.|k\.\s?s\.|z\.\s?s\.|z\.\s?ú\.|o\.\s?p\.\s?s\.)")
_RE_FORMA = re.compile(rf",?[ \t]+{_FORMA}(?![\w])")
_CONECTORES = {"&", "and", "of", "the", "for", "a", "&amp;", "-", "–", "a.", "und", "et"}
_ANTES = {"between", "by", "with", "from", "to", "at", "for", "and", "the", "company", "employer", "landlord",
          "tenant", "seller", "buyer", "contractor", "client", "supplier", "customer", "party", "of", "in", "on",
          "name", "employed", "works", "worked", "director", "shareholder", "agreement", "contract", "s", "is",
          "was", "\"", "“", "(", "re", "via", "trading", "as", "dear", "společnost", "společnosti", "firma"}


_FORMA_CHECA = re.compile(r"s\.\s?r\.\s?o|a\.\s?s|spol|v\.\s?o\.\s?s|k\.\s?s|z\.\s?s|z\.\s?ú|o\.\s?p\.\s?s")


def empresas(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_FORMA.finditer(texto):
        base = max(0, m.start() - 150)
        palabras = list(re.finditer(r"[^\s]+", texto[base:m.start()]))
        # Las razones sociales checas llevan minúsculas ("Bezpečnostní agentura Štít s.r.o.").
        checa = bool(_FORMA_CHECA.match(m.group().lstrip(", \t")))
        inicio = None
        vistas = 0
        for p in reversed(palabras):
            w = p.group().strip(",“”\"()")
            if "\n" in texto[base + p.end():m.start()] and (inicio is not None or vistas):
                break
            if w.lower().strip(".:") in _ANTES or w.endswith(":") or p.group().endswith((",", ")")) and (inicio is not None or vistas):
                break
            if p.group().endswith(("—", "–")) or w in {"—", "–", "|"}:
                break
            vistas += 1
            if w[:1].isupper() or w[:1].isdigit():
                inicio = base + p.start() + (len(p.group()) - len(p.group().lstrip("“\"(")))
            elif w.lower() in _CONECTORES and inicio is not None:
                continue
            elif checa and w.isalpha() and w.lower() not in PALABRAS_FUNCIONALES and vistas <= 5:
                continue
            else:
                break
        if inicio is None:
            continue
        while (c := re.match(r"(\S+)\s+", texto[inicio:m.start()])) and c.group(1).lower() in _CONECTORES:
            inicio += c.end()
        fin = m.end()
        valor = texto[inicio:fin]
        if re.search(r"\w{2}", texto[inicio:m.start()]):
            yield Hallazgo(EMPRESA, valor, inicio, fin)


# --- identificadores --------------------------------------------------------------

_RE_SSN = re.compile(r"(?<![\d-])(\d{3})[- ](\d{2})[- ](\d{4})(?![\d-])")
_CTX_SSN = re.compile(r"\b(?:SSN|social\s+security(?:\s+(?:no\.?|number|#))?)\s*[:#]?\s*$", _I)
_RE_NUEVE = re.compile(r"(?<![\d-])\d{9}(?![\d-])")


def _ssn_valido(area: str, grupo: str, serie: str) -> bool:
    return area not in {"000", "666"} and not area.startswith("9") and grupo != "00" and serie != "0000"


_RE_NINO = re.compile(r"(?<![A-Z\d])([A-CEGHJ-PR-TW-Z][A-CEGHJ-NPR-TW-Z])[ ]?(\d{2})[ ]?(\d{2})[ ]?(\d{2})[ ]?([A-D])(?![A-Z\d])")
_NINO_NO = {"BG", "GB", "NK", "KN", "TN", "NT", "ZZ"}

# Rótulo + número: pasaporte, licencia, expediente, póliza, referencias…
_ROTULOS_ID = (
    r"passport(?:\s+(?:no\.?|number|#))?|driv(?:ing|er'?s)\s+licen[cs]e(?:\s+(?:no\.?|number|#))?|"
    r"(?:national\s+)?id(?:entity)?\s+card(?:\s+(?:no\.?|number|#))?|id\s+(?:no\.?|number|#)|identity\s+document\s+no\.?|"
    r"personal\s+(?:id|identification)\s+(?:no\.?|number)|"
    r"licen[cs]e\s+(?:no\.?|number|#)|member(?:ship)?\s+(?:id|no\.?|number)|patient\s+(?:id|no\.?|number)|"
    r"nhs\s+(?:no\.?|number)|employee\s+(?:id|no\.?|number)|staff\s+(?:id|no\.?|number)|"
    r"policy\s+(?:no\.?|number|#)|claim\s+(?:no\.?|number|#|reference)|customer\s+(?:no\.?|number|id|reference)|"
    r"(?:our|your)\s+ref(?:erence)?\.?|ref(?:erence)?\.?\s*(?:no\.?|number|#)?|invoice\s+(?:no\.?|number|#)|"
    r"(?:student\s+)?identification\s+(?:no\.?|number)|vat\s+id|tax\s+id|"
    r"(?:translation\s+(?:clause|log)|certified\s+translation|notarial\s+deed|report|police\s+report|register|"
    r"registration|entry|record|deed|log|clause|application|permit|visa|ticket|order|transaction)\s+(?:no\.?|number|#)|"
    r"contract\s+(?:no\.?|number)|certificate\s+(?:no\.?|number)|serial\s+(?:no\.?|number)|"
    r"(?:company\s+)?registration\s+(?:no\.?|number)|reg\.?\s+no\.?|company\s+(?:no\.?|number)|"
    r"(?:ein|tin|itin|employer\s+identification\s+number|tax\s+(?:id|identification|reference)(?:\s+(?:no\.?|number))?|"
    r"utr|vat\s+(?:no\.?|number|reg(?:istration)?\.?\s+no\.?))|"
    r"student\s+(?:id|no\.?|number)|file\s+(?:no\.?|number)|birth\s+certificate\s+(?:no\.?|number)|"
    r"certificate\s+of\s+[a-z]+\s+no\.?|record\s+(?:no\.?|number)|entry\s+no\.?|volume\s+no\.?|"
    r"insurance\s+(?:no\.?|number)|insured\s+person'?s?\s+(?:no\.?|number)|health\s+insurance\s+(?:no\.?|number)|"
    r"case\s+(?:no\.?|number|#)|docket\s+(?:no\.?|number)|index\s+no\.?|file\s+ref\.?|"
    r"(?:court\s+)?ref(?:erence)?\s+(?:mark|no\.?)|ref\.\s+no\.?|reference\s+mark|"
    r"(?:vehicle\s+)?registration\s+(?:mark|plate)|licen[cs]e\s+plate(?:\s+(?:no\.?|number))?|plate\s+(?:no\.?|number)|"
    r"vin|chassis\s+(?:no\.?|number)|plate|registration|variable\s+symbol|specific\s+symbol|"
    r"translation\s+log|(?:divorce|court)\s+(?:decision|judgment)"
)
_RE_ROTULO_ID = re.compile(rf"\b(?i:({_ROTULOS_ID}))(?:\s*,?\s*(?i:no\.?|number|#))?(?:[ \t]+(?i:is|was|will\s+be))?"
                           rf"[ \t]*[:#.(|]?[ \t]*(?:\|[ \t]*)?")
# Número tras un "No." cualquiera ("NOTARIAL DEED\nNo. C85QZ999", "under No. 7 T 221/2024"); no las leyes.
_RE_NO_GENERICO = re.compile(r"(?<!\w)(?:No|no|NO|Nr|nr)\.[ \t]*[:#]?[ \t]*(?=[A-Z0-9]*\d)")
_NO_LEY = re.compile(r"(?:Act|Decree|Regulation|Section|Article|Clause|Item|Annex|Schedule|Law|Directive|Convention|"
                     r"Treaty|Paragraph|Point|Part|Chapter|Rule|Order|Exhibit|Appendix|§)\.?\s*$", _I)
_VALOR_ID = re.compile(r"[A-Z0-9]{1,20}(?:[ /.\-:][A-Z0-9]{1,20}){0,5}")
_CASO = re.compile(r"case|docket|index|file\s+ref|court|ref(?:erence)?\s+mark|ref\.\s+no|divorce", _I)
_PLACA_CTX = re.compile(r"registration\s+(?:mark|plate)|plate|vin|chassis", _I)


def _valor_id(texto: str, pos: int) -> tuple[int, int] | None:
    m = _VALOR_ID.match(texto, pos)
    if not m:
        return None
    valor = m.group()
    # Corta grupos finales sin dígitos que en realidad son palabras ("12345 issued", "AB123 dated").
    partes = re.split(r"([ /.\-:])", valor)
    while len(partes) > 1 and not re.search(r"\d", partes[-1]) and (len(partes[-1]) > 3 or partes[-2] in (" ", ":")):
        partes = partes[:-2]
    valor = "".join(partes).rstrip(" /.-:")
    if not re.search(r"\d", valor) or len(re.sub(r"\W", "", valor)) < 4:
        return None
    return m.start(), m.start() + len(valor)


def _identificadores(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_SSN.finditer(texto):
        if _ssn_valido(*m.groups()) and (m.group().count("-") == 2 or _CTX_SSN.search(texto[max(0, m.start() - 40):m.start()])):
            yield Hallazgo(SSN, m.group(), m.start(), m.end(), True)
    for m in _RE_NUEVE.finditer(texto):
        if _CTX_SSN.search(texto[max(0, m.start() - 40):m.start()]):
            yield Hallazgo(SSN, m.group(), m.start(), m.end())
    for m in _RE_NINO.finditer(texto):
        if m.group(1) not in _NINO_NO:
            yield Hallazgo(NINO, m.group(), m.start(), m.end(), True)
    for m in _RE_ROTULO_ID.finditer(texto):
        r = _valor_id(texto, m.end())
        if r is None:
            continue
        rotulo = m.group(1)
        valor = texto[r[0]:r[1]]
        if rotulo.lower() in ("plate", "registration") and not (re.search(r"[A-Z]", valor) and re.search(r"\d", valor)):
            continue
        tipo = EXPEDIENTE if _CASO.match(rotulo) else PLACA if _PLACA_CTX.search(rotulo) else FOLIO
        yield Hallazgo(tipo, valor, *r)
    for m in _RE_NO_GENERICO.finditer(texto):
        if _NO_LEY.search(texto[max(0, m.start() - 25):m.start()]):
            continue
        r = _valor_id(texto, m.end())
        if r and len(re.sub(r"\W", "", texto[r[0]:r[1]])) >= 5 and not re.match(r"\s*Coll\b", texto[r[1]:r[1] + 6]):
            yield Hallazgo(FOLIO, texto[r[0]:r[1]], *r)
    for m in re.finditer(r"(?<![\d-])\d{2}-\d{7}(?![\d-])", texto):
        if re.search(r"EIN|employer\s+identification|tax\s+id|TIN", texto[max(0, m.start() - 50):m.start()], _I):
            yield Hallazgo(FOLIO, m.group(), m.start(), m.end())
    for m in re.finditer(r"(?<![A-Z0-9])GB[ ]?(?:\d{9}|\d{3} \d{4} \d{2})(?![\d])", texto):
        yield Hallazgo(FOLIO, m.group(), m.start(), m.end())
    # Expedientes de EE. UU. sin rótulo: "No. 2:23-cv-01234", "Civil Action No. 1:22-cv-456".
    for m in re.finditer(r"\b\d:\d{2}-[a-z]{2,4}-\d{3,6}(?:-[A-Z]{2,4})*\b", texto):
        yield Hallazgo(EXPEDIENTE, m.group(), m.start(), m.end())
    # Matrícula británica "AB12 CDE" y checa "1AB 2345".
    for m in re.finditer(r"(?<![\w])[A-Z]{2}\d{2}[ ]?[A-Z]{3}(?![\w])", texto):
        yield Hallazgo(PLACA, m.group(), m.start(), m.end())
    # Checos escritos en inglés.
    yield from cs._rodne_cislo(texto)
    yield from cs._documentos(texto)  # OP, parcelas, matrículas, spisová značka ("27 T 39/2021")
    yield from cs._ico_dic(texto)
    for m in re.finditer(r"(?:company\s+)?(?:id(?:entification)?|reg(?:istration)?|business\s+id)\.?\s+(?:no\.?|number)\s*:?\s*"
                         r"(\d{3}\s?\d{2}\s?\d{3}|\d{8})(?!\d)", texto, _I):
        d = re.sub(r"\D", "", m.group(1))
        if cs._ico_valido(d):
            yield Hallazgo(ICO, m.group(1), m.start(1), m.end(1), True)
    for m in re.finditer(r"(?:birth|personal)\s+(?:no\.?|number|id(?:entification)?\s+(?:no\.?|number))\s*:?\s*(\d{6}\s?/?\s?\d{3,4})(?!\d)",
                         texto, _I):
        yield Hallazgo(cs.RODNE_CISLO, m.group(1), m.start(1), m.end(1), cs._rc_valido(re.sub(r"\D", "", m.group(1))))
    for m in re.finditer(r"\b(?:OP|ID\s+card)\s+(?:No\.?|number)?\s*:?\s*(\d{9})(?!\d)", texto):
        yield Hallazgo(FOLIO, m.group(1), m.start(1), m.end(1))


# --- banco ------------------------------------------------------------------------

_RE_IBAN = re.compile(r"(?<![A-Z0-9])[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]{4}){2,7}(?:[ ]?[A-Z0-9]{1,3})?(?![A-Z0-9])")
_RE_CUENTA_CTX = re.compile(
    r"\b(?i:account(?:\s+(?:no\.?|number|#))?|a/c(?:\s+no\.?)?|acct\.?(?:\s+no\.?)?|sort\s+code|routing(?:\s+(?:no\.?|number))?|"
    r"aba(?:\s+(?:no\.?|number))?|swift(?:/bic)?|bic)[ \t]*[:#.(|]?[ \t]*"
    r"((?=[A-Z0-9 \-/]*\d)[A-Z0-9](?:[ \-/]?[A-Z0-9]){5,33})(?![A-Za-z0-9])")
_RE_DIGITOS = re.compile(r"(?<![\d])\d(?:[ \-]?\d){12,18}(?![\d])")


def _iban_valido(s: str) -> bool:
    s = s.replace(" ", "")
    n = "".join(str(int(c, 36)) for c in s[4:] + s[:4])
    return int(n) % 97 == 1


_RE_CUENTA_LEJOS = re.compile(r"(?<![\d/-])\d{8,17}(?![\d/-])")
_CTX_CUENTA_LEJOS = re.compile(r"\b(?:account|a/c|acct)\b[^.\n]{0,40}$", _I)


def _banco(texto: str) -> Iterator[Hallazgo]:
    ibans = []
    for m in _RE_IBAN.finditer(texto):
        if _iban_valido(m.group()):
            ibans.append((m.start(), m.end()))
            yield Hallazgo(CUENTA, m.group(), m.start(), m.end(), True)
    for m in _RE_CUENTA_LEJOS.finditer(texto):  # "the estate account at the bank is 782929273792"
        if _CTX_CUENTA_LEJOS.search(texto[max(0, m.start() - 60):m.start()]) and not any(a <= m.start() < b for a, b in ibans):
            yield Hallazgo(CUENTA, m.group(), m.start(), m.end())
    for m in _RE_CUENTA_CTX.finditer(texto):
        valor = m.group(1)
        if _RE_IBAN.fullmatch(valor):
            continue  # ya lo da el IBAN
        yield Hallazgo(CUENTA, valor, m.start(1), m.end(1))
    for h in cs._cuentas(texto):
        if not re.match(r"[ \t]*(?:Coll|Sb)\b", texto[h.fin:h.fin + 6]):  # "Act No. 262/2006 Coll." es una ley
            yield h
    for m in _RE_DIGITOS.finditer(texto):
        d = v.solo_digitos(m.group())
        if any(a <= m.start() < b for a, b in ibans) or re.search(r"[A-Z]$", texto[max(0, m.start() - 1):m.start()]):
            continue  # dígitos de un IBAN
        if 13 <= len(d) <= 19 and v.tarjeta_valida(d):
            yield Hallazgo(TARJETA, m.group(), m.start(), m.end(), True)
    for m in re.finditer(r"(?<!\d)\d{4}[ \-]\d{4}[ \-]\d{4}[ \-]\d{4}(?!\d)", texto):
        if re.search(r"card|visa|mastercard|amex|ending", texto[max(0, m.start() - 40):m.start()], _I):
            yield Hallazgo(TARJETA, m.group(), m.start(), m.end())


# --- contacto ---------------------------------------------------------------------

_RE_TEL = re.compile(
    r"(?<![\w+])(?:"
    r"\+\d{1,3}[ .\-]?(?:\(0\)[ .\-]?)?\(?\d{1,4}\)?(?:[ .\-]?\d{2,4}){2,4}"  # internacional
    r"|\(\d{3}\)[ .\-]?\d{3}[ .\-]\d{4}"  # (555) 123-4567
    r"|\d{3}[.\-]\d{3}[.\-]\d{4}"  # 555-123-4567
    r"|0\d{2,4}[ \-]?\d{3,4}[ \-]?\d{3,4}"  # 020 7946 0958, 07700 900123
    r")(?![\w])"
)
_CTX_TEL = re.compile(r"(?:tel|phone|mobile|mob|cell|fax|contact|call|whatsapp|telephone)\.?\s*(?:no\.?|number|#)?\s*[:.]?\s*$", _I)
_RE_TEL_CTX = re.compile(r"(?<![\w+])\d(?:[ .\-]?\d){6,13}(?![\w])")
_RE_WEB = re.compile(
    r"(?<![@\w.\-/])(?:https?://|www\.)?[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)*\."
    r"(?:com|net|org|io|co\.uk|org\.uk|uk|cz|eu|de|at|sk|us|info|biz|law|legal)(?:/[^\s<>\"')\]]*)?(?![\w\-])", _I)
_WEB_PUBLICA = re.compile(r"\.(?:gov|gov\.uk|nhs\.uk|police\.uk|justice\.cz|gov\.cz|mvcr\.cz|europa\.eu|edu|ac\.uk)(?:/|$)", _I)


def _contacto(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_TEL.finditer(texto):
        d = v.solo_digitos(m.group())
        if 9 <= len(d) <= 15 and not re.fullmatch(r"(?:19|20)\d{2}[ \-]\d{4}", m.group()):
            yield Hallazgo(TELEFONO, m.group().rstrip(".-"), m.start(), m.start() + len(m.group().rstrip(".-")))
    for m in _RE_TEL_CTX.finditer(texto):
        if _CTX_TEL.search(texto[max(0, m.start() - 25):m.start()]):
            yield Hallazgo(TELEFONO, m.group(), m.start(), m.end())
    yield from cs._telefonos(texto)
    yield from (h for h in patrones.candidatos(texto) if h.tipo == CORREO)
    correos = [(h.inicio, h.fin) for h in patrones.candidatos(texto) if h.tipo == CORREO]
    for m in _RE_WEB.finditer(texto):
        valor = m.group().rstrip(".,;:")
        if any(a <= m.start() < b for a, b in correos) or "." not in valor:
            continue
        if not re.match(r"https?://|www\.", valor, _I) and not valor.islower():
            continue  # "Ltd.Co" o nombres pegados: solo dominios en minúsculas sin www
        if not _WEB_PUBLICA.search(valor.split("/")[0] + "/"):
            yield Hallazgo(WEB, valor, m.start(), m.start() + len(valor))


# --- fechas y montos --------------------------------------------------------------

_MES = (r"(?:January|February|March|April|May|June|July|August|September|October|November|December|"
        r"Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)\.?")
_DIA = r"\d{1,2}(?:st|nd|rd|th)?"
_RE_FECHA = re.compile(
    rf"\b{_DIA}(?:\s+(?:day\s+)?of)?\s+{_MES},?\s+\d{{4}}\b"  # 5 March 2024, 5th day of March, 2024
    rf"|\b{_MES}\s+{_DIA},?\s+\d{{4}}\b"  # March 5, 2024
    rf"|\b(?:January|February|March|April|June|July|August|September|October|November|December)\s+\d{{4}}\b"
    r"|(?<![\d/.])\d{1,2}[/.\-]\d{1,2}[/.\-](?:\d{4}|\d{2})(?![\d/])"  # 03/05/2024, 5.3.2024
    r"|(?<![\d.])\d{1,2}\.\s\d{1,2}\.\s\d{4}(?!\d)"  # 5. 3. 2024
    r"|\b\d{4}-\d{2}-\d{2}\b",
)
_MONEDA = r"(?:USD|GBP|EUR|CZK|CHF|US\$|\$|£|€|Kč)"
_RE_MONTO = re.compile(
    rf"(?<![\w$£€])(?:{_MONEDA})\s?\d{{1,3}}(?:[,  ]\d{{3}})*(?:\.\d{{1,2}})?(?:\s?(?:million|m|bn|k)\b)?"
    rf"|(?<![\w.,])\d{{1,3}}(?:[,  .]\d{{3}})*(?:[.,]\d{{1,2}}|,-)?\s?(?:USD|GBP|EUR|CZK|CHF|Kč|dollars|pounds|euros|"
    rf"(?:Czech\s+)?(?:crowns|korunas?|CZK))\b"
)


def _fechas_montos(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_FECHA.finditer(texto):
        yield Hallazgo(FECHA, m.group(), m.start(), m.end())
    for m in cs._RE_FECHA.finditer(texto):
        yield Hallazgo(FECHA, m.group(), m.start(), m.end())
    for m in _RE_MONTO.finditer(texto):
        yield Hallazgo(MONTO, m.group().rstrip(), m.start(), m.start() + len(m.group().rstrip()))


# --- domicilios -------------------------------------------------------------------

_VIA = (r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|Place|Pl\.?|"
        r"Way|Terrace|Circle|Cir\.?|Parkway|Pkwy\.?|Highway|Hwy\.?|Close|Crescent|Gardens|Grove|Square|Sq\.?|Mews|Hill|"
        r"Row|Walk|Park|Green|Rise|View|Parade|Trail|Pike|Alley)(?![\w])")
_PALABRA_DIR = rf"(?:[{MAY}][{MIN}]+|[{MAY}]{{2,}}|\d+(?:st|nd|rd|th))"
_UNIDAD = r"(?:,?\s+(?:Apt\.?|Apartment|Suite|Ste\.?|Unit|Flat|Floor|Fl\.?|#)\s*[\w\-]+)"
_ESTADO = (r"(?:AL|AK|AZ|AR|CA|CO|CT|DE|FL|GA|HI|ID|IL|IN|IA|KS|KY|LA|ME|MD|MA|MI|MN|MS|MO|MT|NE|NV|NH|NJ|NM|NY|NC|ND|"
           r"OH|OK|OR|PA|RI|SC|SD|TN|TX|UT|VT|VA|WA|WV|WI|WY|DC)")
_CP_UK = r"[A-Z]{1,2}\d[A-Z\d]?\s?\d[A-Z]{2}"
_SEP = r"(?:,[ \t]*|[ \t]*\n[ \t]*|,?[ \t]+)"
_RE_DIR_EN = re.compile(
    rf"(?<![\w])(?:(?:Flat|Apartment|Apt\.?|Unit)\s+[\w\-]+,?\s+)?\d{{1,6}}[A-Za-z]?(?:[\-/]\d{{1,5}})?[ \t]+"
    rf"(?:[NSEW]\.?[ \t]+)?(?:{_PALABRA_DIR}[ \t]+){{0,3}}{_VIA}(?:[ \t]+[NSEW][EW]?\.?)?{_UNIDAD}?"
    rf"(?:{_SEP}(?:[{MAY}][{MIN}]+(?:[ \t]+[{MAY}][{MIN}]+){{0,2}}))?"  # barrio o ciudad
    rf"(?:{_SEP}(?:[{MAY}][{MIN}]+(?:[ \t]+[{MAY}][{MIN}]+){{0,2}}))?"  # ciudad
    rf"(?:,?[ \t]+{_ESTADO}[ \t]+\d{{5}}(?:-\d{{4}})?|{_SEP}{_CP_UK})?"
)
_RE_CIUDAD_ESTADO = re.compile(rf"(?<![\w])[{MAY}][{MIN}]+(?:[ \t]+[{MAY}][{MIN}]+){{0,2}},[ \t]+{_ESTADO}[ \t]+\d{{5}}(?:-\d{{4}})?(?!\d)")
_RE_CP_UK = re.compile(rf"(?<![A-Z\d]){_CP_UK}(?![A-Z\d])")
_CTX_DIR = re.compile(
    r"(?:(?:permanently\s+|temporarily\s+)?resid(?:ing|ent|es)\s+(?:at|in)|living\s+at|domiciled\s+at|"
    r"(?:registered|principal)\s+(?:office|address|seat)(?:\s+(?:at|is))?|having\s+its\s+(?:registered\s+)?(?:office|seat)\s+at|"
    r"(?:home|permanent|residential|postal|correspondence|billing|delivery|business)\s+address|address(?:\s+of\s+residence)?|"
    r"place\s+of\s+(?:residence|business)|with\s+(?:its\s+)?(?:seat|registered\s+office)\s+at|located\s+at|situated\s+at|"
    r"property\s+(?:at|known\s+as)|premises\s+(?:at|known\s+as))\s*[:,]?\s*",
    _I,
)
_FIN_DIR = re.compile(r"\n\s*\n|;|\.(?:\s+[A-Z]|\s*$)|\s*\(|,?\s+and\s|,\s+(?:born|date|hereinafter|represented|"
                      r"Birth|ID|Company|tel|phone|e-?mail|as\s|who|which|and\s+the|acting)|\s+(?:hereinafter|as\s+the)\b", _I)


def _domicilios(texto: str) -> Iterator[Hallazgo]:
    for rx in (_RE_DIR_EN, _RE_CIUDAD_ESTADO):
        for m in rx.finditer(texto):
            valor = m.group().rstrip(" ,\n")
            if rx is _RE_DIR_EN and not re.search(_VIA, valor):
                continue
            yield Hallazgo(DOMICILIO, valor, m.start(), m.start() + len(valor))
    for m in _RE_CP_UK.finditer(texto):
        if re.search(r"\d", m.group()) and re.search(r"\d[A-Z]{2}$", m.group().replace(" ", "")):
            yield Hallazgo(DOMICILIO, m.group(), m.start(), m.end())
    yield from cs._direcciones(texto)
    # Tras "residing at", "registered office at"…: hasta el fin de la frase o del renglón.
    for m in _CTX_DIR.finditer(texto):
        resto = texto[m.end():m.end() + 160]
        corte = _FIN_DIR.search(resto)
        valor = resto[:corte.start()] if corte else resto.split("\n")[0]
        if "\n" in valor.strip():
            # En un bloque de varias líneas solo se sigue si la siguiente parece parte de la dirección.
            lineas = valor.split("\n")
            valor = lineas[0]
            for l in lineas[1:]:
                if re.search(rf"\d|{_CP_UK}|^\s*[{MAY}][{MIN}]+(?:\s+\d+)?\s*,?\s*$", l) and len(l.strip()) < 50:
                    valor += "\n" + l
                else:
                    break
        valor = valor.rstrip(" ,\n")
        if re.search(r"\d", valor) and 6 <= len(valor) <= 160 and not re.match(r"\s*(?:the|a|an|this|that)\b", valor, _I):
            ini = m.end() + len(resto) - len(resto.lstrip()) if not valor[:1].strip() else m.end()
            valor = valor.strip()
            yield Hallazgo(DOMICILIO, valor, ini, ini + len(valor))


# --- todo junto -------------------------------------------------------------------


def candidatos(texto: str, usar_modelo: bool = True) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    for f in (_identificadores, _banco, _contacto, _fechas_montos, _domicilios):
        salida += list(f(texto))
    salida += list(empresas(texto))
    salida += personas(texto, usar_modelo)
    return salida
