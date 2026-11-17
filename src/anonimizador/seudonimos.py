"""Seudonimización consistente: agrupa hallazgos en entidades, les asigna etiquetas
([PERSONA_1], [RFC_1], …), localiza todas sus apariciones y permite revertir.

El estado editable es la lista de `Entidad` (variantes, marcada sí/no, etiqueta). Las
apariciones se recalculan siempre a partir de las variantes, así que cualquier ajuste
del abogado (fusionar, separar, renombrar, añadir a mano) se refleja en todo el texto.
"""

from __future__ import annotations

import datetime
import functools
import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .detector.modelo import (
    CLABE, CORREO, CUENTA, CURP, DESMARCADOS_POR_DEFECTO, DIC, DOMICILIO, EMPRESA, EXPEDIENTE, FECHA, FOLIO, ICO,
    INE, MONTO, NINO, NOMBRE, NSS, PLACA, RFC, RODNE_CISLO, SSN, TARJETA, TELEFONO, WEB, Hallazgo,
)
from .textos import tr

FORMATO_TABLA = "anonimizador-tabla/1"

PREFIJOS = {NOMBRE: "PERSONA", EMPRESA: "EMPRESA", INE: "CLAVE_ELECTOR"}
# En un documento en inglés las etiquetas también van en inglés: la IA y el lector las entienden.
PREFIJOS_EN = {
    NOMBRE: "PERSON", EMPRESA: "COMPANY", DOMICILIO: "ADDRESS", FECHA: "DATE", MONTO: "AMOUNT",
    TELEFONO: "PHONE", CORREO: "EMAIL", WEB: "WEBSITE", CUENTA: "ACCOUNT", TARJETA: "CARD",
    PLACA: "PLATE", EXPEDIENTE: "CASE_NO", FOLIO: "ID_NO", RODNE_CISLO: "BIRTH_NO", ICO: "COMPANY_ID",
    DIC: "VAT_NO", "MANUAL": "OTHER",
}
# Igual en checo, sin diacríticos: así las reconoce el patrón de revertir y cualquier IA.
PREFIJOS_CS = {
    NOMBRE: "OSOBA", EMPRESA: "FIRMA", DOMICILIO: "ADRESA", FECHA: "DATUM", MONTO: "CASTKA",
    TELEFONO: "TELEFON", CORREO: "EMAIL", WEB: "WEB", CUENTA: "UCET", TARJETA: "KARTA",
    PLACA: "SPZ", EXPEDIENTE: "SPIS_ZN", FOLIO: "CISLO", RODNE_CISLO: "RODNE_CISLO", ICO: "ICO",
    DIC: "DIC", "MANUAL": "JINE",
}
MANUAL = "MANUAL"

# Tipos cuyo valor es un identificador: se comparan sin espacios ni guiones.
_IDENTIFICADORES = {CURP, RFC, NSS, CLABE, TARJETA, INE, FOLIO, RODNE_CISLO, ICO, DIC, SSN, NINO}

_TRATAMIENTO_SUELTO = re.compile(
    r"(?:\b(?:el|la|los|las|del|al)\s+)?(?:\bC\.|\bciudadan[oa]|\bse[ñn]or(?:a|ita)?|\bsra?\.|\blic\.|"
    r"\blicenciad[oa]|\bdon|\bdoña|\bdra?\.|\bdoctor(?:a)?|\bing\.)\s+$",
    re.IGNORECASE,
)

# --- normalización ------------------------------------------------------------


def _pliega_caracter(c: str) -> str:
    base = unicodedata.normalize("NFD", c)[0]
    return base.lower()[0]


class _TablaPliegue(dict):
    """Tabla para str.translate que se llena sola: cada carácter se calcula una vez."""

    def __missing__(self, codigo: int) -> str:
        r = self[codigo] = _pliega_caracter(chr(codigo))
        return r


_PLIEGUE = _TablaPliegue()


def plegar(texto: str) -> str:
    """Minúsculas y sin acentos, carácter por carácter: conserva la longitud."""
    return texto.translate(_PLIEGUE)


def clave(tipo: str, valor: str) -> str:
    p = plegar(valor)
    if tipo in _IDENTIFICADORES:
        return re.sub(r"[^0-9a-zñ&]", "", p)
    return re.sub(r"\s+", " ", p).strip(" ,.")


# --- modelo -------------------------------------------------------------------


@dataclass
class Entidad:
    etiqueta: str
    tipo: str
    variantes: list[str]  # textos tal como aparecen; la primera es la canónica
    marcada: bool = True
    verificado: bool = False
    derivadas: list[str] = field(default_factory=list)  # variantes inferidas (apellidos…)
    sugerida: bool = False  # la propuso la IA local (ia_local): el abogado la confirma

    @property
    def canonico(self) -> str:
        return self.variantes[0]

    @property
    def marcador(self) -> str:
        return f"[{self.etiqueta}]"

    def todas_las_variantes(self) -> list[str]:
        vistas = {clave(self.tipo, v) for v in self.variantes}
        return self.variantes + [d for d in self.derivadas if clave(self.tipo, d) not in vistas]


@dataclass(frozen=True)
class Aparicion:
    inicio: int
    fin: int
    etiqueta: str


# --- nombres: variantes derivadas ---------------------------------------------

_PARTICULAS = {"de", "del", "la", "las", "los", "y"}


def _tokens_nombre(nombre: str) -> list[str]:
    """Une las partículas con la palabra siguiente: 'Hernández de la Cruz' → 2 tokens."""
    tokens, pend = [], []
    for w in nombre.split():
        if w.lower() in _PARTICULAS:
            pend.append(w)
        else:
            tokens.append(" ".join(pend + [w]))
            pend = []
    return tokens


def _apellidos(nombre: str) -> list[str]:
    t = _tokens_nombre(nombre)
    return t[-2:] if len(t) >= 3 else t[-1:]


def _derivadas(nombre: str) -> list[str]:
    t = _tokens_nombre(nombre)
    if len(t) < 3:
        return []
    dos_apellidos = " ".join(t[-2:])
    nombre_y_primer_apellido = " ".join(t[:-1])
    primer_nombre_y_apellido = " ".join([t[0], t[-2]])
    return list(dict.fromkeys([dos_apellidos, nombre_y_primer_apellido, primer_nombre_y_apellido]))


