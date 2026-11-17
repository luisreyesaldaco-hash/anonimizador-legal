"""Detección por patrones (regex + validadores) de datos sensibles en texto plano.

Cada detector produce candidatos; `detectar()` resuelve los traslapes quedándose con
el de mayor prioridad (y, a igual prioridad, con el más largo).
"""

from __future__ import annotations

import re
from typing import Callable, Iterable, Iterator

from . import validadores as v

from .modelo import (
    CLABE, CORREO, CUENTA, CURP, DOMICILIO, EXPEDIENTE, FECHA, FOLIO, INE, MONTO, NSS, PLACA,
    RFC, TARJETA, TELEFONO, WEB, Hallazgo,
)

_I = re.IGNORECASE
_NO_ALNUM_ANTES = r"(?<![A-Za-z0-9ÑñÁÉÍÓÚáéíóú&])"
_NO_ALNUM_DESPUES = r"(?![A-Za-z0-9ÑñÁÉÍÓÚáéíóú&])"
_SEP = r"[ \-]?"  # separador opcional dentro de números (espacio o guion)


def _compacta(s: str) -> str:
    return re.sub(r"[\s\-.]", "", s).upper()


def _contexto_antes(texto: str, inicio: int, patron: re.Pattern, ventana: int = 40) -> bool:
    return patron.search(texto[max(0, inicio - ventana):inicio]) is not None


# --- detectores ---------------------------------------------------------------

_RE_CURP = re.compile(
    _NO_ALNUM_ANTES + r"[A-Z][AEIOUX][A-Z]{2}\d{6}[HMX][A-Z]{5}[0-9A-Z]\d" + _NO_ALNUM_DESPUES, _I
)


