"""Verificación de la salida: vuelve a abrir el archivo generado y busca cualquier valor
original marcado, en cualquier lugar del paquete (texto, atributos, relaciones).

La verificación no confía en el procesador que generó el archivo: lee el resultado
desde cero. Si encuentra algo, el archivo no debe darse por bueno.
"""

from __future__ import annotations

import bisect
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from lxml import etree

from .seudonimos import Entidad, localizar
from .textos import tr

_W_P = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"
_W_T = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t"
_EXT_INCRUSTADOS = (".xlsx", ".xlsm", ".docx", ".pptx", ".bin", ".xls", ".doc", ".ppt")
_EXT_IMAGEN = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".emf", ".wmf")


@dataclass(frozen=True)
class Fuga:
    ubicacion: str  # parte del paquete o página
    etiqueta: str  # entidad cuyo valor original apareció
    fragmento: str  # contexto donde apareció


@dataclass
class ResultadoVerificacion:
    fugas: list[Fuga]
    avisos: list[str]

    @property
    def limpio(self) -> bool:
        return not self.fugas


_SEPARADOR = "\x00"  # ni espacio ni letra: ningún valor puede quedar "unido" entre dos cadenas


def buscar_en_cadenas(ubicacion: str, cadenas: Iterable[str], entidades: list[Entidad]) -> list[Fuga]:
    """Busca todas las cadenas de una vez (unidas por un separador) y recorta cada fragmento
    a la cadena donde apareció."""
    cadenas = [c.replace(_SEPARADOR, " ") for c in cadenas if c and c.strip()]
    if not cadenas:
        return []
    inicios, pos = [], 0
    for c in cadenas:
        inicios.append(pos)
        pos += len(c) + 1
    todo = _SEPARADOR.join(cadenas)
    fugas = []
    for a in localizar(todo, entidades):
        i = bisect.bisect_right(inicios, a.inicio) - 1
        base, s = inicios[i], cadenas[i]
        ini, fin = max(0, a.inicio - base - 30), min(len(s), a.fin - base + 30)
        fugas.append(Fuga(ubicacion, a.etiqueta, s[ini:fin].replace("\n", " ")))
    return fugas


def _cadenas_xml(datos: bytes) -> list[str]:
    try:
        raiz = etree.fromstring(datos, etree.XMLParser(recover=True, huge_tree=True))
    except etree.XMLSyntaxError:
        return [datos.decode("utf-8", "replace")]
    if raiz is None:
        return [datos.decode("utf-8", "replace")]
    cadenas: list[str] = []
    for el in raiz.iter():
        t = etree._Element.text.__get__(el)
        if t:
            cadenas.append(t)
        if el.tail:
            cadenas.append(el.tail)
        if isinstance(el.tag, str):
            cadenas.extend(el.attrib.values())
    # Párrafos de Word completos: un nombre partido en runs solo se ve al unirlos.
    for p in raiz.iter(_W_P):
        cadenas.append("".join(etree._Element.text.__get__(t) or "" for t in p.iter(_W_T)))
    return cadenas


def verificar_paquete(ruta: str | Path, entidades: Iterable[Entidad]) -> ResultadoVerificacion:
    """Para formatos Office (zip + XML): .docx y similares."""
    fugas: list[Fuga] = []
    avisos: list[str] = []
    with zipfile.ZipFile(ruta) as z:
        for nombre in z.namelist():
            bajo = nombre.lower()
            if bajo.endswith((".xml", ".rels", ".vml")):
                fugas += buscar_en_cadenas(nombre, _cadenas_xml(z.read(nombre)), entidades)
            elif "thumbnail" in bajo:
                fugas.append(Fuga(nombre, "-", tr('miniatura de la primera página')))
            elif bajo.endswith(_EXT_INCRUSTADOS):
                avisos.append(tr('{nombre}: objeto incrustado que no se puede verificar automáticamente.', nombre=nombre))
            elif bajo.endswith(_EXT_IMAGEN):
                pass  # las imágenes se avisan una sola vez abajo
        if any(n.lower().endswith(_EXT_IMAGEN) for n in z.namelist()):
            avisos.append(tr('El documento contiene imágenes; revisa que no muestren datos (firmas, credenciales, sellos).'))
    return ResultadoVerificacion(fugas, avisos)