def _contenido_en(corto: str, largo: str) -> bool:
    """¿Las palabras de `corto` aparecen, en orden y contiguas, dentro de `largo`?"""
    a, b = clave(NOMBRE, corto).split(), clave(NOMBRE, largo).split()
    return len(a) < len(b) and any(b[i:i + len(a)] == a for i in range(len(b) - len(a) + 1))


# --- agrupación ---------------------------------------------------------------


def _prefijo(tipo: str, idioma: str = "es") -> str:
    if idioma == "en":
        return PREFIJOS_EN.get(tipo, tipo)
    if idioma == "cs":
        return PREFIJOS_CS.get(tipo, tipo)
    return PREFIJOS.get(tipo, tipo)


def agrupar(hallazgos: Iterable[Hallazgo]) -> list[Entidad]:
    """Hallazgos → entidades, sin etiquetas definitivas (las pone `numerar`)."""
    grupos: dict[tuple[str, str], Entidad] = {}
    for h in sorted(hallazgos, key=lambda h: h.inicio):
        k = (h.tipo, clave(h.tipo, h.valor))
        if k not in grupos:
            grupos[k] = Entidad("", h.tipo, [h.valor], h.tipo not in DESMARCADOS_POR_DEFECTO, h.verificado)
        elif h.valor not in grupos[k].variantes:
            grupos[k].variantes.append(h.valor)

    entidades = list(grupos.values())

    # Nombres: "Pérez García" se une a "Juan Pérez García" si solo cabe en una persona.
    personas = [e for e in entidades if e.tipo == NOMBRE]
    personas.sort(key=lambda e: -len(e.canonico.split()))
    absorbidas: set[int] = set()
    for corta in personas:
        contenedoras = [
            larga for larga in personas
            if larga is not corta and id(larga) not in absorbidas
            and _contenido_en(corta.canonico, larga.canonico)
        ]
        if len(contenedoras) == 1:
            destino = contenedoras[0]
            destino.variantes += [v for v in corta.variantes if v not in destino.variantes]
            absorbidas.add(id(corta))
    entidades = [e for e in entidades if id(e) not in absorbidas]

    # Variantes derivadas (apellidos, etc.), solo si no son ambiguas entre personas.
    personas = [e for e in entidades if e.tipo == NOMBRE]
    conteo: dict[str, int] = {}
    candidatas = {id(e): _derivadas(e.canonico) for e in personas}
    for ds in candidatas.values():
        for d in ds:
            conteo[clave(NOMBRE, d)] = conteo.get(clave(NOMBRE, d), 0) + 1
    for e in personas:
        e.derivadas = [d for d in candidatas[id(e)] if conteo[clave(NOMBRE, d)] == 1]

    # Empresas: el nombre sin "S.A. de C.V." y la sigla ("Industrias Metálicas del Valle" → IMV).
    for e in entidades:
        if e.tipo == EMPRESA:
            e.derivadas = _derivadas_empresa(e.canonico)
    return entidades


_SUFIJO_EMPRESA = re.compile(
    r",?\s+(?:S\.?\s*A\.?\s*P\.?\s*I\.?|S\.?\s*A\.?\s*B\.?|S\.?\s*A\.?|S\.?\s*de\s+R\.?\s*L\.?|S\.?\s*C\.?|"
    r"A\.?\s*C\.?|S\.?\s*A\.?\s*S\.?|I\.?\s*A\.?\s*P\.?|"
    # inglés y checo
    r"Ltd|Limited|LLC|L\.L\.C|LLP|Inc|Incorporated|Corp|Corporation|PLC|L\.P|LP|GmbH|AG|N\.V|B\.V|Pty\.?\s+Ltd|"
    r"spol\.\s?s\s?r\.\s?o|s\.\s?r\.\s?o|a\.\s?s|v\.\s?o\.\s?s|k\.\s?s|z\.\s?s|z\.\s?ú|o\.\s?p\.\s?s)"
    r"(?:\s+de\s+C\.?\s*V\.?)?\.?\s*$",
    re.IGNORECASE,
)
_CONECTORES_SIGLA = {"de", "del", "la", "las", "los", "y", "e", "el", "en", "&"}


def _derivadas_empresa(razon: str) -> list[str]:
    base = _SUFIJO_EMPRESA.sub("", razon).strip(" ,")
    salida = []
    if base != razon and len(base.split()) >= 2:
        salida.append(base)
    iniciales = [w[0] for w in re.findall(r"[^\s,]+", base) if w.lower() not in _CONECTORES_SIGLA and w[0].isalpha()]
    if len(iniciales) >= 3:
        salida.append("".join(iniciales).upper())
    return salida


# --- localización -------------------------------------------------------------


def _es_limite(texto: str, i: int) -> bool:
    return i < 0 or i >= len(texto) or not texto[i].isalnum()


@functools.lru_cache(maxsize=4096)
def _patron(variante: str, tipo: str) -> re.Pattern:
    if tipo in _IDENTIFICADORES:
        # Permite que el mismo identificador aparezca con o sin separadores.
        chars = [re.escape(c) for c in clave(tipo, variante)]
        return re.compile(r"(?:\s?[\-./]\s?|\s)?".join(chars))  # "800312/1236", "800312 / 1236"
    partes = [re.escape(p) for p in plegar(variante).split()]
    return re.compile(r"\s+".join(partes))


def _busca(texto_plegado: str, texto: str, variante: str, tipo: str) -> Iterable[tuple[int, int]]:
    for m in _patron(variante, tipo).finditer(texto_plegado):
        if _es_limite(texto, m.start() - 1) and _es_limite(texto, m.end()):
            yield m.start(), m.end()


