"""Detector para documentos en checo.

Personas: modelo spaCy propio (entrenado con datos sintéticos; ver paquetes/cs) más reglas:
nombres de pila en sus casos gramaticales, tratamientos y títulos. Sin modelo, quedan las
reglas.

Identificadores con validación: rodné číslo (fecha + divisible entre 11), IČO (dígito de
control), DIČ, cuentas bancarias (norma de la ČNB) e IBAN (módulo 97).
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from . import patrones
from .modelo import (CORREO, CUENTA, DIC, DOMICILIO, EMPRESA, EXPEDIENTE, FECHA, FOLIO, ICO, MONTO,
                     NOMBRE, PLACA, RODNE_CISLO, TELEFONO, WEB, Hallazgo)

AQUI = Path(__file__).parent
MAY = "A-ZÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"
MIN = "a-záčďéěíňóřšťúůýž"
PALABRA = rf"[{MAY}][{MIN}]+(?:-[{MAY}][{MIN}]+)?"
MESICE = ("ledna|února|března|dubna|května|června|července|srpna|září|října|listopadu|prosince")
# Cualquier caso: "1. ledna" (gen.), "1. lednu" (loc.), "22. červen" (nom.), "lednem" (instr.)
MESICE_TODOS = ("července|červenci|červencem|červenec|června|červnu|červnem|červen|ledna|lednu|lednem|leden"
                "|února|únoru|únorem|únor|března|březnu|březnem|březen|dubna|dubnu|dubnem|duben"
                "|května|květnu|květnem|květen|srpna|srpnu|srpnem|srpen|zářím|září|října|říjnu|říjnem|říjen"
                "|listopadu|listopadem|listopad|prosince|prosinci|prosincem|prosinec")

TRATAMIENTOS = (
    "pan", "pana", "panu", "pane", "panem", "panovi", "paní", "slečna", "slečny", "slečně", "slečnu",
    "slečnou", "Ing.", "Mgr.", "Bc.", "JUDr.", "MUDr.", "MVDr.", "PhDr.", "RNDr.", "PaedDr.", "doc.",
    "prof.", "ing.",
)
# Nombres de pila que no están en las tablas declinadas (alemanes, eslovacos, antiguos,
# internacionales). Solo cuentan seguidos de otra palabra con mayúscula: "Heinrich Blum".
_EXTRA_NOM = """René Ferdinand Štefan Heinrich Theodor Bohumír Kryštof Emanuel Leon Gottlieb Victor Viktor Eduardus
Johann Johannes Wilhelm Friedrich Franz Karl Ludwig Hermann Hans Otto Rudolf Ernst Gustav Moritz Julius Anton Alois
Ignác Ignaz Leopold Maxmilián Maximilian Wenzel Wolfgang Georg Christian Christoph Joseph Josephus Adalbert Albín
Augustin Baltazar Benedikt Bernard Blažej Bohuš Bořivoj Ctibor Čeněk Dalibor Dominik Erich Erik Felix Florián Gabriel
Hanuš Heřman Hynek Ignát Izidor Jaromír Jeroným Kazimír Kliment Kornel Lambert Lumír Matouš Melichar Mikuláš Mojmír
Norbert Oldřich Oskar Otmar Prokop Rafael Rostislav Řehoř Silvestr Svatopluk Šimon Teodor Tobiáš Valentin Vavřinec
Vendelín Vincenc Vojtěch Zbyněk Zikmund Ľubomír Ľudovít Ján Jozef Juraj Mikuláš Ondrej Peter Pavol Miroslav Dušan
Gejza Imrich Ladislav Viliam Andrej Matej Michal Marián Igor Branislav Rastislav Radoslav Vladimír Anna Mária Zuzana
Katarína Alžbeta Henrieta Ľudmila Hedviga Johanna Wilhelmine Bertha Berta Elsa Gertrud Margarethe Friederike
Rosa Rosalie Amalie Aloisie Ottilie Ottilie Klotilda Kunhuta Ludmila Sidonie Terezie Josefína Františka Antonie
Achille Alessandro Antonio Carlo Giovanni Giuseppe Luigi Marco Paolo Pietro Pierre Jean Jacques Louis Michel André
Henri Charles François Philippe Claude Nicolas Laurent Juan Carlos José Luis Miguel Pedro Manuel Diego Javier
John James William George Thomas Richard Robert David Michael Paul Mark Peter Steven Andrew Kevin Brian Edward
Mary Elizabeth Sarah Emily Jennifer Jessica Susan Margaret Dorothy Helen Ivan Sergej Dmitrij Nikolaj Alexandr
Alexej Vasilij Grigorij Fjodor Olga Taťána Irina Natalja Jelena Jurij Igor Oleg Bohdan Taras Andrij Mykola
Piotr Krzysztof Wojciech Tomasz Paweł Marek Jacek Andrzej Stanisław Zbigniew Jerzy Tadeusz Ferenc László István
Sándor Gábor Zoltán Lajos Attila Imre Endre Árpád Mihály""".split()
_EXTRA = frozenset(_EXTRA_NOM) | frozenset(n + "a" for n in _EXTRA_NOM if n[-1] not in "aeiouyíáéě") | \
    frozenset(n + s for n in _EXTRA_NOM if n[-1] not in "aeiouyíáéě" for s in ("em", "ovi", "e"))
AMBIGUOS = {"Lada", "Vlasta", "Hora", "Ota", "Kamila", "Ivo", "Viktorie", "Sláva", "Věra", "Naděje",
            "Lev", "Lva", "Karla", "Jana", "Nikola", "Max", "Ema", "Eda", "Dan", "Daniela"}


# --- personas ------------------------------------------------------------------

@lru_cache(maxsize=1)
def _lemas() -> dict[str, str]:
    """Cualquier forma declinada de las tablas → su nominativo ("Evou" → "Eva")."""
    d = json.loads((AQUI / "datos_cs" / "nombres.json").read_text(encoding="utf-8"))
    salida: dict[str, str] = {}
    for g in d.values():
        for grupo in ("jmena", "prijmeni"):
            for fila in g[grupo]:
                for f in fila.values():
                    salida.setdefault(f.lower(), fila["nom"].lower())
    return salida


@lru_cache(maxsize=1)
def _formas() -> tuple[frozenset[str], frozenset[str]]:
    d = json.loads((AQUI / "datos_cs" / "nombres.json").read_text(encoding="utf-8"))
    # Sin vocativo: "Zlato", "Pavle" o "Karle" casi siempre son otra cosa fuera de un saludo.
    jmena = {f for g in d.values() for fila in g["jmena"] for c, f in fila.items() if c != "vok"}
    prijmeni = {f for g in d.values() for fila in g["prijmeni"] for f in fila.values()}
    return frozenset(jmena), frozenset(prijmeni)


def ruta_modelo() -> Path | None:
    for candidato in (os.environ.get("ANONIMIZADOR_MODELO_CS"), AQUI.parent / "modelos" / "cs"):
        if candidato and (Path(candidato) / "meta.json").exists():
            return Path(candidato)
    return None


@lru_cache(maxsize=1)
def _nlp():
    """El modelo checo: cs_ner_sm (spaCy checo de ~/spacy-cs, en Hugging Face), o una carpeta si se indica
    una (ANONIMIZADOR_MODELO_CS / modelos/cs). Las reglas de identificadores de cs_ner_sm no se cargan:
    la app tiene las suyas."""
    try:
        import spacy

        ruta = ruta_modelo()
        if ruta is not None:
            return spacy.load(ruta, exclude=["cs_pii_rules"])
        import cs_ner_sm

        return cs_ner_sm.load(exclude=["cs_pii_rules"])
    except Exception:  # sin spaCy o sin modelo: quedan las reglas
        return None


_ETIQUETAS_MODELO = {"PER": "PERSON"}  # cs_ner_sm dice PER/ORG/LOC; el modelo viejo, PERSON/ORG/ADDRESS


def modelo_disponible() -> bool:
    return _nlp() is not None


def _por_reglas(texto: str) -> list[tuple[int, int]]:
    jmena, prijmeni = _formas()
    tramos = []
    for m in re.finditer(rf"(?<![\w.]){PALABRA}(?:[ \t]+{PALABRA})?", texto):
        palabras = m.group().split()
        if "sv." in texto[max(0, m.start() - 4):m.start()]:
            continue
        if palabras[0] not in jmena:
            if palabras[0] in _EXTRA and len(palabras) == 2:
                tramos.append((m.start(), m.end()))
            continue
        fin = m.end()
        if len(palabras) == 2 and palabras[1] in jmena and palabras[1] not in prijmeni:
            fin = m.start() + len(palabras[0])
        if fin == m.start() + len(palabras[0]) and palabras[0] in AMBIGUOS:
            continue
        tramos.append((m.start(), fin))
    # "Emanuel rytíř von Forster", "Zdeněk z Lobkovic"
    for m in re.finditer(rf"(?<![\w.])({PALABRA})[ \t]+(?:rytíř|svobodný pán|hrabě|baron)?[ \t]*(?:von|van|de|z|ze)[ \t]+{PALABRA}", texto):
        if m.group(1) in jmena or m.group(1) in _EXTRA:
            tramos.append((m.start(), m.end()))
    trat = "|".join(re.escape(t) for t in TRATAMIENTOS)
    for m in re.finditer(rf"(?<!\w)(?:{trat})[ \t]+((?:{PALABRA})(?:[ \t]+{PALABRA})?)", texto):
        tramos.append((m.start(1), m.end(1)))
    return tramos


def _unir(tramos):
    salida: list[list[int]] = []
    for a, b in sorted(tramos):
        if salida and a <= salida[-1][1]:
            salida[-1][1] = max(salida[-1][1], b)
        else:
            salida.append([a, b])
    return [tuple(x) for x in salida]


_INICIO_FALSO = {"Ačkoliv", "Kolem", "Narodila", "Narodil", "Mládí", "Dále", "Tedy", "Proto", "Také", "Podle"}


@lru_cache(maxsize=1)
def _obce() -> frozenset[str]:
    """Municipios de Chequia como clave de raíces ("Moravské Třebové" → "morav třebov")."""
    claves = set()
    for n in _obce_json():
        # Con y sin la "e" que se pierde al declinar: Hradec → Hradce, Kolinec → Kolince
        variantes = [[raiz(w)] + ([raiz(w[:-2] + w[-1])] if re.search(r"[^aeiouyáéěíóúůý]e[cklnň]$", w) else [])
                     for w in n.split()]
        for combo in __import__("itertools").product(*variantes):
            claves.add(" ".join(combo))
    return frozenset(claves)


_CTX_LUGAR = re.compile(r"(?<!\w)(?:v|ve|z|ze|do|u|na|nad|pod|od|okres\w*|obc\w*|měst\w*|starost\w*|rodák\w*|"
                        r"rodačk\w*|obyvatel\w*|poblíž|nedaleko|mezi|zastupitel\w*|primátor\w*|hejtman\w*|radní|rodišt\w*|okolí)[ \t]+$", re.IGNORECASE)


def _es_municipio(texto: str, a: int, b: int) -> bool:
    """"Tábor", "Moravská Třebová": el nombre tal cual; declinado ("z Rakovníka", "starosta
    Šternberka") solo con contexto de lugar, porque muchos apellidos se declinan igual."""
    valor = " ".join(texto[a:b].split())
    if valor in _obce_nom():
        return True
    if " ".join(raiz(p) for p in valor.split()) not in _obce():
        return False
    # Un nombre de varias palabras que coincide con un municipio ("Hradce Králové") casi nunca es una persona.
    return len(valor.split()) > 1 or bool(_CTX_LUGAR.search(texto[max(0, a - 15):a]))


@lru_cache(maxsize=1)
def _obce_nom() -> frozenset[str]:
    return frozenset(_obce_json())


def _obce_json() -> list[str]:
    return json.loads((AQUI / "datos_cs" / "obce.json").read_text(encoding="utf-8"))


_TIT_ANTES = re.compile(r"(?:(?:Ing\.\s?arch|Ing|Mgr|Bc|BcA|MgA|JUDr|MUDr|MDDr|MVDr|PhDr|RNDr|PaedDr|ThDr|ThLic|PharmDr|"
                        rf"Dr|doc|prof|[{MAY}])\.[ \t]?)+$")
_TIT_DESPUES = re.compile(r"^(?:,?[ \t]?(?:Ph\.\s?D\.|CSc\.|DrSc\.|MBA|LL\.\s?M\.|DiS\.|MPA|M\.\s?A\.|dr\.\s?h\.\s?c\.))+")
_NOBLEZA = re.compile(rf"^(?:[ \t]+(?:rytíř|svobodný pán|hrabě|baron|šlechtic)?[ \t]*(?:von|van|de|di|du|z|ze)[ \t]+{PALABRA})+"
                      r"|^[ \t]+(?:mladší|starší|ml\.|st\.)(?!\w)")
_NO_PERSONA_ANTES = re.compile(r"(?:německy|něm\.|polsky|latinsky|maďarsky|slovensky|anglicky|italsky|název|dříve|řád\w*|"
                               r"ulic\w*|nám(?:ěstí|\.)|most\w*|kostel\w*|nádraží|Na|sv\.|svat\w+)[ \t]*:?[ \t]*$")
_INICIO_ORACION = re.compile(r"(?:^|[.!?][ \t]+|\d\.[ \t]+|\n[ \t]*)$")
_CTX_PERSONA = re.compile(r"(?:rozen[áý]|roz\.|příjmení|jméno|jménem|manžel\w*|syn\w*|dcer\w*|otc\w*|otec|matk\w*|"
                          r"svěd(?:ek|kyně|ka|kem|kyní)|zástupc\w*|zpracoval\w*|vyřizuje|podpis)\s*:?\s*$", re.IGNORECASE)


def _ampliar_persona(texto: str, a: int, b: int) -> tuple[int, int]:
    """Con títulos e iniciales delante ("JUDr. K. H. Borovského"), grados detrás (", Ph.D."),
    nombres de pila antepuestos ("Jan Jiří Michael Achbauer") y predicados ("rytíř von Forster")."""
    jmena, _ = _formas()
    while True:
        previa = re.search(rf"({PALABRA})[ \t]+$", texto[max(0, a - 30):a])
        if previa and (previa.group(1) in jmena or previa.group(1) in _EXTRA):
            a = a - len(previa.group())
            continue
        break
    t = _TIT_ANTES.search(texto[max(0, a - 40):a])
    if t:
        a -= len(t.group())
    while True:
        n = _NOBLEZA.match(texto[b:])
        if not n:
            break
        b += len(n.group())
    g = _TIT_DESPUES.match(texto[b:])
    if g:
        b += len(g.group())
    return a, b


def _persona_creible(texto: str, a: int, b: int) -> bool:
    """Descarta lo que el modelo confunde con personas: municipios, nombres en otro idioma
    ("německy Strzelitz"), órdenes y calles, y palabras al inicio de oración ("Navrhl")."""
    valor = texto[a:b]
    jmena, prijmeni = _formas()
    palabras = re.findall(r"[^\W\d_]+\.?", valor)
    if re.search(r"\d", valor) or "\n" in valor or not palabras or palabras[0] in _INICIO_FALSO:
        return False
    if _NO_PERSONA_ANTES.search(texto[max(0, a - 25):a]):
        return False
    conocidas = [p for p in palabras if p in jmena or p in _EXTRA]
    titulo = _TIT_ANTES.search(texto[max(0, a - 40):a]) or re.search(r"(?:pan\w*|paní|slečn\w+)[ \t]+$", texto[max(0, a - 12):a])
    if not conocidas and not titulo and not _CTX_PERSONA.search(texto[max(0, a - 25):a]):
        if _es_municipio(texto, a, b):
            return False
        reales = [p for p in palabras if not p.endswith(".") and not p.isupper()]
        if (len(reales) == 1 and palabras[0] == reales[0] and reales[0] not in prijmeni
                and _INICIO_ORACION.search(texto[max(0, a - 6):a])):
            return False
    return True


_NO_AMPLIA_ORG = _INICIO_FALSO | {"V", "Ve", "Na", "Do", "Z", "Ze", "S", "Se", "U", "K", "Ke", "O", "Od", "Po", "Pro",
                                  "Při", "Za", "Před", "Mezi", "Nad", "Pod", "A", "I", "Ale", "Firma", "Společnost",
                                  "Skupina", "Banka", "Pan", "Paní", "Jeho", "Její", "Jejich",
                                  # "Nařízení [Evropského parlamentu]": documento o cargo delante, no parte del nombre
                                  "Nařízení", "Směrnice", "Rozhodnutí", "Usnesení", "Rozsudek", "Zákon", "Vyhláška",
                                  "Podle", "Dle", "Činnost", "Člen", "Členka", "Předseda", "Předsedkyně", "Ředitel",
                                  "Ředitelka", "Mluvčí", "Zástupce", "Zástupci"}


def _ampliar_org(texto: str, a: int, b: int) -> tuple[int, int]:
    """El modelo corta nombres de empresa: "Nová [Mosilana]", "OHL [Central Europe]", "Alois Vavrouš [a syn]"."""
    for _ in range(2):
        previa = re.search(rf"(?<![\w.])([{MAY}][\w\-]*)[ \t]+$", texto[max(0, a - 30):a])
        if not previa or previa.group(1) in _NO_AMPLIA_ORG or previa.group(1) in _NO_ORG:
            break
        a -= len(previa.group())
    cola = re.match(r"[ \t]+a[ \t]+(?:syn|synové|spol\.?)(?!\w)", texto[b:])
    if cola:
        b += cola.end()
    return a, b


_ESTADOS = """Česko|Česká republika|Československo|Československá republika|Slovensko|Slovenská republika|Německo|
Spolková republika Německo|Německá demokratická republika|Rakousko|Rakousko-Uhersko|Polsko|Maďarsko|Rusko|Ruská federace|
Ruská SFSR|Sovětský svaz|SSSR|Ukrajina|Bělorusko|Litva|Lotyšsko|Estonsko|Estonská sovětská socialistická republika|
Lotyšská sovětská socialistická republika|Litevská sovětská socialistická republika|Francie|Itálie|Španělsko|Portugalsko|
Belgie|Nizozemsko|Lucembursko|Švýcarsko|Dánsko|Švédsko|Norsko|Finsko|Island|Irsko|Velká Británie|Spojené království|Anglie|
Skotsko|Řecko|Turecko|Rumunsko|Bulharsko|Srbsko|Chorvatsko|Slovinsko|Jugoslávie|Albánie|Moldavsko|Gruzie|Arménie|
Ázerbájdžán|Kazachstán|Írán|Irák|Sýrie|Egypt|Indie|Čína|Japonsko|Korea|Vietnam|Mongolsko|Kanada|Mexiko|Brazílie|
Argentina|Chile|Austrálie|Spojené státy|Spojené státy americké|USA|Monako|San Marino|Vatikán|Lichtenštejnsko|
Andorra|Malta|Kypr|Россия|Российская Федерация|Советский Союз""".replace("\n", "").split("|")


@lru_cache(maxsize=1)
def _estados() -> frozenset[str]:
    """Estados como clave de raíces: "Sovětském svazu" → "sovětsk svaz" = "Sovětský svaz"."""
    return frozenset(" ".join(raiz(w) for w in e.split()) for e in _ESTADOS)


def _es_estado(valor: str) -> bool:
    return " ".join(raiz(w) for w in valor.split()) in _estados()


def ajustar_modelo(texto: str, ents: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    """Corrige las entidades del modelo estadístico (entrenado con texto sintético) en texto real."""
    salida = []
    for a, b, etiqueta in ents:
        if etiqueta in ("PERSON", "ORG") and _es_estado(texto[a:b]):   # un país no es persona ni organización
            continue
        if etiqueta == "PERSON":
            if not _persona_creible(texto, a, b):
                continue
            a, b = _ampliar_persona(texto, a, b)
        elif etiqueta == "ADDRESS":
            valor = texto[a:b]
            if not re.search(r"\d", valor) or re.fullmatch(rf"(?:{PALABRA}[ \t]*)+(?:1[89]|20)\d\d", valor):
                continue
            if _es_municipio(texto, a, b):
                continue
        elif etiqueta == "ORG":
            a, b = _ampliar_org(texto, a, b)
        salida.append((a, b, etiqueta))
    return salida


def personas(texto: str, usar_modelo: bool = True) -> list[Hallazgo]:
    tramos = [_ampliar_persona(texto, a, b) for a, b in _por_reglas(texto)]
    nlp = _nlp() if usar_modelo else None
    if nlp is not None:
        ents = [(e.start_char, e.end_char, _ETIQUETAS_MODELO.get(e.label_, e.label_)) for e in nlp(texto).ents]
        tramos += [(a, b) for a, b, l in ajustar_modelo(texto, ents) if l == "PERSON"]
    return [Hallazgo(NOMBRE, texto[a:b], a, b) for a, b in _unir(tramos)]


# --- declinaciones ---------------------------------------------------------------

_TERMINACIONES = sorted(["ovou", "ové", "ová", "ovi", "ou", "ého", "ému", "ém", "ým", "ými", "ých",
                         "ý", "á", "é", "em", "ům", "u", "a", "e", "ě", "y", "i", "í", "o"], key=len, reverse=True)


def raiz(palabra: str) -> str:
    """Forma base de un nombre o apellido en cualquier caso.

    Primero la tabla de declinaciones ("Evou" → "eva"); si no está, se quita la terminación:
    Bosákovou/Bosáková/Bosákové → "bosákov" (la marca -ov separa a la esposa del esposo:
    Nováková ≠ Novák) y Gotta/Gottem → "gott".
    """
    p = palabra.lower()
    lema = _lemas().get(p)
    if lema is not None:
        p = lema
    for fem in ("ovou", "ové", "ová"):
        if p.endswith(fem) and len(p) - len(fem) >= 2:
            return p[: -len(fem)] + "ov"
    for t in _TERMINACIONES:
        if p.endswith(t) and len(p) - len(t) >= 3:
            return p[: -len(t)]
    return p


_TITULOS = {t.rstrip(".").lower() for t in TRATAMIENTOS} | {"ph", "d", "csc", "drsc", "mba", "dis"}


def clave_persona(nombre: str) -> str:
    """Misma clave para "Eva Bosáková", "Evou Bosákovou", "Ing. Evy Bosákové"."""
    return " ".join(raiz(w) for w in re.findall(r"\w+", nombre) if w[0].isupper() and w.lower() not in _TITULOS)


# --- empresas --------------------------------------------------------------------

_FORMA = (r"(?:spol\.\s?s\s?r\.\s?o\.|s\.\s?r\.\s?o\.|a\.\s?s\.|v\.\s?o\.\s?s\.|k\.\s?s\.|z\.\s?s\.(?!\s?ú\.)|z\.\s?ú\.|o\.\s?p\.\s?s\.|s\.\s?p\.|SE"
          r"|a\s?spol\.?|Limited|LIMITED|Ltd\.?|LTD\.?|Inc\.|INC\.|GmbH|AG|S\.\s?[àá]\.?\s?r\.\s?l\.|B\.V\.|N\.V\.|plc|PLC|LLC|Co\.|S\.A\.)")
# Nombres en inglés que terminan en una palabra de empresa: "Bakala Foundation", "ABRA Software".
_RE_EMPRESA_CLAVE = re.compile(
    rf"(?<![\w&-])((?:[{MAY}0-9][\w&\-]*[ \t]+){{1,4}}(?:Group|Holding|Holdings|Foundation|Software|Systems|Interactive|"
    r"Cluster|Alliance|Games|Studios?|Entertainment|Technologies|Solutions|Capital|Partners|Investments?|Pharma|"
    r"Energy|Media|Logistics|Industries|INDUSTRIES|Manufacturing|Corporation|Company|Equity|Ventures|Consulting))(?!\w)")
# "společnosti Aukro", "do holdingu Akeso", "hnutí STAN": el nombre tras la palabra que lo presenta.
_RE_EMPRESA_CTX = re.compile(
    r"(?<!\w)(?:[Ss]polečnost\w*|[Ff]irm[aouyěé]\w*|holding\w*|koncern\w*|výrobc\w*|značk\w*|skupin\w+|"
    r"start-?up\w*|e-?shop\w*|portál\w*|hnutí|zařízení|banky|bankou|banka|studi[aouo]\w*|vydavatelství)[ \t]+"
    rf"((?:[{MAY}0-9][\w&\-]*|&)(?:[ \t]+(?:[{MAY}0-9][\w&\-]*|&))*)")
_RE_EMPRESA = re.compile(
    rf"(?<![\w])((?:[{MAY}0-9][\w&.\-]*|a|&|syn|a\s+syn)(?:[ \t]+(?:[\w&.\-]+))*?),?[ \t]+{_FORMA}(?!\w)"
)
_NO_EMPRESA = {"Společnost", "společnost", "společnosti", "společností", "Firma", "firmy", "firmou"}


def empresas(texto: str) -> Iterator[Hallazgo]:
    for r in (_RE_EMPRESA_CLAVE, _RE_EMPRESA_CTX):
        for m in r.finditer(texto):
            valor = m.group(1)
            primera = valor.split()[0]
            if (primera in _NO_EMPRESA or primera.lower() in _TITULOS or re.fullmatch(r"[\d\s]+", valor)
                    or (texto[m.end(1):m.end(1) + 1] == "." and len(valor) <= 4)):
                continue
            if True:
                yield Hallazgo(EMPRESA, valor, m.start(1), m.end(1))
    for m in re.finditer(rf",?[ \t]+{_FORMA}(?!\w)", texto):
        linea_ini = texto.rfind("\n", 0, m.start()) + 1
        palabras = list(re.finditer(r"[^\s,]+|,", texto[linea_ini:m.start()]))
        inicio = None
        for p in reversed(palabras[-7:]):
            w = p.group()
            if w in _NO_EMPRESA or w.endswith((":", ";", "(", ")")):
                break
            if w[0].isupper() or w[0].isdigit() or w in {"&", "a", "syn", ",", "-"}:
                inicio = linea_ini + p.start() if w not in {",", "a", "&", "-"} else inicio
            elif inicio is None:
                break
            else:
                inicio_tmp = inicio
                if not w.islower() or len(w) > 12:
                    break
                inicio = inicio_tmp
        if inicio is not None and not re.search(r"odst\.|§|písm\.", texto[inicio:m.start()]):
            yield Hallazgo(EMPRESA, texto[inicio:m.end()].strip(), inicio, m.end())
    yield from organizaciones(texto)


# --- organizaciones sin forma jurídica ------------------------------------------------
# El spaCy responde "¿qué es esto?": un partido, un banco o una marca son ORG aunque la app no los oculte
# (EMPRESA sale desmarcada por defecto). Los órganos públicos (soudy, úřady, ministerstva) van aparte, en
# instituciones(), que solo usa el spaCy.

_ADJ = rf"[{MAY}][{MIN}]*(?:ního|nímu|ním|ních|ními|ní|ná|né|ný|ího|ímu|ím|ích|ími|ých|ého|ému|ém|ým|ými|ou|á|é|ý|í)"
_ADJ_MIN = rf"[{MIN}]+(?:ího|ímu|ím|ích|ími|ých|ého|ému|ém|ým|ými|ou|á|é|ý|í)"
# Sustantivo núcleo de una organización, en sus casos.
_NUCLEO = ("strana|strany|straně|stranu|stranou|stran|stranami|spořitelna|spořitelny|spořitelně|spořitelnu|spořitelnou|"
           "banka|banky|bance|banku|bankou|pojišťovna|pojišťovny|pojišťovně|pojišťovnu|pojišťovnou|"
           "nemocnice|nemocnici|nemocnicí|asociace|asociaci|asociací|komora|komory|komoře|komoru|komorou|"
           "podnik|podniku|podnikem|podniky|podniků|klub|klubu|klubem|svaz|svazu|svazem|spolek|spolku|spolkem|"
           "hnutí|hnutím|akademie|akademii|akademií|společnost|společnosti|společností|dráhy|drah|drahám|dráhami|"
           "stavitelství|stavby|staveb|holding|holdingu|holdingem|kancelář|kanceláře|kanceláři|kanceláří|"
           "sdružení|sdružením|nadace|nadaci|nadací|družstvo|družstva|družstvu|družstvem|demokracie|demokracii|demokracií|"
           "obec spisovatelů|obce spisovatelů|obci spisovatelů|"
           "závody|závodů|železárny|železáren|strojírny|strojíren|pivovar|pivovaru|pivovarem|"
           "nakladatelství|vydavatelství|divadlo|divadla|divadle|divadlem|orchestr|orchestru|orchestrem|"
           "fond|fondu|fondem|federace|federaci|federací|liga|ligy|lize|ligu|ligou|aliance|alianci")
_PUBLICO = re.compile(r"soud|úřad|ministerstv|inspekc|správ[aěuy]|polici|zastupitelstv|národní ban|unie|unii|úni[ií]",
                      re.IGNORECASE)
_COLA = (rf"(?:[ \t]+[{MIN}]+ě[ \t]+[{MIN}]+(?:ck|sk)(?:á|é|ý|ou|ého|ých|ým))?"   # "sociálně demokratická"
         rf"(?:(?:[ \t]+[{MIN}]+(?:ích|ých))?[ \t]+[{MIN}]{{4,}}ů(?!\w))?"               # "(realitních) pojistitelů"
         rf"(?:[ \t]+(?:města[ \t]+)?(?:[{MAY}][\w\-]*|[{MAY}]\.)){{0,3}}"
         r"(?:(?:(?<=České)|(?<=Slovenské)|(?<=Evropské))[ \t]+(?:republiky|unie)|(?:(?<=ého)|(?<=ské)|(?<=cké))[ \t]+kraje)?")            # "Československa", "města Olomouce"
_RE_NUCLEO = re.compile(
    rf"(?<![\w.])((?:{_ADJ})(?:[ \t]+(?:a[ \t]+)?(?:{_ADJ}|{_ADJ_MIN})){{0,3}}[ \t]+(?:{_NUCLEO})(?!\w){_COLA})")
# Núcleo delante, con mayúscula: "Nemocnice Hořovice", "Studio J. A. Komenského", "Nadace Dobrý skutek".
# Partido con adjetivo pospuesto: "Československá strana lidová", "Evropské strany zelených".
_RE_STRANA_POST = re.compile(
    rf"(?<![\w.])((?:{_ADJ})(?:[ \t]+(?:a[ \t]+)?(?:{_ADJ}|{_ADJ_MIN})){{0,3}}[ \t]+(?:strana|strany|straně|stranu|stranou)"
    rf"[ \t]+[{MIN}]+(?:ová|ové|ovou|ých|ická|ické|ickou|ská|ské|skou|ní))(?!\w)")
_RE_OBEC_SPISOVATELU = re.compile(r"(?<!\w)(?:Obec|Obce|Obci)[ \t]+spisovatelů(?:[ \t]+ČR)?(?!\w)")
_RE_NUCLEO_SOLO = re.compile(rf"(?<!\w)(?:{_NUCLEO})(?!\w)", re.IGNORECASE)
_PARTIDOS = {"ANO", "STAN", "SPD", "TOP", "ČSSD", "KSČ", "KSČM", "ODS", "KDU-ČSL", "ČSL", "ČSNS", "ODA", "SZ", "KAN"}
_RE_NUCLEO_DELANTE = re.compile(
    r"(?<![\w.])((?:Nemocnice|Nemocnici|Nemocnicí|Studio|Studia|Studiu|Studiem|Klub|Klubu|Klubem|Spolek|Spolku|Spolkem|"
    r"Nadace|Nadaci|Nadací|Nadační fond|Nadačního fondu|Divadlo|Divadla|Divadle|Divadlem|Nakladatelství|Vydavatelství|"
    r"Pivovar|Pivovaru|Pivovarem|Sdružení|Asociace|Asociaci|Svaz|Svazu|Svazem|Hnutí)"
    rf"[ \t]+(?:[{MAY}]\.|[{MAY}][\w\-]*)"
    rf"(?:[ \t]*(?:[{MAY}]\.|[{MAY}][\w\-]*|[{MIN}]+(?=[ \t]+[{MAY}])))*"
    r"(?:(?<=ého)[ \t]+kraje)?)")
# Partidos, bancos y marcas que se nombran sin presentarlos: solo siglas inequívocas y nombres que no son apellidos
# ni palabras comunes (por eso no están Albert, Penny, Ford, Škoda, Tesla…).
_CONOCIDAS = ("ČSSD KSČ KSČM ODS KDU-ČSL ČSL ČSNS ODA SPD ČSOB IPB ČEZ ČSA Agrofert Agrofertu Agrofertem "
              "Skanska Skansce Skansku Toyota Toyoty Toyotě Toyotu Toyotou Nissan Nissanu Suzuki Renault Renaultu "
              "Daimler Daimleru Volvo Porsche Audi Volkswagen Volkswagenu Hyundai Peugeot Citroën Mitsubishi Subaru "
              "Siemens Siemensu Microsoft Microsoftu Google Googlu Amazon Amazonu Unipetrol Unipetrolu Kaufland "
              "Kauflandu Lidl Lidlu").split() + [
              "Land Rover", "Mercedes-Benz", "TOP 09", "ANO 2011", "Komerční banka", "Komerční banky", "Komerční bance",
              "Komerční banku", "Komerční bankou"]
_RE_CONOCIDAS = re.compile(r"(?<![\w\-])(" + "|".join(re.escape(x) for x in sorted(_CONOCIDAS, key=len, reverse=True))
                           + r")(?![\w\-])")
# Palabras que presentan una organización (y listas: "automobilky Toyota, Nissan a Suzuki").
_RE_PRESENTA = re.compile(
    r"(?<!\w)(automobil(?:k[aouyěi]|ek|kám|kami)|řetězc[eiů]|řetězec|klub[uemy]?|spol(?:ek|ku|kem)|"
    r"sdružení|nadac[eií]|organizac[eií]|agentur[aouyě]|deník[uem]?|týdeník[uem]?|pojišťovn[aouyě]|"
    r"stran[aouyě]|stranou|hnutí|týmu|týmem|tým|členem|člen|členka|členkou|členové|do|za|pro)"
    rf"[ \t]+((?:[{MAY}0-9][\w&\-]*)(?:[ \t]+(?:[{MAY}0-9][\w&\-]*|noviny|listy|fronta|sbor))*)")
_RE_LISTA = re.compile(rf"^(?:,|[ \t]+a|[ \t]+i|[ \t]+nebo)[ \t]+((?:[{MAY}][\w&\-]*)(?:[ \t]+[{MAY}][\w&\-]*)?)")
_SIGLA = re.compile(rf"^\((?:dále[ \t]+(?:jen|též)[ \t]+)?[„\"]?([{MAY}][{MAY}{MIN}0-9\-]{{1,9}})[“\"]?\)")
_NO_ORG = {"Česká", "České", "Českou", "Český", "Českého", "Praha", "Prahy", "Praze", "Brno", "Brna", "Brně",
           "Ostrava", "Ostravy", "Ostravě", "Plzeň", "Plzně", "Plzni", "Československo", "Československa", "ČR", "SR",
           "EU", "USA", "OSN", "NATO", "DPH"}
# Al inicio de oración, "Druhá strana", "Obchodní společnost" y similares no son nombres.
_ADJ_GENERICOS = {"druhá", "druhé", "druhou", "obě", "každá", "každé", "smluvní", "procesní", "vedlejší", "žalovaná",
                  "žalující", "obchodní", "dotčená", "dotčené", "tato", "této", "tuto", "taková", "takové", "jiná",
                  "jiné", "jinou", "uvedená", "uvedené", "uvedenou", "stejná", "stejné", "politická", "politické",
                  "politickou", "opoziční", "vládní", "koaliční", "celá", "celé", "nová", "nové", "novou", "veřejná",
                  "veřejné", "zahraniční", "mezinárodní", "rodinná", "rodinné", "dceřiná", "dceřiné", "mateřská",
                  "mateřské", "akciová", "akciové", "akciovou", "jediná", "jediné", "některá", "některé", "ostatní",
                  "příslušná", "příslušné", "zmíněná", "zmíněné", "taková", "samotná", "samotné", "vážená", "vážený",
                  "vážené", "vážení", "milá", "milý", "milé", "rodinný", "rodinného", "vaše", "vaší", "váš", "vašeho", "naše",
                  "naší", "náš", "našeho", "jejich", "jeho", "její"}


_POSESIVOS = {"vaše", "vaší", "váš", "vašeho", "vašem", "vaši", "naše", "naší", "náš", "našeho", "našem", "naši"}


def _es_sigla(texto: str) -> bool:
    return bool(re.fullmatch(rf"[{MAY}][{MAY}{MIN}0-9\-]*[{MAY}0-9]", texto)) and sum(c.isupper() for c in texto) >= 2


def _sigla_de(nombre: str, sigla: str) -> bool:
    """¿"IPB" son las iniciales de "Investiční a poštovní banky"? (se saltan "a", "pro", "v"…)"""
    letras = [c for c in sigla.upper() if c.isalpha()]
    vacias = {"a", "i", "pro", "v", "ve", "na", "s", "se", "z", "ze", "o", "do", "of", "and", "the", "for"}
    iniciales = [p[0].upper() for p in re.findall(r"[^\W\d_]+", nombre) if p.lower() not in vacias]
    return len(letras) >= 2 and "".join(iniciales[:len(letras)]) == "".join(letras) and len(iniciales) <= len(letras) + 2


def organizaciones(texto: str) -> Iterator[Hallazgo]:
    tramos: list[tuple[int, int]] = []

    def poner(a: int, b: int) -> None:
        valor = texto[a:b].rstrip(" \t,")
        b = a + len(valor)
        if not valor or valor in _NO_ORG or _PUBLICO.search(valor) or re.fullmatch(r"[\d\s]+", valor) or _es_estado(valor):
            return
        if texto[b:b + 2].lstrip(" \t").startswith(":"):
            return   # rótulo de un campo ("Pojistitel:"), no un nombre
        tramos.append((a, b))

    for r in (_RE_NUCLEO, _RE_NUCLEO_DELANTE, _RE_STRANA_POST):
        for m in r.finditer(texto):
            a, b = m.start(1), m.end(1)
            primera = texto[a:b].split()[0]
            if (primera in _INICIO_FALSO or re.search(r"(?:ení|ání|ití|ítí|utí)$", primera)
                    or primera.lower() in _POSESIVOS):
                continue   # "Prohlášení stran", "Zahájení stavby": sustantivo verbal, no adjetivo
            if (len(texto[a:b].split()) == 2 and r is _RE_NUCLEO
                    and _INICIO_ORACION.search(texto[max(0, a - 6):a])):
                continue   # "Advokátní kancelář", "Pozemní stavby" solos al inicio: genérico
            if _INICIO_ORACION.search(texto[max(0, a - 6):a]) and primera.lower() in _ADJ_GENERICOS:
                continue
            poner(a, b)
    for m in re.finditer(rf"(?<![\w.])((?:{PALABRA}[ \t]+){{0,2}}{PALABRA}[ \t]+a[ \t]+(?:syn|synové|synů|dcera|bratři))(?!\w)", texto):
        poner(m.start(1), m.end(1))
    for m in _RE_OBEC_SPISOVATELU.finditer(texto):
        tramos.append((m.start(), m.end()))
    for m in _RE_CONOCIDAS.finditer(texto):
        poner(m.start(1), m.end(1))
    for m in _RE_PRESENTA.finditer(texto):
        a, valor = m.start(2), m.group(2)
        palabra = m.group(1).lower()
        primera = valor.split()[0]
        if palabra in {"za", "do", "pro"} or palabra.startswith("člen"):
            # "za ANO", "do KSČ", "členem ODS": solo siglas de partidos ("za SMS" no); un nombre propio ahí suele
            # ser persona o lugar.
            if not _es_sigla(primera) or primera in _NO_ORG or (palabra in {"za", "do", "pro"} and primera not in _PARTIDOS):
                continue
            numero = re.match(r"[ \t]+\d+(?!\S)", valor[len(primera):])   # "TOP 09", "ANO 2011"
            poner(a, a + len(primera) + (numero.end() if numero else 0))
            continue
        if primera in _NO_ORG or primera.lower() in _TITULOS or primera in _formas()[0]:
            continue   # "na straně Petra Nováka" es una persona
        poner(a, a + len(valor))
        if palabra.startswith(("automobil", "značk", "řetěz")):
            fin = a + len(valor)
            while (n := _RE_LISTA.match(texto[fin:])):
                poner(fin + n.start(1), fin + n.end(1))
                fin += n.end()
    # Siglas definidas en el texto: "Investiční a poštovní banky (IPB)" y luego cada "IPB".
    siglas = set()
    for m in re.finditer(r"\(", texto):
        s = _SIGLA.match(texto[m.start():])
        if not s or not _es_sigla(s.group(1)) or s.group(1) in _NO_ORG:
            continue
        sigla = s.group(1)
        izq = texto[:m.start()].rstrip()
        if any(b == len(izq) for _, b in tramos):
            siglas.add(sigla)
            continue
        # Sin organización ya vista: las iniciales de las palabras de antes tienen que dar la sigla.
        antes = izq[max(0, len(izq) - 160):]
        base = len(izq) - len(antes)
        palabras = list(re.finditer(r"[^\s()]+", antes))
        for k in range(len(palabras) - 1, max(-1, len(palabras) - 12), -1):
            inicio = palabras[k]
            nombre = antes[inicio.start():]
            # La sigla de un término ("Roční procentní sazba nákladů (RPSN)") no hace organización: hace falta
            # un sustantivo de organización o un nombre con mayúsculas ("Bohemia Energy Group").
            pinta_org = _RE_NUCLEO_SOLO.search(nombre) or sum(p[0].isupper() for p in nombre.split()) >= 2
            if inicio.group()[0].isupper() and _sigla_de(nombre, sigla) and pinta_org and not _PUBLICO.search(nombre):
                poner(base + inicio.start(), len(izq))
                siglas.add(sigla)
                break
    if siglas:
        for m in re.finditer(r"(?<![\w\-])(" + "|".join(re.escape(s) for s in siglas) + r")(?![\w\-])", texto):
            poner(m.start(1), m.end(1))
    for a, b in _unir(tramos):
        yield Hallazgo(EMPRESA, texto[a:b], a, b)



# --- instituciones públicas (solo el spaCy) ---------------------------------------------
# Para un NER, un juzgado, un ministerio o la ČNB son organizaciones. La app no las usa (no las oculta);
# las añade el componente cs_pii_rules del paquete. Solo con mayúscula: "Okresní soud v Brně" es un nombre,
# "okresní soud" es genérico.

_NUCLEO_PUB = ("soud|soudu|soudem|soudě|úřad|úřadu|úřadem|úřadě|zastupitelství|zastupitelstvím|inspekce|inspekci|"
               "inspekcí|správa|správy|správě|správu|správou|ředitelství|ředitelstvím|komise|komisi|komisí|"
               "parlament|parlamentu|parlamentem|unie|unii|unií|policie|policii|policií|dvůr|dvora|dvoru|dvorem|"
               "banka|banky|bance|banku|bankou|agentura|agentury|agentuře|agenturu|agenturou|"
               "fond|fondu|fondem|komora|komory|komoře|komoru|komorou|rada|rady|radě|radu|radou|"
               "kancelář|kanceláře|kanceláři|kanceláří|archiv|archivu|archivem|institut|institutu|institutem|"
               "ústav|ústavu|ústavem|sněmovna|sněmovny|sněmovně|sněmovnu|sněmovnou|senát|senátu|senátem|"
               "vláda|vlády|vládě|vládu|vládou")
_LUGAR_PUB = (rf"(?:hl\.[ \t]*m\.[ \t]+|hlavní[ \t]+město[ \t]+|hlavního[ \t]+města[ \t]+)?[{MAY}][\w\-]*"
              rf"(?:[ \t]+[{MAY}][{MIN}]+)?(?:[ \t]+(?:nad|pod|u|v)[ \t]+[{MAY}][\w\-]*)?(?:[ \t]+(?:kraj|kraje|kraji|krajem|\d+))?")
_COMPL_PUB = (rf"(?:[ \t]+(?:v|ve|pro|při)[ \t]+{_LUGAR_PUB}"
              rf"|[ \t]+(?:sociálního[ \t]+zabezpečení|práce|policie|pro[ \t]+lidská[ \t]+práva)"
              rf"|[ \t]+[{MAY}][{MIN}]+(?:ého|ské|ní)[ \t]+(?:kraje|republiky|unie)|[ \t]+ČR"
              rf"|[ \t]+(?:města|obce|městské[ \t]+části)[ \t]+{_LUGAR_PUB}"
              rf"|[ \t]+[{MAY}][\w\-]*(?=[ \t]*[,.;)]))")
_RE_INSTITUCION = re.compile(
    rf"(?<![\w.])((?:{_ADJ})(?:[ \t]+(?:{_ADJ}|{_ADJ_MIN})){{0,2}}[ \t]+(?:{_NUCLEO_PUB})(?!\w)"
    rf"((?:{_COMPL_PUB}){{0,2}})(?:[ \t]*[–-][ \t]*pobočk[ay][ \t]+v[ \t]+{_LUGAR_PUB})?)")
_MINISTERSTVA = ("financí|vnitra|spravedlnosti|obrany|zdravotnictví|kultury|dopravy|zemědělství|"
                 "zahraničních věcí|práce a sociálních věcí|průmyslu a obchodu|životního prostředí|pro místní rozvoj|"
                 "školství, mládeže a tělovýchovy|regionálního rozvoje|informatiky|hospodářství")
_RE_INSTITUCION_DELANTE = re.compile(
    rf"(?<![\w.])((?:Ministerstv(?:o|a|u|em)[ \t]+(?:{_MINISTERSTVA})"
    r"|Úřad(?:u|em|ě)?[ \t]+(?:práce|vlády|průmyslového vlastnictví|pro ochranu osobních údajů"
    r"|pro ochranu hospodářské soutěže|pro zastupování státu ve věcech majetkových|pro civilní letectví"
    rf"|městské části[ \t]+{_LUGAR_PUB})"
    r"|Policie|Policii|Policií|Generální(?:ho|mu|m)? (?:finanční|celní) ředitelství|Soudní(?:ho|mu|m)? dv(?:ůr|ora|oru|orem)"
    r"|Evropsk(?:ý|ého|ému|ém|ým) soud(?:u|em|ě)? pro lidská práva|Poslaneck(?:á|é|ou) sněmovn[aěuy]|Poslaneckou sněmovnou"
    r"|Senát(?:u|em)?|Vl[áa]d(?:a|y|ě|u|ou)(?= České republiky| ČR))"
    rf"((?:{_COMPL_PUB}){{0,2}}))(?!\w)")
# Adjetivos de órgano local: sin complemento ("Krajský soud rozhodl…") puede ser el genérico con mayúscula de
# inicio de oración. "Nejvyšší soud", "Ústavní soud" o "Česká národní banka" son únicos y valen solos.
_PUB_LOCAL = ("Okresn", "Krajsk", "Městsk", "Obvodn", "Vrchn", "Obecn", "Finančn", "Katastráln", "Celn", "Živnostensk",
              "Stavebn", "Odvolac", "Dovolac", "Nalézac", "Insolvenčn", "Exekučn", "Příslušn", "Správn", "Policie",
              "Policii", "Policií", "Senát")
_PUB_GENERICOS = ("Odvolac", "Dovolac", "Nalézac", "Prvostupňov", "Insolvenčn", "Exekučn", "Příslušn", "Uveden",
                  "Tent", "Jin", "Všech", "Obecn", "Obecné", "Rozhodující", "Vyšší", "Nižší")


def instituciones(texto: str) -> Iterator[Hallazgo]:
    tramos = []
    for r in (_RE_INSTITUCION, _RE_INSTITUCION_DELANTE):
        for m in r.finditer(texto):
            a, b = m.start(1), m.end(1)
            valor = m.group(1)
            primera = valor.split()[0]
            if (primera.startswith(_PUB_GENERICOS) or primera in _INICIO_FALSO or primera.lower() in _ADJ_GENERICOS
                    or re.search(r"(?:ení|ání|ití|ítí|utí)$", primera)):
                continue
            n = re.search(rf"(?i)(?<!\w)(?:{_NUCLEO_PUB})(?!\w)", valor)
            nucleo = n.group() if n else ""
            if primera.endswith("ou") and not nucleo.endswith(("em", "ou", "í")):
                continue   # "Výzvou soudu": un sustantivo en -ou no concuerda con "soudu"
            if nucleo.lower().startswith(("banka", "banky", "bance", "banku", "bankou", "fond", "komor", "rad",
                                          "kancelář", "archiv", "institut", "ústav", "agentur")) and \
                    not re.search(r"(?i)národní|státní|česk|evropsk|ústřední|nejvyšší|krajsk|okresn|městsk|úřad", valor):
                continue   # una banca o un fondo privados ya los cubre organizaciones()
            if not m.group(2).strip() and primera.startswith(_PUB_LOCAL) and _INICIO_ORACION.search(texto[max(0, a - 6):a]):
                continue
            if texto[b:b + 2].lstrip(" \t").startswith(":"):
                continue   # "Matriční úřad: Městský úřad Kolín" — el rótulo no es el nombre
            tramos.append((a, b))
    for a, b in _unir(tramos):
        yield Hallazgo(EMPRESA, texto[a:b], a, b)


# --- identificadores -------------------------------------------------------------

def _rc_fecha(d: str) -> bool:
    if len(d) not in (9, 10):
        return False
    mes, dia = int(d[2:4]), int(d[4:6])
    return (1 <= mes % 50 <= 12 or 21 <= mes % 50 <= 32) and 1 <= dia <= 31


def _rc_valido(d: str) -> bool:
    if not _rc_fecha(d):
        return False
    if len(d) == 9:
        return int(d[:2]) < 54  # antes de 1954 no había dígito de control
    n = int(d)
    return n % 11 == 0 or (int(d[:9]) % 11 == 10 and d[9] == "0")


_RE_RC = re.compile(r"(?<![\d/])(\d{6})\s?/\s?(\d{3,4})(?![\d/])|(?<!\d)(?<!420-)(?<!420 )(?<!420\xa0)(\d{9,10})(?!\d)")  # tras +420 es teléfono
_CONTEXTO_RC = re.compile(r"(?:r\.\s?č\.|rodné\s+číslo|RČ|nar\.|pojištěnce)\s*:?\s*$", re.IGNORECASE)


def _rodne_cislo(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_RC.finditer(texto):
        contexto = bool(_CONTEXTO_RC.search(texto[max(0, m.start() - 25):m.start()]))
        d = m.group(3) or (m.group(1) + m.group(2))
        ok = _rc_valido(d)
        # Con diagonal y fecha posible, o con "r. č." al lado, se marca aunque el control falle
        # (erratas, documentos de prueba); sin nada de eso, solo si el control cuadra.
        if ok or (_rc_fecha(d) and (contexto or not m.group(3))):
            yield Hallazgo(RODNE_CISLO, m.group(), m.start(), m.end(), verificado=ok)


def _ico_valido(d: str) -> bool:
    s = sum(int(c) * w for c, w in zip(d[:7], range(8, 1, -1)))
    return (11 - s % 11) % 10 == int(d[7])


_RE_ICO = re.compile(r"(?:IČO?|IČ)\s*:?\s*(\d{3}\s?\d{2}\s?\d{3}|\d{2}\s\d{3}\s\d{3}|\d{8})(?!\d)")
_RE_DIC = re.compile(r"(?<![A-Z])CZ\s?(\d{8,10})(?!\d)")


def _ico_dic(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_ICO.finditer(texto):
        d = re.sub(r"\s", "", m.group(1))  # también el espacio duro (\xa0) de Word
        if _ico_valido(d):
            yield Hallazgo(ICO, m.group(1), m.start(1), m.end(1), verificado=True)
    for m in _RE_DIC.finditer(texto):
        d = m.group(1)
        ok = (len(d) == 8 and _ico_valido(d)) or _rc_valido(d)
        yield Hallazgo(DIC, m.group(), m.start(), m.end(), verificado=ok)


def _mod11(cifras: str, pesos: tuple[int, ...]) -> bool:
    cifras = cifras.zfill(len(pesos))
    return sum(int(c) * w for c, w in zip(cifras, pesos)) % 11 == 0


_BANCOS = frozenset("""0100 0300 0600 0710 0800 2010 2020 2060 2070 2100 2200 2220 2250 2260 2275 2600 2700 3030
3050 3060 3500 4000 4300 5500 5800 6000 6100 6200 6210 6300 6363 6700 6800 7910 7950 7960 7970 7990 8030 8040 8060
8090 8150 8190 8198 8220 8250 8255 8265 8500""".split())
_RE_CUENTA = re.compile(r"(?<![\d/-])(?:(\d{1,6})-)?(\d{2,10})/(\d{4})(?![\d/])")
_RE_IBAN = re.compile(r"(?<!\w)CZ\d{2}(?:\s?\d{4}){5}(?!\d)")


def _cuentas(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_CUENTA.finditer(texto):
        pref, num, banco = m.groups()
        if banco not in _BANCOS:
            continue
        if pref and not _mod11(pref, (10, 5, 8, 4, 2, 1)):
            continue
        if _mod11(num, (6, 3, 7, 9, 10, 5, 8, 4, 2, 1)) and int(num) > 0:
            yield Hallazgo(CUENTA, m.group(), m.start(), m.end(), verificado=True)
    for m in _RE_IBAN.finditer(texto):
        s = re.sub(r"\s", "", m.group())
        ok = int(s[4:] + "1235" + s[2:4]) % 97 == 1
        yield Hallazgo(CUENTA, m.group(), m.start(), m.end(), verificado=ok)


# Separadores: espacio, tabulador, espacio duro (\xa0) o guion; sin prefijo, el guion solo con contexto.
_RE_TEL = re.compile(r"(?<![\d+])(?:\+|00)420[ \t\xa0-]?[1-9]\d{2}[ \t\xa0-]?\d{3}[ \t\xa0-]?\d{3}(?!\d)"
                     r"|(?<![\d/])[2-79]\d{2}[ \t\xa0]\d{3}[ \t\xa0]\d{3}(?![\d/])")
_RE_TEL_GUION = re.compile(r"(?<![\d/\-])[2-79]\d{2}-\d{3}-\d{3}(?![\d/\-])")
_RE_NUEVE = re.compile(r"(?<![\d/.\-])[2-79]\d{8}(?![\d/])")
_CTX_TEL = re.compile(r"tel|kontakt|mobil|mob\.|GSM|volat|volejte|@|ordinac", re.IGNORECASE)


def _telefonos(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_TEL.finditer(texto):
        yield Hallazgo(TELEFONO, m.group(), m.start(), m.end())
    # Nueve dígitos seguidos: teléfono solo si cerca hay "tel", "kontakt", un correo…
    for m in [*_RE_NUEVE.finditer(texto), *_RE_TEL_GUION.finditer(texto)]:
        if _CTX_TEL.search(texto[max(0, m.start() - 45):m.start()]) and not _RE_DOC_CTX.search(
                texto[max(0, m.start() - 30):m.start()]):
            yield Hallazgo(TELEFONO, m.group(), m.start(), m.end())


_DOC = (r"(?:č(?:íslo)?\.?\s*OP|OP\s*č\.|občansk\w+\s+průkaz\w*(?:\s+č\.)?|číslo\s+průkazu|průkaz\w*\s+totožnosti(?:\s+č\.)?"
        r"|cestovní\w*\s+pas\w*(?:\s+č\.)?|pas\s+č\.|č(?:íslo)?\.?\s*pasu|číslo\s+dokladu|řidičsk\w+\s+průkaz\w*(?:\s+č\.)?)")
_RE_DOC = re.compile(rf"{_DOC}\s*:?\s*([A-Z]{{0,2}}\d{{6,9}})(?!\d)", re.IGNORECASE)
_RE_DOC_CTX = re.compile(rf"{_DOC}\s*:?\s*$", re.IGNORECASE)
# Inmuebles: la parcela y el folio del registro catastral identifican al propietario.
_RE_PARCELA = re.compile(r"(?:parc\.\s?č\.|parcel\w*\s+č\.|LV\s+č\.|list\w*\s+vlastnictví\s+č\.)\s*(?:st\.\s*)?(\d{1,6}(?:/\d{1,4})?)")
_RE_VS = re.compile(r"(?i:variabilní\w*\s+symbol\w*|VS)\s*:?\s*(\d{4,10})(?!\d)")
_RE_TJUE = re.compile(r"(?<![\w-])[CT]-\d{1,4}/\d{2}(?![\d/])")
_RE_SPZ = re.compile(rf"(?<![\w])\d[{MAY}][{MAY}0-9][ \t]?\d{{4}}(?!\w)")
_RE_SPZN = re.compile(r"(?<![\w/])\d{1,3}\s?(?:[A-Z][a-z]{0,3}|ICm|INS|EXE|Nc|Cm|To|Co|Ca|Cdo|Tdo)\s\d{1,6}/\d{4}(?:-\d+)?(?![\d/])")
_TOKEN_EXP = rf"(?:[{MAY}]{{1,5}}(?:-[\w/.\-]+)?|[{MAY}][{MIN}]{{1,3}}|\d[\w/.\-]*)"
_RE_CJ = re.compile(r"(?i:č\.\s?j\.|čj\.|sp\.\s?zn\.|spis\.\s?zn\.|spisov\w+\s+značk\w+|číslo\s+jednací|"
                    r"naše\s+značka|vaše\s+značka|evidenční\s+číslo)\s*:?[ \t]*"
                    rf"({_TOKEN_EXP}(?:[ \t]+{_TOKEN_EXP})*)")


def _documentos(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_DOC.finditer(texto):
        yield Hallazgo(FOLIO, m.group(1), m.start(1), m.end(1))
    for m in _RE_PARCELA.finditer(texto):
        yield Hallazgo(FOLIO, m.group(1), m.start(1), m.end(1))
    for m in _RE_VS.finditer(texto):
        yield Hallazgo(FOLIO, m.group(1), m.start(1), m.end(1))
    for m in _RE_TJUE.finditer(texto):
        yield Hallazgo(EXPEDIENTE, m.group(), m.start(), m.end())
    for m in _RE_SPZ.finditer(texto):
        yield Hallazgo(PLACA, m.group(), m.start(), m.end())
    for m in _RE_SPZN.finditer(texto):
        yield Hallazgo(EXPEDIENTE, m.group(), m.start(), m.end())
    for m in _RE_CJ.finditer(texto):
        valor = m.group(1).rstrip(" .")
        if re.search(r"\d", valor):
            yield Hallazgo(EXPEDIENTE, valor, m.start(1), m.start(1) + len(valor))


_RE_FECHA = re.compile(rf"(?<![\d.])\d{{1,2}}\.\s?(?:\d{{1,2}}\.\s?\d{{4}}|(?:{MESICE_TODOS})(?!\w)(?:\s?\d{{4}})?)(?![\d.]\d)")
_MONEDA = r"(?:Kč|CZK|EUR|€|USD|US\$|\$|korun(?:a|y|ou|ami)?|eur(?:a|o)?)"
_RE_MONTO = re.compile(r"(?<![\d,.])\d{1,3}(?:[ .\u00a0\u202f]\d{3})*(?:,[ \t]?\d{1,2}|,-{1,2}|,—)?\s?" + _MONEDA + r"(?!\w)"
                       r"|(?<![\d,.])\d+(?:[,.]\d+)?[ \t\u00a0](?:tis\.|tisíc\w*|mil\.|milion\w*|miliard\w*|mld\.)[ \t\u00a0]?" + _MONEDA + r"(?!\w)")


def _fechas_montos(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_FECHA.finditer(texto):
        yield Hallazgo(FECHA, m.group(), m.start(), m.end())
    for m in _RE_MONTO.finditer(texto):
        yield Hallazgo(MONTO, m.group(), m.start(), m.end())


_PSC_OBEC = rf"\d{{3}}\s?\d{{2}}[ \t]+{PALABRA}(?:[ \t]+(?:\d{{1,2}}|nad|pod|u|{PALABRA}))*(?:[ \t]*[-–][ \t]*{PALABRA})?"
_ULICE = rf"(?:{PALABRA}|nám\.|náměstí|tř\.|třída|ul\.)(?:[ \t]+(?:{PALABRA}|[a-z]{{1,3}}|nám\.|č\.\s?p\.))*[ \t]+\d{{1,5}}(?:/\d{{1,4}}[a-z]?)?[a-z]?"
_RE_DIR = re.compile(rf"(?:{_ULICE}),?[ \t]+(?:PSČ[ \t]+)?{_PSC_OBEC}|(?:{_ULICE}),?[ \t]+{PALABRA}(?:[ \t]+\d{{1,2}})?,?[ \t]+(?:PSČ[ \t]*)?\d{{3}}\s?\d{{2}}")
_RE_DIR_CTX = re.compile(rf"(?:trvale\s+bytem|bytem|bydliště|trvalé\s+bydliště|se\s+sídlem|sídlo|místo\s+podnikání|adresa|na\s+adrese|"
                         rf"v\s+ulici|ulice|místo\s+výkonu(?:\s+práce)?|doručovací\s+adresa|kontaktní\s+adresa)\s*:?[ \t]*([^\n;]{{6,120}})", re.IGNORECASE)


def _direcciones(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_DIR.finditer(texto):
        yield Hallazgo(DOMICILIO, m.group(), m.start(), m.end())
    for m in _RE_DIR_CTX.finditer(texto):
        valor = _recortar_direccion(m.group(1))
        if valor and re.search(r"\d", valor):
            yield Hallazgo(DOMICILIO, valor, m.start(1), m.start(1) + len(valor))


_RE_FIN_PSC = re.compile(rf"(?:PSČ[ \t]*)?\d{{3}}\s?\d{{2}}(?:[ \t]+{PALABRA}(?:[ \t]+(?:\d{{1,2}}|nad|pod|u|{PALABRA}))*(?:[ \t]*[-–][ \t]*{PALABRA})?)?")
_RE_FIN_NUMERO = re.compile(r"\d{1,5}(?:/\d{1,4}[a-z]?)?[a-z]?(?=\s*(?:[,;.)]|$))")


def _recortar_direccion(resto: str) -> str:
    """Después de "bytem", "se sídlem"…: hasta el PSČ con su ciudad, o hasta el número de casa."""
    resto = re.split(r",\s*(?:IČO?|DIČ|r\.\s?č\.|nar\.|tel\.|e-mail|OP)", resto)[0]
    psc = list(_RE_FIN_PSC.finditer(resto))
    if psc:
        return resto[: psc[0].end()].rstrip(" ,.")
    num = _RE_FIN_NUMERO.search(resto)
    if num and num.start() < 60:
        corte = resto[: num.end()]
        # "Chodská 1590" o "Máchova 1276, Soběslav": la ciudad tras la coma también es parte
        sigue = re.match(rf",[ \t]*{PALABRA}(?:[ \t]+(?:nad|pod|u|{PALABRA}))*(?=\s*(?:[,;.]|$))", resto[num.end():])
        return (corte + (sigue.group() if sigue else "")).rstrip(" ,.")
    return ""


def candidatos(texto: str, usar_modelo: bool = True) -> list[Hallazgo]:
    salida: list[Hallazgo] = []
    for f in (_rodne_cislo, _ico_dic, _cuentas, _telefonos, _documentos, _fechas_montos, _direcciones):
        salida += list(f(texto))
    salida += [h for h in patrones.candidatos(texto) if h.tipo in (CORREO, WEB)]
    salida += list(empresas(texto))
    salida += personas(texto, usar_modelo)
    return salida
