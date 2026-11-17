"""Procesador de Word (.docx).

Trabaja sobre el XML del paquete, no sobre la API de párrafos de python-docx, porque
esa API no ve el texto dentro de hipervínculos, cambios controlados, cuadros de texto,
notas al pie ni campos.

Pasos al abrir:
1. Acepta todos los cambios controlados (el texto borrado desaparece del archivo).
2. Elimina los comentarios.
3. Extrae el texto de cuerpo, encabezados, pies, notas al pie/final y cuadros de texto
   como una sola cadena, recordando de qué nodo <w:t> salió cada carácter.

Al guardar:
4. Sustituye cada aparición por su etiqueta aunque esté partida en varios *runs*; el
   reemplazo hereda el formato del primer fragmento.
5. Barre el resto del paquete (códigos de campo, textos alternativos, XML personalizado,
   gráficos) y limpia metadatos, autores, plantilla y variables del documento.
"""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from pathlib import Path

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree

from ..seudonimos import Entidad, aplicar, localizar
from ..verificacion import ResultadoVerificacion, verificar_paquete
from ..textos import tr

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
XML_NS = "http://www.w3.org/XML/1998/namespace"
MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"
CT_WORD = "application/vnd.openxmlformats-officedocument.wordprocessingml."


# python-docx redefine `.text` en sus clases XML (CT_P.text es de solo lectura y devuelve
# el texto del párrafo). Aquí siempre se usa el texto crudo del nodo lxml.
_get = etree._Element.text.__get__
_set = etree._Element.text.__set__


def _texto(el) -> str | None:
    return _get(el)


def _pon_texto(el, valor: str) -> None:
    _set(el, valor)


def _w(tag: str) -> str:
    return f"{{{W}}}{tag}"


# Partes cuyo texto se extrae para detección, en este orden.
_PARTES_CON_TEXTO = ("document.main", "header", "footer", "footnotes", "endnotes")

_ELIMINAR = [
    "del", "moveFrom", "rPrChange", "pPrChange", "sectPrChange", "tblPrChange", "trPrChange",
    "tcPrChange", "tblGridChange", "numberingChange", "moveFromRangeStart", "moveFromRangeEnd",
    "moveToRangeStart", "moveToRangeEnd", "customXmlDelRangeStart", "customXmlDelRangeEnd",
    "customXmlMoveFromRangeStart", "customXmlMoveFromRangeEnd", "customXmlMoveToRangeStart",
    "customXmlMoveToRangeEnd", "customXmlInsRangeStart", "customXmlInsRangeEnd",
    "commentRangeStart", "commentRangeEnd", "proofErr",
]
_DESENVOLVER = ["ins", "moveTo"]

_REL_COMENTARIOS = ("/comments", "/commentsExtended", "/commentsIds", "/commentsExtensible", "/people")
_REL_FUERA = ("/glossaryDocument",) + _REL_COMENTARIOS

# Atributos que pueden llevar texto del usuario.
_ATRIBUTOS_TEXTO = {"descr", "title", "instr", "alias", "tag", "name"}
_ATRIBUTOS_AUTOR = {"author", "initials"}


class DocumentoNoSoportado(Exception):
    pass


@dataclass
class _Pieza:
    inicio: int
    fin: int
    nodo: etree._Element | None  # <w:t> editable; None = carácter fijo (tab, salto, separador)


@dataclass
class Informe:
    salida: Path
    apariciones: int
    verificacion: ResultadoVerificacion
    avisos: list[str] = field(default_factory=list)

    @property
    def limpio(self) -> bool:
        return self.verificacion.limpio