def localizar(texto: str, entidades: Iterable[Entidad], solo_marcadas: bool = True) -> list[Aparicion]:
    """Todas las apariciones de todas las variantes, sin traslapes (gana la más larga)."""
    plegado = plegar(texto)
    candidatas: list[Aparicion] = []
    personas: list[Entidad] = []
    # Lo que el abogado dejó visible reserva su lugar frente a datos más cortos del mismo tipo:
    # si desmarcó "8-sep-2026", "8-sep" no se tapa dentro de ella. Entre tipos distintos no
    # protege: los apellidos de una persona marcada se tapan aunque el despacho esté desmarcado.
    reservados: list[tuple[int, int, str]] = []
    for e in entidades:
        if solo_marcadas and not e.marcada:
            for v in e.todas_las_variantes():
                reservados += [(ini, fin, e.tipo) for ini, fin in _busca(plegado, texto, v, e.tipo)]
            continue
        for v in e.todas_las_variantes():
            for ini, fin in _busca(plegado, texto, v, e.tipo):
                candidatas.append(Aparicion(ini, fin, e.etiqueta))
        if e.tipo == NOMBRE:
            personas.append(e)
    if reservados:
        tipo_de = {e.etiqueta: e.tipo for e in entidades}
        candidatas = [a for a in candidatas if not any(
            t == tipo_de[a.etiqueta] and ini <= a.inicio and a.fin <= fin and fin - ini > a.fin - a.inicio
            for ini, fin, t in reservados)]

    # Apellido suelto tras un tratamiento ("el C. Pérez", "la señora Soto"), si es único.
    duenos: dict[str, list[Entidad]] = {}
    for e in personas:
        for a in _apellidos(e.canonico):
            duenos.setdefault(clave(NOMBRE, a), []).append(e)
    for k, es in duenos.items():
        if len(es) != 1:
            continue
        for ini, fin in _busca(plegado, texto, k, NOMBRE):
            if _TRATAMIENTO_SUELTO.search(texto[max(0, ini - 25):ini]):
                candidatas.append(Aparicion(ini, fin, es[0].etiqueta))

    candidatas.sort(key=lambda a: (-(a.fin - a.inicio), a.inicio))
    elegidas: list[Aparicion] = []
    for a in candidatas:
        if all(a.fin <= b.inicio or a.inicio >= b.fin for b in elegidas):
            elegidas.append(a)
    return sorted(elegidas, key=lambda a: a.inicio)


# --- etiquetas ----------------------------------------------------------------


def numerar(texto: str, entidades: list[Entidad], idioma: str = "es") -> list[Entidad]:
    """Asigna PERSONA_1, PERSONA_2… por orden de primera aparición en el texto."""
    plegado = plegar(texto)

    def primera(e: Entidad) -> int:
        pos = [ini for v in e.variantes for ini, _ in _busca(plegado, texto, v, e.tipo)]
        return min(pos) if pos else len(texto)

    contadores: dict[str, int] = {}
    for e in sorted(entidades, key=primera):
        p = _prefijo(e.tipo, idioma)
        contadores[p] = contadores.get(p, 0) + 1
        e.etiqueta = f"{p}_{contadores[p]}"
    return entidades


# --- checo: declinaciones ---------------------------------------------------------


def _propagar_apellidos_en(texto: str, entidades: list[Entidad]) -> None:
    """"John Smith … Mr Smith … Smith's": el apellido (y el nombre de pila) suelto es de la
    persona que lo tiene, si es una sola. "Smith" detectado aparte se une a "John Smith".
    Sin tratamientos ni iniciales: "Dr. J. Smith" y "John Smith" comparten la clave "smith"."""
    from .detector.en import PALABRAS_FUNCIONALES, TRATAMIENTOS

    trat = re.compile(rf"^(?:(?:{TRATAMIENTOS})\.?\s+)+", re.IGNORECASE)

    def palabras(nombre: str) -> list[str]:
        sin = trat.sub("", nombre)
        return [w for w in re.findall(r"[^\W\d_][\w'’\-]*", sin) if len(w) > 1 and w.lower() not in PALABRAS_FUNCIONALES]

    personas = [e for e in entidades if e.tipo == NOMBRE]
    completas = [e for e in personas if len(palabras(e.canonico)) >= 2]
    # "Ms Ward" (tratamiento + apellido) también es dueña de su apellido.
    con_trat = [e for e in personas if len(palabras(e.canonico)) == 1 and trat.match(e.canonico)]
    duenos_ap: dict[str, list[Entidad]] = {}
    duenos_pila: dict[str, list[Entidad]] = {}
    for e in completas:
        p = palabras(e.canonico)
        duenos_ap.setdefault(p[-1].lower(), []).append(e)
        duenos_pila.setdefault(p[0].lower(), []).append(e)
    # 1. "Smith" o "Mr Smith" detectado aparte → a "John Smith" si es el único Smith.
    for e in [e for e in personas if len(palabras(e.canonico)) == 1]:
        k = palabras(e.canonico)[0].lower() if palabras(e.canonico) else ""
        es = duenos_ap.get(k) or (duenos_pila.get(k) if k not in duenos_ap else None) or []
        if len(es) == 1:
            es[0].variantes += [v for v in e.variantes if v not in es[0].variantes]
            entidades.remove(e)
    # 2. Formas largas detectadas aparte ("Dr John Smith", "John A. Smith") → a "John Smith".
    for e in [e for e in entidades if e.tipo == NOMBRE and e in completas]:
        p = palabras(e.canonico)
        otros = [o for o in completas if o is not e and o in entidades
                 and palabras(o.canonico)[0].lower() == p[0].lower() and palabras(o.canonico)[-1].lower() == p[-1].lower()]
        for o in otros:
            if len(o.canonico) > len(e.canonico):
                continue
            o.variantes += [v for v in e.variantes if v not in o.variantes]
            entidades.remove(e)
            completas.remove(e)
            break
    # 3. El nombre de pila suelto ("Philomena's application"), si es de una sola persona y no es
    #    también una palabra común ("Will", "May").
    from .detector.en import _nombres

    _, ambiguos = _nombres()
    for k, es in duenos_pila.items():
        es = [e for e in es if e in entidades]
        if len(es) != 1:
            continue
        e = es[0]
        pila = palabras(e.canonico)[0]
        if len(pila) < 3 or pila in ambiguos or pila.isupper():
            continue
        for m in re.finditer(rf"(?<![\w'’-]){re.escape(pila)}(?![\w-])", texto):
            if m.group() not in e.variantes + e.derivadas:
                e.derivadas.append(m.group())
    for e in con_trat:
        k = palabras(e.canonico)[0].lower()
        if e in entidades and k not in duenos_ap:
            duenos_ap[k] = [e]
    # 4. El apellido suelto donde aparezca (también en MAYÚSCULAS), si es de una sola persona. Si
    #    lo comparten varias (Sarah y David Price), no se adivina de quién es, pero tampoco se deja
    #    a la vista: el apellido suelto queda como una persona aparte que el abogado puede unir.
    for k, es in list(duenos_ap.items()):
        es = [e for e in es if e in entidades]
        if len(es) > 1:
            ap = palabras(es[0].canonico)[-1]
            cubiertos = {clave(NOMBRE, v) for x in es for v in x.variantes + x.derivadas}
            sueltos = [m.group() for m in re.finditer(rf"(?<![\w'’-])({re.escape(ap)}|{re.escape(ap.upper())})(?![\w-])", texto)]
            if sueltos and clave(NOMBRE, ap) not in cubiertos:
                ya = next((x for x in entidades if x.tipo == NOMBRE and clave(NOMBRE, x.canonico) == clave(NOMBRE, ap)), None)
                if ya is None:
                    entidades.append(Entidad("", NOMBRE, [ap], True))
            continue
        if len(es) != 1:
            continue
        e = es[0]
        ap = palabras(e.canonico)[-1]
        for m in re.finditer(rf"(?<![\w'’-])({re.escape(ap)}|{re.escape(ap.upper())})(?![\w-])", texto):
            if m.group() not in e.variantes + e.derivadas:
                e.derivadas.append(m.group())


