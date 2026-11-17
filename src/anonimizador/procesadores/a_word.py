"""Salida en Word (.docx) para lo que no entró como Word: PDF, imagen escaneada o texto.

Se escribe el texto ya seudonimizado (las sustituciones se hacen sobre el texto original,
con las mismas apariciones que el PDF), un párrafo por bloque, con salto de página donde
cambiaba la página. Se pierde el diseño exacto (sellos, columnas, tablas dibujadas); a
cambio el resultado se puede editar. Al final se verifica el .docx como cualquier Word.
"""

from __future__ import annotations

import re
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from ..seudonimos import Entidad, aplicar, localizar
from ..verificacion import verificar_paquete

FUENTE = "Arial"


def _documento_vacio():
    documento = docx.Document()
    normal = documento.styles["Normal"]
    normal.font.name, normal.font.size = FUENTE, Pt(11)
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FUENTE)
    normal.paragraph_format.space_after = Pt(6)
    cp = documento.core_properties  # que el documento no diga "python-docx" ni nada del original
    cp.author = cp.last_modified_by = cp.title = cp.subject = cp.keywords = cp.comments = ""
    quitar_miniatura(documento)
    return documento


def quitar_miniatura(documento) -> None:
    """La plantilla de python-docx trae una miniatura (docProps/thumbnail.jpeg) que no es del
    documento: confunde a la verificación y a quien lo abra."""
    paquete = documento.part.package
    for rid, rel in list(paquete.rels.items()):
        if rel.reltype.endswith("/thumbnail"):
            del paquete.rels[rid]


def _bloques(texto: str) -> list[str]:
    """Los procesadores separan bloques con una línea en blanco; dentro de un bloque, cada
    renglón del PDF se une al siguiente (con guion de corte: se junta la palabra)."""
    bloques = []
    for bloque in re.split(r"\n\s*\n", texto):
        lineas = [l.strip() for l in bloque.split("\n") if l.strip()]
        if not lineas:
            continue
        unido = lineas[0]
        for l in lineas[1:]:
            if unido.endswith("-") and l[:1].islower():
                unido = unido[:-1] + l
            else:
                unido += " " + l
        bloques.append(re.sub(r"[ \t]+", " ", unido))
    return bloques


def _corrido(cortes: list[int], apariciones, marcadores: dict[str, str]) -> list[int]:
    """Dónde quedan los inicios de página en el texto ya sustituido."""
    nuevos = []
    for corte in cortes:
        delta = 0
        for a in apariciones:
            if a.fin <= corte:
                delta += len(marcadores[a.etiqueta]) - (a.fin - a.inicio)
            elif a.inicio < corte:  # la página empieza dentro de un dato: va después de su etiqueta
                delta += len(marcadores[a.etiqueta]) - (corte - a.inicio)
        nuevos.append(corte + delta)
    return nuevos


def guardar_como_word(texto: str, entidades: list[Entidad], salida: str | Path,
                      cortes_pagina: list[int] | None = None):
    """Escribe `texto` seudonimizado en `salida` (.docx). Devuelve (apariciones, verificación)."""
    salida = Path(salida)
    marcadas = [e for e in entidades if e.marcada]
    apariciones = localizar(texto, entidades)  # las desmarcadas reservan su lugar
    marcadores = {e.etiqueta: e.marcador for e in marcadas}
    limpio = aplicar(texto, apariciones, marcadas)
    cortes = _corrido(sorted(cortes_pagina or []), sorted(apariciones, key=lambda a: a.inicio), marcadores)
    paginas = [limpio[i:j] for i, j in zip([0] + cortes, cortes + [len(limpio)])]

    documento = _documento_vacio()
    primero = True
    for pagina in paginas:
        for k, b in enumerate(_bloques(pagina)):
            p = documento.add_paragraph(b)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if k == 0 and not primero:
                p.paragraph_format.page_break_before = True
            primero = False
    documento.save(str(salida))
    return apariciones, verificar_paquete(salida, entidades)