class DocumentoWord:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        try:
            self._doc = docx.Document(str(self.ruta))
        except Exception as e:  # python-docx lanza varios tipos según el daño
            raise DocumentoNoSoportado(tr('No pude abrir {ruta} como documento de Word: {e}', ruta=self.ruta.name, e=e)) from e
        self.avisos: list[str] = []
        self._raices: list[tuple[object, etree._Element]] = []  # (parte, raíz XML)
        self._cargar_partes()
        comentarios = cambios = 0
        for _, raiz in self._raices:
            cambios += _aceptar_cambios(raiz)
            comentarios += _quitar_comentarios(raiz)
        # Se quitan porque pueden traer datos (y el nombre de quien los escribió); el
        # original no se toca. Se avisa para que nadie se sorprenda al abrir la copia.
        if comentarios:
            self.avisos.append(tr('Se quitaron {n} comentario(s) del Word: pueden traer datos y el nombre de quien '
                                  'los escribió. El original los conserva.', n=comentarios))
        if cambios:
            self.avisos.append(tr('Se aceptaron los cambios controlados del Word: el texto borrado podía traer '
                                  'datos. El original los conserva.'))
        self._quitar_relaciones_fuera()
        self.texto, self._piezas, self._duplicados = self._extraer()

    # --- carga ---------------------------------------------------------------

    def _partes(self):
        return list(self._doc.part.package.iter_parts())

    def _cargar_partes(self) -> None:
        for parte in self._partes():
            ct = parte.content_type
            if not ct.endswith("+xml") and not ct.endswith("/xml"):
                if "oleObject" in ct or "package" in ct or "embeddings" in str(parte.partname):
                    self.avisos.append(
                        tr('El documento contiene un objeto incrustado ({partname}) que no se revisa. Ábrelo y revísalo a mano, o elimínalo antes de compartir.', partname=parte.partname)
                    )
                continue
            raiz = _raiz(parte)
            if raiz is not None:
                self._raices.append((parte, raiz))

    def _quitar_relaciones_fuera(self) -> None:
        for parte in self._partes():
            for rid, rel in list(parte.rels.items()):
                if rel.reltype.endswith(_REL_FUERA):
                    del parte.rels[rid]
        # Propiedades personalizadas (docProps/custom.xml): se quitan completas.
        paquete = self._doc.part.package
        for rid, rel in list(paquete.rels.items()):
            # custom-properties: campos personalizados; thumbnail: imagen de la 1.ª página.
            if rel.reltype.endswith(("/custom-properties", "/thumbnail")):
                del paquete.rels[rid]
        self._raices = [(p, r) for p, r in self._raices if p in set(self._partes())]

    # --- extracción ----------------------------------------------------------

    def _raices_con_texto(self):
        orden = {k: i for i, k in enumerate(_PARTES_CON_TEXTO)}
        con_texto = []
        for parte, raiz in self._raices:
            ct = parte.content_type
            if ct.startswith(CT_WORD):
                tipo = ct[len(CT_WORD):].removesuffix("+xml")
                if tipo in orden:
                    con_texto.append((orden[tipo], str(parte.partname), raiz))
        return [r for *_, r in sorted(con_texto, key=lambda x: (x[0], x[1]))]

    def _extraer(self) -> tuple[str, list[_Pieza], list[tuple[int, int]]]:
        """Texto + piezas. Los párrafos dentro de mc:Fallback (copia de un cuadro de texto
        para Word antiguo) se extraen para limpiarlos, pero se marcan como duplicados."""
        partes: list[str] = []
        piezas: list[_Pieza] = []
        duplicados: list[tuple[int, int]] = []
        pos = 0

        def agrega(texto: str, nodo):
            nonlocal pos
            if texto:
                partes.append(texto)
                piezas.append(_Pieza(pos, pos + len(texto), nodo))
                pos += len(texto)

        for raiz in self._raices_con_texto():
            for p in raiz.iter(_w("p")):
                inicio_p = pos
                for el in p.iter():
                    if el is p or _parrafo_de(el) is not p:
                        continue
                    tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
                    if tag == "t" and _texto(el):
                        agrega(_texto(el), el)
                    elif tag == "tab" and el.getparent() is not None and etree.QName(el.getparent()).localname == "r":
                        agrega("\t", None)
                    elif tag in ("br", "cr"):
                        agrega("\n", None)
                    elif tag == "noBreakHyphen":
                        agrega("-", None)
                agrega("\n", None)  # fin de párrafo
                if any(a.tag == MC_FALLBACK for a in p.iterancestors()):
                    duplicados.append((inicio_p, pos))
        return "".join(partes), piezas, duplicados

    # --- guardado ------------------------------------------------------------

    def guardar(self, salida: str | Path, entidades: list[Entidad]) -> Informe:
        salida = Path(salida)
        if salida.resolve() == self.ruta.resolve():
            raise ValueError(tr('La salida no puede ser el archivo original; elige otro nombre.'))
        marcadas = [e for e in entidades if e.marcada]
        apariciones = localizar(self.texto, entidades)  # las desmarcadas reservan su lugar
        self._sustituir(apariciones, {e.etiqueta: e.marcador for e in marcadas})
        for _, raiz in self._raices:
            _barrer(raiz, entidades)
        self._limpiar_hipervinculos(entidades)
        self._limpiar_metadatos()
        for parte, raiz in self._raices:
            _guardar_raiz(parte, raiz)
        self._doc.save(str(salida))
        verificacion = verificar_paquete(salida, entidades)
        return Informe(salida, len(apariciones), verificacion, self.avisos + verificacion.avisos)

    def texto_limpio(self, entidades: list[Entidad]) -> str:
        marcadas = [e for e in entidades if e.marcada]
        texto, pos = [], 0
        for ini, fin in self._duplicados:
            texto.append(self.texto[pos:ini])
            pos = fin
        texto.append(self.texto[pos:])
        unico = "".join(texto)
        return aplicar(unico, localizar(unico, entidades), marcadas)

    def _sustituir(self, apariciones, marcadores: dict[str, str]) -> None:
        inicios = [p.inicio for p in self._piezas]
        textos = {id(p.nodo): _texto(p.nodo) for p in self._piezas if p.nodo is not None}
        for a in sorted(apariciones, key=lambda a: a.inicio, reverse=True):
            i = bisect.bisect_right(inicios, a.inicio) - 1
            j = bisect.bisect_left(inicios, a.fin)
            tocadas = [p for p in self._piezas[max(i, 0):j] if p.fin > a.inicio and p.inicio < a.fin]
            editables = [p for p in tocadas if p.nodo is not None]
            if not editables:
                continue
            primera = editables[0]
            for p in reversed(editables):
                t = textos[id(p.nodo)]
                li, lf = max(a.inicio, p.inicio) - p.inicio, min(a.fin, p.fin) - p.inicio
                insertar = marcadores[a.etiqueta] if p is primera else ""
                textos[id(p.nodo)] = t[:li] + insertar + t[lf:]
        for p in self._piezas:
            if p.nodo is not None and textos[id(p.nodo)] != _texto(p.nodo):
                _pon_texto(p.nodo, textos[id(p.nodo)])
                p.nodo.set(f"{{{XML_NS}}}space", "preserve")

    def _limpiar_hipervinculos(self, entidades: list[Entidad]) -> None:
        """Un hipervínculo 'mailto:juan@…' conserva el dato aunque el texto visible cambie."""
        for parte in self._partes():
            for rid, rel in list(parte.rels.items()):
                if rel.reltype != RT.HYPERLINK or not rel.is_external:
                    continue
                if localizar(rel.target_ref, entidades):
                    raiz = next((r for p, r in self._raices if p is parte), None)
                    if raiz is not None:
                        for h in raiz.iter(_w("hyperlink")):
                            if h.get(f"{{{_R}}}id") == rid:
                                _desenvolver(h)
                    del parte.rels[rid]

    def _limpiar_metadatos(self) -> None:
        cp = self._doc.core_properties
        for campo in ("author", "last_modified_by", "title", "subject", "keywords", "comments",
                      "category", "identifier", "content_status", "version", "language"):
            setattr(cp, campo, "")
        for parte, raiz in self._raices:
            nombre = str(parte.partname)
            if nombre == "/docProps/app.xml":
                for el in list(raiz):
                    if etree.QName(el).localname in ("Company", "Manager", "HyperlinkBase", "Template"):
                        _pon_texto(el, "")
            if parte.content_type == CT_WORD + "settings+xml":
                for tag in ("attachedTemplate", "trackRevisions", "docVars", "rsids"):
                    for el in list(raiz.iter(_w(tag))):
                        el.getparent().remove(el)