def _curp(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_CURP.finditer(texto):
        c = m.group().upper()
        estructura = v.fecha_yymmdd_valida(c[4:10]) and c[11:13] in v._ENTIDADES
        if estructura:
            yield Hallazgo(CURP, m.group(), m.start(), m.end(), v.curp_valida(c))


_RE_INE = re.compile(_NO_ALNUM_ANTES + r"[A-Z]{6}\d{8}[HM]\d{3}" + _NO_ALNUM_DESPUES, _I)


def _ine(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_INE.finditer(texto):
        c = m.group().upper()
        if v.fecha_yymmdd_valida(c[6:12]):
            yield Hallazgo(INE, m.group(), m.start(), m.end())


_RE_RFC = re.compile(
    _NO_ALNUM_ANTES + r"([A-ZÑ&]{3,4})[ \-]?(\d{6})(?:[ \-]?((?-i:[A-Z0-9]{3})))?" + _NO_ALNUM_DESPUES, _I
)


_NO_ALNUM_TRAS_FECHA = re.compile(_NO_ALNUM_DESPUES)


def _rfc(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_RFC.finditer(texto):
        letras, fecha, homo = m.group(1).upper(), m.group(2), (m.group(3) or "").upper()
        if not v.fecha_yymmdd_valida(fecha):
            continue
        if homo and v.rfc_estructura_valida(letras + fecha + homo):
            yield Hallazgo(RFC, m.group(), m.start(), m.end(), v.rfc_valido(letras + fecha + homo))
        elif len(letras) == 4 and _NO_ALNUM_TRAS_FECHA.match(texto, m.end(2)):
            # RFC de persona física sin homoclave (p. ej. "COMG600703").
            yield Hallazgo(RFC, texto[m.start():m.end(2)], m.start(), m.end(2))


_RE_DIGITOS = re.compile(r"(?<![\d])\d(?:" + _SEP + r"\d){9,18}(?![\d])")
_CTX_CLABE = re.compile(r"clabe", _I)
_CTX_NSS = re.compile(r"\bNSS\b|seguro social|seguridad social|IMSS|afiliaci[oó]n", _I)
_CTX_TARJETA = re.compile(r"tarjeta", _I)


def _numeros(texto: str) -> Iterator[Hallazgo]:
    """CLABE, tarjeta y NSS: corridas de dígitos validadas por checksum o contexto."""
    for m in _RE_DIGITOS.finditer(texto):
        d = v.solo_digitos(m.group())
        s, e, val = m.start(), m.end(), m.group()
        if len(d) == 18 and (v.clabe_valida(d) or _contexto_antes(texto, s, _CTX_CLABE)):
            yield Hallazgo(CLABE, val, s, e, v.clabe_valida(d))
        elif 13 <= len(d) <= 19 and (v.tarjeta_valida(d) or _contexto_antes(texto, s, _CTX_TARJETA)):
            yield Hallazgo(TARJETA, val, s, e, v.tarjeta_valida(d))
        elif len(d) == 11 and (v.nss_valido(d) or _contexto_antes(texto, s, _CTX_NSS)):
            yield Hallazgo(NSS, val, s, e, v.nss_valido(d))


_RE_CUENTA = re.compile(
    r"\bcuenta(?:\s+(?:bancaria|de\s+cheques|de\s+ahorro|de\s+dep[oó]sito))?"
    r"(?:\s+(?:n[uú]mero|n[uú]m\.|no\.))?\s*:?\s*"
    r"(\d(?:[ \-]?\d){6,19})(?!\d)",
    _I,
)


def _cuenta(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_CUENTA.finditer(texto):
        yield Hallazgo(CUENTA, m.group(1), m.start(1), m.end(1))


_RE_CORREO = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)*\.[A-Za-z]{2,}")


# El OCR suele leer mal la arroba (O, W, 0, ©, ® según la fuente). Se acepta cualquier
# mayúscula, dígito o símbolo de ese tipo entre un usuario y un dominio en minúsculas con
# terminación conocida: "MercadoLibre.com" o "MEXICO.com" no cuadran porque la mayúscula
# va al inicio de la palabra.
_RE_CORREO_OCR = re.compile(
    r"(?<![A-Za-z0-9._%+\-])[a-z0-9._%+\-]*[a-z][a-z0-9._%+\-]*(?:[A-Z0-9©®]|\(a\))"
    r"[a-z0-9\-]+(?:\.[a-z0-9\-]+)*\.(?:com|net|org|edu|gob|info|io|es|mx)(?:\.mx)?(?![A-Za-z0-9])"
)


def _correo(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_CORREO.finditer(texto):
        yield Hallazgo(CORREO, m.group(), m.start(), m.end())
    for m in _RE_CORREO_OCR.finditer(texto):
        yield Hallazgo(CORREO, m.group(), m.start(), m.end())


_RE_TELEFONO = re.compile(
    r"(?<![\d+])(?:\+?52[ .\-]?)?(?:\(\d{2,3}\)[ .\-]?|\d{2,3}[ .\-]?)\d{3,4}[ .\-]?\d{4}(?![\d])"
)


def _telefono(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_TELEFONO.finditer(texto):
        d = v.solo_digitos(m.group())
        if len(d) == 10 or (len(d) == 12 and d.startswith("52")):
            yield Hallazgo(TELEFONO, m.group(), m.start(), m.end())


_RE_EXPEDIENTE = re.compile(
    r"\b(?:expediente|exp\.|toca|cuaderno|causa\s+penal|carpeta\s+de\s+investigaci[oó]n"
    r"|amparo(?:\s+(?:directo|indirecto|en\s+revisi[oó]n))?|juicio(?:\s+[a-záéíóúñ]+){0,4}?"
    r"|n[uú]mero\s+de\s+identificaci[oó]n\s+[uú]nico)"
    r"(?:\s+(?:n[uú]mero|n[uú]m\.|no\.))?\s*:?\s*"
    r"([A-Z0-9][A-Z0-9\-/]*\d[A-Z0-9\-/]*)",
    _I,
)


def _expediente(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_EXPEDIENTE.finditer(texto):
        valor = m.group(1).rstrip("-/")
        # Un número de expediente casi siempre lleva "/" (123/2024) o es largo.
        if "/" in valor or len(v.solo_digitos(valor)) >= 5:
            yield Hallazgo(EXPEDIENTE, valor, m.start(1), m.start(1) + len(valor))


# Folios con contexto. Basta detectarlos una vez: después se buscan en todo el documento
# (con o sin guiones), así que también se tapan sueltos en encabezados y pies de página.
_RE_FOLIO = re.compile(
    r"\b(?:(?:n[uú]mero|n[uú]m\.|no\.)\s+(?:de\s+)?(?:emplead[oa]|n[oó]mina|trabajador[a]?|colaborador[a]?|credencial)"
    r"|registro\s+patronal(?:\s+(?:IMSS|ante\s+el\s+IMSS|del\s+IMSS))?(?:\s+\([^)\n]{0,30}\))?"
    r"|c[eé]dulas?\s+profesional(?:es)?(?:\s+(?:n[uú]mero|n[uú]m\.|no\.))?|c[eé]d\."
    r"|matr[ií]cula|folio(?:\s+fiscal)?|clave\s+interna|pasaporte|licencia\s+de\s+conducir)"
    r"\s*:?\s*",
    _I,
)
_VALOR_FOLIO = re.compile(r"[A-Z0-9][A-Z0-9\-/]*\d[A-Z0-9\-/]*", _I)
_SIGUIENTE_FOLIO = re.compile(r"\s*(?:,|\by\b|\be\b)\s*", _I)  # "cédulas 98417203 y 98652914"
_RE_REGISTRO_PATRONAL = re.compile(_NO_ALNUM_ANTES + r"[A-Z]\d{2}-\d{5}-\d{2}-\d" + _NO_ALNUM_DESPUES)


def _folio(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_FOLIO.finditer(texto):
        pos = m.end()
        while True:
            v_ = _VALOR_FOLIO.match(texto, pos)
            if not v_ or len(v.solo_digitos(v_.group())) < 3:
                break
            valor = v_.group().rstrip("-/")
            yield Hallazgo(FOLIO, valor, v_.start(), v_.start() + len(valor))
            sig = _SIGUIENTE_FOLIO.match(texto, v_.end())
            if not sig:
                break
            pos = sig.end()
    for m in _RE_REGISTRO_PATRONAL.finditer(texto):
        yield Hallazgo(FOLIO, m.group(), m.start(), m.end())


_RE_WEB = re.compile(
    r"(?<![@\w.\-])(?:https?://|www\.)[A-Za-z0-9\-]+(?:\.[A-Za-z0-9\-]+)+(?:/[^\s<>\"')\]]*)?", _I
)
_WEB_PUBLICA = re.compile(r"\.(?:gob|gov|edu)(?:\.[a-z]{2})?$", _I)
# Dominio suelto, sin www: solo en minúsculas y con terminación conocida.
_RE_DOMINIO = re.compile(
    r"(?<![@\w.\-/])[a-z0-9][a-z0-9\-]*(?:\.[a-z0-9\-]+)*\.(?:com|net|org|io|mx)(?:\.mx)?(?![\w\-])"
)


def _web(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_DOMINIO.finditer(texto):
        if not _WEB_PUBLICA.search(m.group()):
            yield Hallazgo(WEB, m.group(), m.start(), m.end())
    for m in _RE_WEB.finditer(texto):
        valor = m.group().rstrip(".,;:")
        anfitrion = re.sub(r"^(?:https?://)?", "", valor, flags=_I).split("/")[0]
        if not _WEB_PUBLICA.search(anfitrion):
            yield Hallazgo(WEB, valor, m.start(), m.start() + len(valor))


_RE_PLACA = re.compile(
    r"\bplacas?(?:\s+de\s+circulaci[oó]n)?(?:\s+(?:n[uú]mero|no\.))?\s*:?\s*"
    r"([A-Z0-9]{2,4}[ \-]?[A-Z0-9]{2,4}(?:[ \-]?[A-Z0-9]{1,3})?)(?![A-Z0-9])",
    _I,
)


def _placa(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_PLACA.finditer(texto):
        valor = m.group(1)
        if re.search(r"\d", valor) and re.search(r"[A-Za-z]", valor):
            yield Hallazgo(PLACA, valor, m.start(1), m.end(1))


_MESES = r"(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|setiembre|octubre|noviembre|diciembre)"
_MES_CORTO = r"(?:ene|feb|mar|abr|may|jun|jul|ago|sept?|set|oct|nov|dic)(?:\.(?=[\-/ ]?\d))?"  # el punto solo si sigue el año
_RE_FECHA = re.compile(
    r"\b(?:\d{1,2}|primero|1[oº°])\s+de\s+" + _MESES + r"(?:\s+del?\s+(?:a[ñn]o\s+)?\d{4})?\b"
    r"|\b" + _MESES + r"\s+(?:de\s+|del\s+)?\d{4}\b"
    # Abreviadas, como se escriben en notas y correos: 8-sep-2026, 15-sep, ene-2022, 4 mar 2019.
    r"|(?<![\w-])\d{1,2}[\-/ ]" + _MES_CORTO + r"(?:[\-/ .]\d{4}|[\-/]\d{2})?(?![\w-])"
    r"|(?<![\w-])" + _MES_CORTO + r"[\-/ ]\d{4}(?![\w-])"
    r"|(?<![\d/])\d{1,2}[/\-.]\d{1,2}[/\-.](?:\d{4}|\d{2})(?![\d/])"
    r"|\b\d{4}-\d{2}-\d{2}\b",
    _I,
)


def _fecha(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_FECHA.finditer(texto):
        yield Hallazgo(FECHA, m.group(), m.start(), m.end())


_RE_MONTO = re.compile(
    r"(?:US)?\$\s?\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?(?:\s?(?:M\.?\s?N\.?|MXN|USD))?"
    r"|\b\d{1,3}(?:,\d{3})*(?:\.\d{1,2})?\s(?:pesos|MXN|USD|d[oó]lares)\b"
    r"|\([^()]{3,120}?\s(?:pesos|d[oó]lares)\s\d{2}/100(?:\s?(?:M\.?\s?N\.?|USD|moneda\s+nacional))?\s?\)",
    _I,
)


def _monto(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_MONTO.finditer(texto):
        yield Hallazgo(MONTO, m.group(), m.start(), m.end())


_VIALIDAD = (
    r"(?:calle|avenida|av\.|avda\.|calzada|calz\.|boulevard|bulevar|blvd\.|privada|priv\."
    r"|andador|carretera|camino|prolongaci[oó]n|cerrada|circuito|retorno|paseo)"
)
_RE_DOMICILIO_INICIO = re.compile(
    r"\bdomicilio(?:\s+(?:particular|fiscal|procesal|legal|convencional|social|conyugal|laboral))?"
    r"(?:\s+(?:ubicado\s+en|ubicado|sito\s+en|el\s+ubicado\s+en|en|"
    r"para\s+o[ií]r\s+y\s+recibir\s+notificaciones\s+(?:el\s+ubicado\s+)?en))?\s*:?\s*"
    r"|\b(?=" + _VIALIDAD + r"\s)",
    _I,
)
_RE_CP = re.compile(r"(?:C\.\s?P\.|c[oó]digo\s+postal)\s*:?\s*\d{5}", _I)
_NO_ES_DIRECCION = re.compile(
    r"(?:y|e|o|u|que|como|del|de\s+(?:la|las|los|mi|su|sus)|a\s+(?:la|que)|para\s+(?!o[ií]r)|se[ñn]alad[oa]s?|"
    r"indicad[oa]s?|mencionad[oa]s?|referid[oa]s?|antes|ya|no|es|son|fue|ser[áa]?|conocid[oa])\b"
)
_RE_FIN_FRASE = re.compile(r"[;\n]|\.(?=\s+[A-ZÁÉÍÓÚÑ])|\.$")


# "Avenida de los Insurgentes", "calle 5", "Prolongación Reforma"; no "prolongación diaria".
_RE_VIA_CON_NOMBRE = re.compile(
    r"(?i:" + _VIALIDAD + r")\s+(?:(?i:de\s+las|de\s+los|de\s+la|del|de)\s+)?(?:[A-ZÁÉÍÓÚÑ0-9]|(?i:n[oú]m?\.?\s*\d))"
)


def _domicilio(texto: str) -> Iterator[Hallazgo]:
    for m in _RE_DOMICILIO_INICIO.finditer(texto):
        if not m.group() and not _RE_VIA_CON_NOMBRE.match(texto, m.start()):
            continue  # vialidad sin nombre propio: es una palabra común
        ini = m.end()
        # "Domicilio para emplazar\nAv. …": si antes del salto de línea solo hay un rótulo
        # corto sin números, el domicilio empieza en la línea siguiente (otra celda de la tabla).
        salto = texto.find("\n", ini, ini + 60)
        if salto != -1 and not re.search(r"\d", texto[ini:salto]) and len(texto[ini:salto].split()) <= 5:
            ini = salto + 1
        if ini >= len(texto) or not texto[ini].strip():
            continue
        if _NO_ES_DIRECCION.match(texto, ini):
            continue  # "el domicilio procesal y el correo indicados…": se habla de él, no lo da
        ventana = texto[ini:ini + 250]
        cp = _RE_CP.search(ventana)
        if cp:
            fin = ini + cp.end()
        else:
            corte = _RE_FIN_FRASE.search(ventana[:150])
            fin = ini + (corte.start() if corte else min(len(ventana), 150))
        valor = texto[ini:fin].rstrip(" ,")
        # Debe parecer domicilio: una vialidad o un número.
        if len(valor) >= 8 and re.search(r"\d", valor):
            yield Hallazgo(DOMICILIO, valor, ini, ini + len(valor))


DETECTORES: tuple[Callable[[str], Iterable[Hallazgo]], ...] = (
    _curp, _ine, _rfc, _numeros, _cuenta, _correo, _telefono, _expediente, _folio,
    _web, _placa, _fecha, _monto, _domicilio,
)


# --- API ----------------------------------------------------------------------


def candidatos(texto: str) -> list[Hallazgo]:
    """Todos los hallazgos por patrón, con traslapes (los resuelve `detector.detectar`)."""
    return [h for det in DETECTORES for h in det(texto)]
