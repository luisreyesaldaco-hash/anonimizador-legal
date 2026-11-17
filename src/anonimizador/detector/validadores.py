"""Validadores de dígito verificador y estructura para identificadores mexicanos.

Cada función recibe el valor ya normalizado (mayúsculas, sin espacios ni guiones)
y devuelve True si el identificador es estructural y aritméticamente válido.
"""

from __future__ import annotations

import datetime
import re

# --- utilidades ---------------------------------------------------------------


def solo_digitos(valor: str) -> str:
    return re.sub(r"\D", "", valor)


def fecha_yymmdd_valida(yymmdd: str) -> bool:
    if len(yymmdd) != 6 or not yymmdd.isdigit():
        return False
    yy, mes, dia = int(yymmdd[:2]), int(yymmdd[2:4]), int(yymmdd[4:6])
    for siglo in (1900, 2000):  # el siglo es ambiguo; basta con que uno exista
        try:
            datetime.date(siglo + yy, mes, dia)
            return True
        except ValueError:
            pass
    return False


def luhn_valido(digitos: str) -> bool:
    if not digitos.isdigit() or len(digitos) < 2:
        return False
    total = 0
    for i, c in enumerate(reversed(digitos)):
        d = int(c)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


# --- CURP ---------------------------------------------------------------------

_CURP_DICC = "0123456789ABCDEFGHIJKLMNÑOPQRSTUVWXYZ"
_ENTIDADES = {
    "AS", "BC", "BS", "CC", "CL", "CM", "CS", "CH", "DF", "DG", "GT", "GR", "HG",
    "JC", "MC", "MN", "MS", "NT", "NL", "OC", "PL", "QT", "QR", "SP", "SL", "SR",
    "TC", "TS", "TL", "VZ", "YN", "ZS", "NE",
}


def curp_digito(curp17: str) -> str:
    suma = sum(_CURP_DICC.index(c) * (18 - i) for i, c in enumerate(curp17))
    return str((10 - suma % 10) % 10)


def curp_valida(curp: str) -> bool:
    if len(curp) != 18:
        return False
    if not fecha_yymmdd_valida(curp[4:10]) or curp[10] not in "HMX":
        return False
    if curp[11:13] not in _ENTIDADES:
        return False
    if any(c not in _CURP_DICC for c in curp[:17]):
        return False
    return curp_digito(curp[:17]) == curp[17]


# --- RFC ----------------------------------------------------------------------

_RFC_DICC = "0123456789ABCDEFGHIJKLMN&OPQRSTUVWXYZ Ñ"


def rfc_digito(rfc_sin_dv: str) -> str:
    """Dígito verificador SAT; acepta 11 (moral) o 12 (física) caracteres."""
    base = rfc_sin_dv.rjust(12)  # moral: se antepone un espacio
    suma = sum(_RFC_DICC.index(c) * (13 - i) for i, c in enumerate(base))
    r = 11 - suma % 11
    if r == 11:
        return "0"
    if r == 10:
        return "A"
    return str(r)


def rfc_estructura_valida(rfc: str) -> bool:
    if len(rfc) == 13:
        letras, fecha = rfc[:4], rfc[4:10]
    elif len(rfc) == 12:
        letras, fecha = rfc[:3], rfc[3:9]
    else:
        return False
    if not all(c.isalpha() or c == "&" for c in letras) or not fecha_yymmdd_valida(fecha):
        return False
    # Homoclave del SAT: 2 caracteres de homonimia + dígito verificador.
    return re.fullmatch(r"[1-9A-V][1-9A-Z][0-9A]", rfc[-3:]) is not None


def rfc_valido(rfc: str) -> bool:
    if not rfc_estructura_valida(rfc):
        return False
    if any(c not in _RFC_DICC for c in rfc):
        return False
    return rfc_digito(rfc[:-1]) == rfc[-1]


# --- CLABE --------------------------------------------------------------------

_CLABE_PESOS = (3, 7, 1)


def clabe_valida(clabe: str) -> bool:
    if len(clabe) != 18 or not clabe.isdigit():
        return False
    suma = sum((int(d) * _CLABE_PESOS[i % 3]) % 10 for i, d in enumerate(clabe[:17]))
    return (10 - suma % 10) % 10 == int(clabe[17])


# --- NSS (IMSS) ---------------------------------------------------------------


def nss_valido(nss: str) -> bool:
    return len(nss) == 11 and luhn_valido(nss)


# --- Tarjeta ------------------------------------------------------------------


def tarjeta_valida(numero: str) -> bool:
    return 13 <= len(numero) <= 19 and luhn_valido(numero)