_R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


# --- utilidades XML -------------------------------------------------------------


def _raiz(parte) -> etree._Element | None:
    elemento = getattr(parte, "_element", None)
    if elemento is not None:
        return elemento
    try:
        return etree.fromstring(parte.blob)
    except (etree.XMLSyntaxError, ValueError):
        return None


def _guardar_raiz(parte, raiz) -> None:
    if getattr(parte, "_element", None) is None and hasattr(parte, "_blob"):
        parte._blob = etree.tostring(raiz, xml_declaration=True, encoding="UTF-8", standalone=True)


def _parrafo_de(el) -> etree._Element | None:
    p = el.getparent()
    while p is not None and p.tag != _w("p"):
        p = p.getparent()
    return p


def _desenvolver(el) -> None:
    padre = el.getparent()
    if padre is None:
        return
    i = padre.index(el)
    for hijo in list(el):
        padre.insert(i, hijo)
        i += 1
    padre.remove(el)


def _aceptar_cambios(raiz) -> int:
    """Acepta los cambios controlados; devuelve cuántas marcas de cambio había."""
    marcas = sum(1 for _ in raiz.iter(_w("ins"), _w("del"), _w("moveFrom"), _w("moveTo")))
    # Filas de tabla eliminadas con control de cambios.
    for tr in list(raiz.iter(_w("tr"))):
        trpr = tr.find(_w("trPr"))
        if trpr is not None and trpr.find(_w("del")) is not None:
            tr.getparent().remove(tr)
    for tag in _ELIMINAR:
        for el in list(raiz.iter(_w(tag))):
            if el.getparent() is not None:
                el.getparent().remove(el)
    for tag in _DESENVOLVER:
        for el in list(raiz.iter(_w(tag))):
            _desenvolver(el)
    for el in list(raiz.iter(_w("delText"), _w("delInstrText"))):
        el.getparent().remove(el)
    return marcas


def _quitar_comentarios(raiz) -> int:
    refs = list(raiz.iter(_w("commentReference")))
    for ref in refs:
        run = ref.getparent()
        if run is not None and run.tag == _w("r") and run.getparent() is not None:
            run.getparent().remove(run)
        elif run is not None:
            run.remove(ref)
    return len(refs)


def _sustituye(cadena: str, entidades: list[Entidad]) -> str:
    aps = localizar(cadena, entidades)
    return aplicar(cadena, aps, entidades) if aps else cadena


def _barrer(raiz, entidades: list[Entidad]) -> None:
    """Sustituye en cualquier texto o atributo que haya quedado (campos, alt text, XML personalizado)."""
    for el in raiz.iter():
        t = _texto(el)
        if t and t.strip():
            _pon_texto(el, _sustituye(t, entidades))
        if el.tail and el.tail.strip():
            el.tail = _sustituye(el.tail, entidades)
        if not isinstance(el.tag, str):
            continue
        for nombre, valor in list(el.attrib.items()):
            local = etree.QName(nombre).localname
            if local in _ATRIBUTOS_AUTOR:
                el.set(nombre, "")
            elif local in _ATRIBUTOS_TEXTO and valor:
                el.set(nombre, _sustituye(valor, entidades))