def _propagar_apellidos_cs(texto: str, entidades: list[Entidad]) -> None:
    """Une variantes declinadas y añade el apellido suelto en cualquier caso, si es de una sola persona."""
    from .detector.cs import PALABRA, clave_persona, raiz

    personas = [e for e in entidades if e.tipo == NOMBRE]
    # 1. Fusionar personas cuya clave por raíz coincide.
    por_clave: dict[str, Entidad] = {}
    for e in list(personas):
        k = clave_persona(e.canonico)
        if k in por_clave and por_clave[k] is not e:
            d = por_clave[k]
            d.variantes += [v for v in e.variantes if v not in d.variantes]
            entidades.remove(e)
            personas.remove(e)
        else:
            por_clave[k] = e
    # 2. Una persona de "Nombre Apellido" absorbe a la de solo "Apellido" (misma raíz).
    for e in list(personas):
        palabras = re.findall(PALABRA, e.canonico)
        if len(palabras) != 1:
            continue
        r = raiz(palabras[0])
        duenos = [o for o in personas if o is not e and len(re.findall(PALABRA, o.canonico)) >= 2
                  and raiz(re.findall(PALABRA, o.canonico)[-1]) == r]
        if len(duenos) == 1:
            duenos[0].variantes += [v for v in e.variantes if v not in duenos[0].variantes]
            entidades.remove(e)
            personas.remove(e)
    # 3. El apellido en cualquier caso, donde aparezca suelto.
    duenos_raiz: dict[str, list[Entidad]] = {}
    for e in personas:
        palabras = re.findall(PALABRA, e.canonico)
        if len(palabras) >= 2:
            duenos_raiz.setdefault(raiz(palabras[-1]), []).append(e)
    for m in re.finditer(rf"(?<!\w){PALABRA}", texto):
        es = duenos_raiz.get(raiz(m.group()), [])
        if len(es) == 1 and m.group() not in es[0].variantes + es[0].derivadas:
            es[0].derivadas.append(m.group())
    # 4. Nombre completo en otros casos ("Evy Bosákové") ya cubierto por la búsqueda de cada
    #    variante; las formas declinadas vistas en el texto se agregan como variantes.
    for m in re.finditer(rf"(?<!\w){PALABRA}[ \t]+{PALABRA}", texto):
        e = por_clave.get(clave_persona(m.group()))
        if e is not None and e in entidades and m.group() not in e.variantes:
            e.variantes.append(m.group())


# --- personas: los dos apellidos sueltos ---------------------------------------


_PUESTO = re.compile(
    r"(?:gerente|director|directora|coordinador|coordinadora|supervisor|supervisora|analista|auxiliar|"
    r"asistente|jefe|jefa|encargad[oa]|operador|operadora|contador|contadora|abogad[oa]s?|licenciad[oa]|"
    r"cuentas|andador|calle|avenida|colonia|presente|representante|apoderad[oa]|"
    # Debajo de la firma («Lic. Fernanda Ortiz Villaseñor\nSocia · Cédula…»): el cargo no es apellido.
    r"soci[oa]s?|asociad[oa]s?|titular|notari[oa]|secretari[oa]|president[ea]|consejer[oa]|tesorer[oa]|"
    r"perit[oa]|actuari[oa]|juez|jueza|magistrad[oa]|pasante|becari[oa]|practicante|vocal|"
    r"mediador|mediadora|conciliador|conciliadora|fundador|fundadora)$",
    re.IGNORECASE,
)


_RE_PALABRA_CAPITAL = re.compile(r"(?<![\w])[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?![\w])")
# Nombres de pila que también son palabras o lugares comunes: sueltos no se tocan.
_PILA_AMBIGUOS = {
    "rosa", "luz", "paz", "sol", "victoria", "dolores", "pilar", "mercedes", "angeles", "guadalupe",
    "jesus", "cruz", "rocio", "esperanza", "gloria", "flor", "consuelo", "socorro", "amparo", "asuncion",
    "concepcion", "soledad", "trinidad", "mar", "alma", "aurora", "estrella", "perla", "iris", "celeste",
    "cielo", "salvador", "santiago", "reyes", "rey", "leal", "franco", "bello", "angel", "clemente",
    "prudencio", "modesto", "justo", "fidel", "inocencio", "patricio", "pastor", "rosario", "lucero",
    "abril", "mayo", "armando", "blanca", "gracia", "martin", "domingo", "leon", "cesar", "valentin",
}
_SIGLAS = {"CURP", "RFC", "NSS", "INE", "IFE", "CLABE", "IMSS", "INFONAVIT", "SAT", "CP", "TEL", "CEL", "DNI"}


