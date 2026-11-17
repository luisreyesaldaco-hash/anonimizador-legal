"""Modelo de datos del detector: hallazgos, tipos y prioridades."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Hallazgo:
    tipo: str
    valor: str  # el texto tal como aparece en el documento
    inicio: int
    fin: int
    verificado: bool = False  # True si pasó un dígito verificador / checksum


CURP = "CURP"
INE = "CLAVE_ELECTOR"
CLABE = "CLABE"
TARJETA = "TARJETA"
RFC = "RFC"
NSS = "NSS"
CORREO = "CORREO"
EXPEDIENTE = "EXPEDIENTE"
CUENTA = "CUENTA"
PLACA = "PLACA"
TELEFONO = "TELEFONO"
DOMICILIO = "DOMICILIO"
EMPRESA = "EMPRESA"
NOMBRE = "NOMBRE"
FECHA = "FECHA"
MONTO = "MONTO"
FOLIO = "FOLIO"  # no. de empleado, registro patronal, cédula profesional, folios internos
WEB = "WEB"  # sitios web privados (los de gobierno no)
# Checo
RODNE_CISLO = "RODNE_CISLO"  # número de nacimiento: fecha + dígito de control (divisible entre 11)
ICO = "ICO"  # identificación de empresa o persona que factura (8 dígitos con control)
DIC = "DIC"  # número fiscal (CZ + IČO o rodné číslo)
# Inglés
SSN = "SSN"  # Social Security Number de EE. UU. (AAA-GG-SSSS)
NINO = "NINO"  # National Insurance number del Reino Unido (AB 12 34 56 C)

# DIČ (CZ + rodné číslo) va antes que el rodné číslo: gana el completo.
# Ante un traslape gana la mayor prioridad (y, a igual prioridad, el más largo).
# DOMICILIO gana a NOMBRE para que una calle con nombre de persona no deje el
# domicilio a medias; EMPRESA gana a NOMBRE porque la incluye con su sufijo.
PRIORIDAD = {
    CURP: 100, DIC: 99, RODNE_CISLO: 98, SSN: 97, NINO: 96, INE: 95, ICO: 82, CLABE: 90, TARJETA: 85, RFC: 80, NSS: 75, CORREO: 70,
    EXPEDIENTE: 65, FOLIO: 62, CUENTA: 60, WEB: 58, PLACA: 55, TELEFONO: 50, DOMICILIO: 40,
    EMPRESA: 39, NOMBRE: 38, FECHA: 30, MONTO: 30,
}

TIPOS = tuple(PRIORIDAD)

# Tipos que se sugieren pero llegan desmarcados a la revisión (SPEC §4).
DESMARCADOS_POR_DEFECTO = frozenset({EMPRESA})