def ligar_apellidos(texto: str, entidades: list[Entidad]) -> None:
    """"Ríos Calderón vs. IMV": si la persona se detectó como "María Fernanda Ríos", su
    apellido seguido de otro apellido también es ella (siempre que nadie más lo tenga)."""
    from .detector.nombres import _palabra_de_nombre

    personas = [e for e in entidades if e.tipo == NOMBRE]
    duenos: dict[str, list[Entidad]] = {}
    for e in personas:
        t = _tokens_nombre(e.canonico)
        if len(t) >= 2:
            duenos.setdefault(clave(NOMBRE, t[-1]), []).append(e)
    for e in personas:
        t = _tokens_nombre(e.canonico)
        if len(t) < 2 or len(duenos.get(clave(NOMBRE, t[-1]), [])) != 1:
            continue
        apellido = t[-1]
        # Un salto de línea sencillo es el renglón siguiente del PDF; dos, otro párrafo.
        patron = re.compile(rf"(?<!\w){re.escape(apellido)}(?:[ \t]+|[ \t]*\n[ \t]*)([^\W\d_][\w'-]+)", re.IGNORECASE)
        conocidas = {clave(NOMBRE, v) for v in e.todas_las_variantes()}
        for m in patron.finditer(texto):
            segundo = m.group(1)
            if (not _palabra_de_nombre(segundo) or segundo.isupper() != m.group(0).split()[0].isupper()
                    or _PUESTO.match(segundo) or len(segundo) < 3 or segundo.upper() in _SIGLAS):
                continue
            if any(len(_tokens_nombre(o.canonico)) >= 2 and clave(NOMBRE, segundo) == clave(NOMBRE, _tokens_nombre(o.canonico)[0])
                   for o in personas):
                continue  # "Ríos Paola…": el siguiente es el nombre de otra persona
            par = m.group(0)
            for nueva in (par, f"{e.canonico} {segundo}"):
                if clave(NOMBRE, nueva) not in conocidas:
                    e.derivadas.append(nueva)
                    conocidas.add(clave(NOMBRE, nueva))


# --- empresas: cuáles llegan marcadas -----------------------------------------

# Una empresa llega marcada si es parte del asunto o si su nombre delata a una persona
# (un despacho con los apellidos de sus socios). Las demás (bancos, dependencias,
# proveedores mencionados de paso) llegan desmarcadas: la IA suele necesitarlas.
_CONTEXTO_PARTE = re.compile(
    r"\b(?:demandad[oa]s?|actor(?:a|es)?|part(?:e|es)\s+(?:actora|demandada|contratante)|patr[oó]n(?:al)?|"
    r"empleador(?:a)?|contratante|contratista|arrendador(?:a)?|arrendatari[oa]|deudor(?:a)?|acreedor(?:a)?|"
    r"quejos[oa]|tercer[oa]\s+interesad[oa]|en\s+contra\s+de|vs\.?|contra|la\s+empresa|la\s+sociedad|"
    r"denominada|en\s+lo\s+sucesivo|representante\s+legal\s+de|apoderad[oa]\s+(?:legal\s+)?de|"
    r"prest[oóa]b?a?\s+sus\s+servicios|laboraba|labor[oó]|trabaj(?:aba|ó)\s+(?:para|en)|"
    r"(?:persona\s+)?citad[oa]|empresa\s*:|patr[oó]n\s*:|empleador\s*:|present\s?e|"
    # checo: partes de contratos, procesos y facturas
    r"prodávající|kupující|pronajímatel|nájemce|zaměstnavatel|zaměstnanec|dodavatel|odběratel|objednatel|"
    r"zhotovitel|žalobce|žalovan[ýá]|věřitel|dlužník|zmocnitel|zmocněnec|pojistník|pojištěn[ýá]|klient|"
    r"smluvní\s+stran[ay]|IČO?\s*:?|se\s+sídlem|zastoupen[áý]|"
    # inglés: partes de contratos, juicios y cartas
    r"between|employer|employee|landlord|tenant|lessor|lessee|seller|buyer|purchaser|vendor|contractor|"
    r"supplier|customer|client|claimant|defendant|plaintiff|respondent|petitioner|borrower|lender|"
    r"guarantor|disclosing\s+party|receiving\s+party|the\s+company|hereinafter|company\s+id|"
    r"registered\s+office|employed\s+by|worked\s+(?:for|at)|on\s+behalf\s+of|v\.)\b",
    re.IGNORECASE,
)
# Inglés: "X v Y", "instructed by", la aseguradora que emite la póliza…
_CONTEXTO_PARTE_EN = re.compile(
    r"(?:\b(?:v|vs)\.?\s*$|^\s*v\.?\s|\b(?:issued|instructed|insured|underwritten|operated|owned|managed|"
    r"offered|signed)\s+by\b|\b(?:insurer|carrier|policyholder|interests?\s+in|shares?\s+in|director\s+of|"
    r"for\s+and\s+on\s+behalf\s+of|re:)\b|"
    # La otra parte de un acuerdo o pleito: "settlement agreement with X", "claim against X",
    # "between X and Y", "the Landlord, X". Con "with" solo no basta ("we bank with Barclays").
    r"\b(?:agreement|contract|settlement|lease|dispute|claim|lawsuit|litigation|negotiations?|deal|"
    r"arbitration|proceedings)\s+(?:with|against|between)\b|"
    r"\b(?:against|between|sued|plaintiffs?|defendants?|claimants?|respondents?|appellants?|landlord|"
    r"tenant|employer|counterparty|seller|buyer|vendor|purchaser|lessor|lessee|licensor|licensee)\b)",
    re.IGNORECASE,
)
_DESPACHO = re.compile(r"\b(?:abogad[oa]s|asociad[oa]s|despacho|bufete|consultores|legal|contadores)\b|,?\s+S\.?\s?C\.?$",
                       re.IGNORECASE)
_VENTANA = 80


def sugerir_empresas(texto: str, entidades: list[Entidad], idioma: str = "es") -> None:
    apellidos = {
        clave(NOMBRE, w)
        for e in entidades if e.tipo == NOMBRE
        for tok in _tokens_nombre(e.canonico)[1:] for w in tok.split()
        if len(w) >= 4 and w.lower() not in _PARTICULAS
    }
    empresas = [e for e in entidades if e.tipo == EMPRESA]
    veces = {e.etiqueta: len(localizar(texto, [e], solo_marcadas=False)) for e in empresas}
    # La que domina el documento (membrete, recibos, registros) casi siempre es una parte.
    principal = max(empresas, key=lambda e: veces[e.etiqueta], default=None)
    if principal and veces[principal.etiqueta] >= 3:
        principal.marcada = True
    for e in empresas:
        palabras = {clave(NOMBRE, w) for w in re.findall(r"\w+", e.canonico)}
        if palabras & apellidos or _DESPACHO.search(e.canonico):
            e.marcada = True
            continue
        for a in localizar(texto, [e], solo_marcadas=False):
            antes = texto[max(0, a.inicio - _VENTANA):a.inicio]
            despues = texto[a.fin:a.fin + _VENTANA // 2]
            if _CONTEXTO_PARTE.search(antes) or _CONTEXTO_PARTE.search(despues):
                e.marcada = True
                break
            if idioma == "en" and (_CONTEXTO_PARTE_EN.search(antes[-40:]) or _CONTEXTO_PARTE_EN.search(despues[:8])
                                   or not texto[:a.inicio].strip("\n -—|*#").count("\n") > 2):
                e.marcada = True  # también el membrete: la empresa en los primeros renglones
                break


# --- operaciones de revisión --------------------------------------------------


class Sesion:
    """Estado de la revisión de un documento (o de varios: ver `flujo.Flujo`, que les pasa el
    texto de todos unido con un separador y los hallazgos ya recorridos a esa posición)."""

    def __init__(self, texto: str, hallazgos: Iterable[Hallazgo], idioma: str = "es"):
        self.texto = texto
        self.idioma = idioma
        entidades = agrupar(hallazgos)
        if idioma == "cs":
            _propagar_apellidos_cs(texto, entidades)
        elif idioma == "en":
            _propagar_apellidos_en(texto, entidades)
        self.entidades = numerar(texto, entidades, idioma)
        self._retiradas: set[str] = set()  # etiquetas que ya existieron: no se reciclan
        if idioma != "en":  # reglas del español ("Ríos Calderón", nombres de pila de la lista)
            ligar_apellidos(texto, self.entidades)
            self._ligar_nombres_de_pila()
        sugerir_empresas(texto, self.entidades, idioma)

    def _ligar_nombres_de_pila(self, texto: str | None = None) -> None:
        """"Entré con Arturo", "Jorge quiere el borrador": un nombre de pila suelto es de la
        persona del documento que lo tiene (si es una sola) o, si nadie lo tiene, una persona
        nueva. Si lo comparten dos, no se adivina: lo decide el abogado."""
        from .detector.nombres import DE_PILA, _parece_lugar, _sin_acentos

        texto = self.texto if texto is None else texto
        cubierto = bytearray(len(texto))
        for a in localizar(texto, self.entidades, solo_marcadas=False):
            cubierto[a.inicio:a.fin] = b"\x01" * (a.fin - a.inicio)
        personas = [e for e in self.entidades if e.tipo == NOMBRE]
        nuevas: dict[str, Entidad] = {}
        for m in _RE_PALABRA_CAPITAL.finditer(texto):
            palabra = m.group(0)
            base = _sin_acentos(palabra)
            if base not in DE_PILA or base in _PILA_AMBIGUOS or cubierto[m.start()]:
                continue
            siguiente = re.match(r"[ \t]+(\S)", texto[m.end():m.end() + 3])
            anterior = re.search(r"(\S+)[ \t]+$", texto[max(0, m.start() - 30):m.start()])
            if (siguiente and siguiente.group(1).isupper()) or (anterior and anterior.group(1)[0].isupper()
                                                                  and not anterior.group(1).endswith(".")):
                continue  # pegado a otra palabra con mayúscula: o ya es un nombre o es otra cosa
            if _parece_lugar(texto, m.start(), m.end()):
                continue
            duenos = [e for e in personas if _sin_acentos(_tokens_nombre(e.canonico)[0]) == base]
            if len(duenos) == 1:
                if clave(NOMBRE, palabra) not in {clave(NOMBRE, v) for v in duenos[0].todas_las_variantes()}:
                    duenos[0].derivadas.append(palabra)
            elif not duenos and base not in nuevas:
                e = Entidad(self._siguiente(NOMBRE), NOMBRE, [palabra], True)
                nuevas[base] = e
                self.entidades.append(e)

    def entidad(self, etiqueta: str) -> Entidad:
        for e in self.entidades:
            if e.etiqueta == etiqueta:
                return e
        raise KeyError(etiqueta)

    def marcar(self, etiqueta: str, marcada: bool = True) -> None:
        self.entidad(etiqueta).marcada = marcada

    def renombrar(self, etiqueta: str, nueva: str) -> str:
        nueva = re.sub(r"[^0-9A-Za-zÁÉÍÓÚÑáéíóúñ_]", "_", nueva.strip().strip("[]")).upper()
        if not nueva:
            raise ValueError(tr('La etiqueta no puede quedar vacía.'))
        if any(e.etiqueta == nueva for e in self.entidades):
            raise ValueError(tr('Ya existe la etiqueta {nueva}.', nueva=nueva))
        self._retiradas.add(etiqueta)
        self.entidad(etiqueta).etiqueta = nueva
        return nueva

    def fusionar(self, destino: str, origen: str) -> None:
        d, o = self.entidad(destino), self.entidad(origen)
        d.variantes += [v for v in o.variantes if v not in d.variantes]
        d.derivadas += [v for v in o.derivadas if v not in d.derivadas]
        self._retiradas.add(origen)
        self.entidades.remove(o)

    def separar(self, etiqueta: str, variante: str) -> Entidad:
        e = self.entidad(etiqueta)
        if variante not in e.variantes or len(e.variantes) == 1:
            raise ValueError(tr('Solo se puede separar una variante de una entidad que tenga varias.'))
        e.variantes.remove(variante)
        nueva = Entidad(self._siguiente(e.tipo), e.tipo, [variante], e.marcada)
        self.entidades.append(nueva)
        return nueva

    def agregar_manual(self, valor: str, tipo: str = MANUAL) -> Entidad:
        valor = valor.strip()
        if not valor:
            raise ValueError(tr('Escribe el texto que quieres ocultar.'))
        for e in self.entidades:
            if e.tipo == tipo and clave(tipo, valor) in {clave(tipo, v) for v in e.variantes}:
                e.marcada = True
                return e
        e = Entidad(self._siguiente(tipo), tipo, [valor], True)
        if not localizar(self.texto, [e]):
            raise ValueError(tr('«{valor}» no aparece en el documento. Revisa cómo está escrito.', valor=valor))
        self.entidades.append(e)
        return e

    def _siguiente(self, tipo: str) -> str:
        p = _prefijo(tipo, getattr(self, "idioma", "es"))
        vivas = [e.etiqueta for e in self.entidades] + list(self._retiradas)
        usados = {int(m.group(1)) for t in vivas if (m := re.fullmatch(rf"{p}_(\d+)", t))}
        n = 1
        while n in usados:
            n += 1
        return f"{p}_{n}"

    # --- proyectos de varios documentos ---

    def incorporar(self, texto: str, hallazgos: Iterable[Hallazgo], texto_total: str) -> list[Entidad]:
        """Suma un documento a una revisión en curso sin deshacer lo que el abogado ya decidió
        (marcas, etiquetas, uniones, separaciones y agregados a mano).

        `texto` es el del documento nuevo (los hallazgos se refieren a él) y `texto_total` el
        combinado que queda en la sesión. Lo que ya cubre una entidad existente no se vuelve a
        proponer; lo nuevo recibe etiquetas que siguen la numeración (sin reciclar retiradas).
        Devuelve las entidades nuevas que salieron del detector."""
        self.texto = texto_total
        cubierto = bytearray(len(texto))
        for a in localizar(texto, self.entidades, solo_marcadas=False):
            cubierto[a.inicio:a.fin] = b"\x01" * (a.fin - a.inicio)
        por_clave = {(e.tipo, clave(e.tipo, v)): e for e in self.entidades for v in e.variantes}
        resto = []
        for h in hallazgos:
            if h.fin > h.inicio and all(cubierto[h.inicio:h.fin]):
                continue
            e = por_clave.get((h.tipo, clave(h.tipo, h.valor)))
            if e is not None:
                if h.valor not in e.variantes:
                    e.variantes.append(h.valor)
                continue
            resto.append(h)

        nuevas = agrupar(resto)
        personas = [e for e in self.entidades if e.tipo == NOMBRE]
        # "Pérez García" en el documento nuevo es de la persona que ya estaba, si solo cabe en una.
        for n in [e for e in nuevas if e.tipo == NOMBRE]:
            contenedoras = [p for p in personas if _contenido_en(n.canonico, p.canonico)]
            if len(contenedoras) == 1:
                destino = contenedoras[0]
                destino.variantes += [v for v in n.variantes if v not in destino.variantes]
                nuevas.remove(n)
        # Las variantes inferidas que ahora comparten dos personas dejan de ser de ninguna.
        nuevas_personas = [e for e in nuevas if e.tipo == NOMBRE]
        claves_viejas = {clave(NOMBRE, v) for p in personas for v in p.todas_las_variantes()}
        claves_nuevas = {clave(NOMBRE, v) for n in nuevas_personas for v in n.todas_las_variantes()}
        for n in nuevas_personas:
            n.derivadas = [d for d in n.derivadas if clave(NOMBRE, d) not in claves_viejas]
        for p in personas:
            p.derivadas = [d for d in p.derivadas if clave(NOMBRE, d) not in claves_nuevas]

        plegado = plegar(texto)

        def primera(e: Entidad) -> int:
            pos = [ini for v in e.variantes for ini, _ in _busca(plegado, texto, v, e.tipo)]
            return min(pos) if pos else len(texto)

        for e in sorted(nuevas, key=primera):
            e.etiqueta = self._siguiente(e.tipo)
            self.entidades.append(e)
        if self.idioma != "en":
            ligar_apellidos(texto, self.entidades)
            self._ligar_nombres_de_pila(texto)
        empresas = [e for e in nuevas if e.tipo == EMPRESA]
        if empresas:  # solo se sugieren las nuevas: las que ya estaban las decidió el abogado
            sugerir_empresas(texto, [e for e in self.entidades if e.tipo == NOMBRE] + empresas, self.idioma)
        return nuevas

    def retirar_ausentes(self, texto_total: str) -> list[Entidad]:
        """Tras quitar un documento: deja solo las entidades que siguen apareciendo en lo que
        queda. Sus etiquetas no se reciclan. Devuelve las retiradas."""
        self.texto = texto_total
        fuera = [e for e in self.entidades if not localizar(texto_total, [e], solo_marcadas=False)]
        for e in fuera:
            self._retiradas.add(e.etiqueta)
            self.entidades.remove(e)
        return fuera

    # --- resultados ---

    def apariciones(self) -> list[Aparicion]:
        return localizar(self.texto, self.entidades)

    def texto_limpio(self) -> str:
        return aplicar(self.texto, self.apariciones(), self.entidades)

    def tabla(self, archivo: str | Path | None = None, contenido: bytes | None = None) -> dict:
        return construir_tabla(self.entidades, archivo, contenido)


def aplicar(texto: str, apariciones: Iterable[Aparicion], entidades: Iterable[Entidad]) -> str:
    marcadores = {e.etiqueta: e.marcador for e in entidades}
    partes, pos = [], 0
    for a in sorted(apariciones, key=lambda a: a.inicio):
        partes += [texto[pos:a.inicio], marcadores[a.etiqueta]]
        pos = a.fin
    partes.append(texto[pos:])
    return "".join(partes)


# --- tabla y reversión --------------------------------------------------------


def construir_tabla(entidades: Iterable[Entidad], archivo=None, contenido: bytes | None = None) -> dict:
    return {
        "formato": FORMATO_TABLA,
        "aviso": tr('Contiene los datos reales del documento. No la compartas ni la subas a ninguna IA.'),
        "creada": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "documento": {
            "archivo": Path(archivo).name if archivo else None,
            "sha256": hashlib.sha256(contenido).hexdigest() if contenido is not None else None,
        },
        "entidades": [
            {"etiqueta": e.etiqueta, "tipo": e.tipo, "original": e.canonico, "variantes": e.variantes}
            for e in entidades if e.marcada
        ],
    }

_INVISIBLES = "[\u200b-\u200d\u2060\ufeff]*"
_SEP = r"(?:\\?[_ \t\xa0-])"  # guion bajo (también escapado: \_), espacio o guion


def _patron_etiqueta(etiqueta: str) -> str:
    *palabras, numero = re.split(r"[_ ]", etiqueta)
    cuerpo = f"{_SEP}+".join(re.escape(p) for p in palabras) + f"{_SEP}*0*{re.escape(numero)}"
    abre, cierra = rf"\\?\[{_INVISIBLES}\s*{_INVISIBLES}", rf"{_INVISIBLES}\s*{_INVISIBLES}\\?\]"
    return rf"({abre}{cuerpo}{cierra}|(?<!\w){cuerpo}(?!\w))"


def reemplazos(texto: str, tabla: dict) -> list[tuple[int, int, str]]:
    """(inicio, fin, valor real) de cada etiqueta de la tabla que aparece en `texto`.

    Tolera variaciones comunes que introducen los modelos: sin corchetes, con espacio o
    guion en lugar de guion bajo, sin separador, con ceros a la izquierda, en minúsculas,
    escapada como Markdown, con caracteres invisibles o varias en un mismo corchete
    ("[Persona 1]", "PERSONA-1", "[PERSONA01]", "\\[PERSONA\\_1\\]", "[PERSONA_1 y PERSONA_2]"). El valor real
    sale en un solo renglón: un domicilio partido por el diseño del PDF no parte el escrito.
    """
    if tabla.get("formato") != FORMATO_TABLA:
        raise ValueError(tr('El archivo no es una tabla de equivalencias del anonimizador.'))
    alternativas, valores = [], []
    # Las etiquetas más largas primero (PERSONA_10 antes que PERSONA_1).
    for e in sorted(tabla["entidades"], key=lambda e: len(e["etiqueta"]), reverse=True):
        alternativas.append(_patron_etiqueta(e["etiqueta"]))
        valores.append(re.sub(r"\s+", " ", e["original"]).strip())
    if not alternativas:
        return []
    patron = re.compile("|".join(alternativas), re.IGNORECASE)
    return [(m.start(), m.end(), valores[m.lastindex - 1]) for m in patron.finditer(texto)]


def revertir(texto: str, tabla: dict) -> str:
    """Sustituye las etiquetas en la respuesta de la IA por los valores originales."""
    partes, pos = [], 0
    for ini, fin, valor in reemplazos(texto, tabla):
        partes += [texto[pos:ini], valor]
        pos = fin
    partes.append(texto[pos:])
    return "".join(partes)


_LETRAS = r"[^\W\d_]"
_RE_ETIQUETA = re.compile(  # entre corchetes con guion bajo: cualquier palabra (la IA inventó [CLIENTE_1])
    rf"\\?\[{_INVISIBLES}\s*({_LETRAS}+(?:\\?_{_LETRAS}+)*\\?_\d+){_INVISIBLES}\s*\\?\]")


@functools.lru_cache(maxsize=1)
def _raices_de_etiqueta() -> str:
    """Raíz de cada palabra con que empieza una etiqueta, en los tres idiomas (PERS, OSOB, FIRM…)."""
    from .detector import modelo
    palabras = {v for v in vars(modelo).values() if isinstance(v, str) and re.fullmatch(r"[A-Z_]{3,}", v)}
    for d in (PREFIJOS, PREFIJOS_EN, PREFIJOS_CS):
        palabras |= set(d.values())
    raices = {p.split("_")[0][:4] for p in palabras}
    return "|".join(sorted(raices, key=len, reverse=True))


def etiquetas_desconocidas(texto: str, tabla: dict) -> list[str]:
    """Lo que, ya revertido el texto, sigue pareciendo una etiqueta: la IA la inventó, la
    deformó (la declinó, la tradujo, le cambió el número) o viene de otro documento. Se
    avisa para que nadie crea que se revirtió todo: un dato real nunca se pierde en silencio."""
    # Se revisa el texto con un hueco donde va cada dato real, NUNCA con el dato: así un aviso
    # no puede contener un dato real («RFC [RFC_1]» no se lee como la etiqueta «RFC GODE561231»).
    partes, pos = [], 0
    for ini, fin, _ in reemplazos(texto, tabla):
        partes += [texto[pos:ini], "\x00"]
        pos = fin
    resto = "".join(partes) + texto[pos:]
    raices = _raices_de_etiqueta()
    # Con la raíz de una etiqueta (también declinada o en minúsculas si va entre corchetes:
    # [Osobě 1]); sin corchetes, solo en mayúsculas (OSOBA_1ovi), para no avisar de «persona 1».
    corchetes = re.compile(rf"\\?\[{_INVISIBLES}\s*(?:{raices}){_LETRAS}*(?:{_SEP}+{_LETRAS}+)*{_SEP}*\d+"
                           rf"{_INVISIBLES}\s*\\?\]", re.IGNORECASE)
    sueltas = re.compile(rf"(?<!\w)(?:{raices})[A-ZÁ-Ž]*(?:\\?_[A-ZÁ-Ž]+)*{_SEP}*\d+\w*")
    vistas: list[str] = []
    for m in [*_RE_ETIQUETA.finditer(resto), *corchetes.finditer(resto), *sueltas.finditer(resto)]:
        if m.group(0) not in vistas and not any(m.group(0) in v for v in vistas):
            vistas.append(m.group(0))
    return vistas
