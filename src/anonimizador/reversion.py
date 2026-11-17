"""La respuesta de la IA, de vuelta con los datos reales y lista para Word.

- Texto (lo que se pega del chat, casi siempre Markdown) → .docx con títulos, negritas,
  listas y tablas de verdad, en vez de asteriscos sueltos.
- Un .docx que entregó la IA → el mismo .docx revertido, conservando su formato. Word
  parte a veces una etiqueta en varios *runs* ("[PERSONA_" + "1]"): el valor real se
  escribe en el primero, con su formato, y los demás se vacían.
- Texto para copiar: sin las marcas de Markdown, para pegarlo en un correo.
"""

from __future__ import annotations

import re
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path

import docx
from lxml import etree
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from .procesadores.a_word import quitar_miniatura
from .procesadores.docx import CT_WORD, XML_NS, _guardar_raiz, _parrafo_de, _pon_texto, _raiz, _texto, _w
from .seudonimos import etiquetas_desconocidas, reemplazos, revertir
from .textos import tr

FUENTE = "Arial"
_PARTES = ("document.main", "header", "footer", "footnotes", "endnotes")


@dataclass
class Reversion:
    texto: str  # texto revertido (de un .docx: el de sus párrafos)
    reemplazos: int
    desconocidas: list[str]  # etiquetas que la tabla no conoce: quedan tal cual


# --- revertir un documento de Word ---------------------------------------------------


def _raices(documento) -> list[tuple[object, object]]:
    raices = []
    for parte in documento.part.package.iter_parts():
        ct = parte.content_type
        if ct.startswith(CT_WORD) and ct[len(CT_WORD):].removesuffix("+xml") in _PARTES:
            raiz = _raiz(parte)
            if raiz is not None:
                raices.append((parte, raiz))
    return raices


def _revertir_documento(documento, tabla: dict) -> Reversion:
    """Revierte párrafo por párrafo (una etiqueta nunca cruza de un párrafo a otro)."""
    total, lineas, desconocidas = 0, [], []
    for parte, raiz in _raices(documento):
        for p in raiz.iter(_w("p")):
            nodos = [t for t in p.iter(_w("t")) if _parrafo_de(t) is p and _texto(t)]
            texto = "".join(_texto(t) for t in nodos)
            for d in etiquetas_desconocidas(texto, tabla):
                if d not in desconocidas:
                    desconocidas.append(d)
            cambios = reemplazos(texto, tabla)
            if cambios:
                _sustituir(nodos, cambios)
                total += len(cambios)
            lineas.append(revertir(texto, tabla))
        _guardar_raiz(parte, raiz)
    return Reversion("\n".join(lineas).strip("\n"), total, desconocidas)


def _sustituir(nodos, cambios, espacio: bool = True) -> None:
    inicios, pos = [], 0
    textos = [_texto(n) for n in nodos]
    for t in textos:
        inicios.append(pos)
        pos += len(t)
    for ini, fin, valor in reversed(cambios):
        tocados = [k for k, t in enumerate(textos) if inicios[k] < fin and inicios[k] + len(t) > ini]
        for k in reversed(tocados):
            li, lf = max(ini - inicios[k], 0), min(fin - inicios[k], len(textos[k]))
            textos[k] = textos[k][:li] + (valor if k == tocados[0] else "") + textos[k][lf:]
    for nodo, nuevo in zip(nodos, textos):
        if nuevo != _texto(nodo):
            _pon_texto(nodo, nuevo)
            if espacio:  # en WordprocessingML; <a:t> de DrawingML conserva espacios sin él
                nodo.set(f"{{{XML_NS}}}space", "preserve")


def revertir_docx(entrada: str | Path, salida: str | Path, tabla: dict) -> Reversion:
    """El .docx de la IA con los datos reales y TODO lo demás idéntico.

    No pasa por python-docx (que vuelve a escribir cada parte que abre: declaraciones,
    [Content_Types], .rels vacíos). Se copia el .zip entrada por entrada, con su mismo
    orden, compresión y fecha, y solo se reescriben las partes donde hubo una etiqueta;
    dentro de ellas solo cambia el texto. Además del cuerpo, revierte encabezados, pies,
    notas, comentarios, cuadros de texto, cambios controlados (también lo tachado, que se
    ve en la revisión), gráficas, las propiedades del archivo (título, autor…) y los
    destinos de los enlaces (mailto:[CORREO_1])."""
    entrada, salida = Path(entrada), Path(salida)
    if salida.resolve() == entrada.resolve():
        raise ValueError(tr('Guarda el resultado con otro nombre: el archivo de la IA se conserva.'))
    try:
        origen = zipfile.ZipFile(entrada)
        tipos = _tipos_de_parte(origen)
    except Exception as e:
        raise ValueError(tr('No pude abrir {entrada} como documento de Word: {e}', entrada=entrada.name, e=e)) from e
    cuenta = _Cuenta(tabla)
    temporal = salida.with_name(f".{salida.name}.tmp")
    try:
        with origen, zipfile.ZipFile(temporal, "w") as destino:
            for info in origen.infolist():
                datos = origen.read(info)
                if not info.is_dir():
                    datos = _revertir_parte(info.filename, datos, tipos, cuenta)
                destino.writestr(info, datos)
        temporal.replace(salida)
    finally:
        temporal.unlink(missing_ok=True)
    return Reversion("\n".join(cuenta.lineas).strip("\n"), cuenta.total, cuenta.desconocidas)


_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
_C = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
_TIPOS_TEXTO = {f"{CT_WORD}{t}+xml" for t in ("document.main", "header", "footer", "footnotes", "endnotes",
                                               "comments", "template.main", "document.macroEnabled.main")}


class _Cuenta:
    def __init__(self, tabla: dict):
        self.tabla, self.total, self.lineas, self.desconocidas = tabla, 0, [], []

    def ver(self, texto: str) -> list:
        for d in etiquetas_desconocidas(texto, self.tabla):
            if d not in self.desconocidas:
                self.desconocidas.append(d)
        cambios = reemplazos(texto, self.tabla)
        self.total += len(cambios)
        return cambios


def _tipos_de_parte(origen: zipfile.ZipFile) -> dict[str, str]:
    """Nombre de cada parte → su tipo, según [Content_Types].xml (no se adivina por el nombre:
    Google Docs y otros nombran distinto los encabezados)."""
    raiz = etree.fromstring(origen.read("[Content_Types].xml"))
    por_extension, tipos = {}, {}
    for el in raiz:
        if el.tag.endswith("Default"):
            por_extension[el.get("Extension", "").lower()] = el.get("ContentType", "")
        elif el.tag.endswith("Override"):
            tipos[el.get("PartName", "").lstrip("/")] = el.get("ContentType", "")
    for nombre in origen.namelist():
        if nombre not in tipos:
            tipos[nombre] = por_extension.get(nombre.rsplit(".", 1)[-1].lower(), "")
    return tipos


def _revertir_parte(nombre: str, datos: bytes, tipos: dict, cuenta: _Cuenta) -> bytes:
    tipo = tipos.get(nombre, "")
    if tipo in _TIPOS_TEXTO:
        editar = _revertir_wordml
    elif nombre.endswith(".rels"):
        editar = _revertir_enlaces
    elif nombre.startswith("docProps/") and nombre.endswith(".xml"):
        editar = _revertir_hojas
    elif "drawingml" in tipo or nombre.startswith(("word/charts/", "word/diagrams/")):
        editar = _revertir_dibujo
    else:
        return datos
    try:
        raiz = etree.fromstring(datos)
    except etree.XMLSyntaxError:
        return datos
    if not editar(raiz, cuenta, guardar_lineas=tipo.startswith(CT_WORD + "document")):
        return datos  # sin cambios: los bytes originales, tal cual
    declaracion = datos[: datos.index(b"?>") + 2] if datos.lstrip().startswith(b"<?xml") else b""
    cuerpo = etree.tostring(raiz, encoding="UTF-8", xml_declaration=False)
    return declaracion + (b"\r\n" if declaracion and datos[len(declaracion):len(declaracion) + 2] == b"\r\n"
                          else b"\n" if declaracion and datos[len(declaracion):len(declaracion) + 1] == b"\n"
                          else b"") + cuerpo


def _revertir_wordml(raiz, cuenta: _Cuenta, guardar_lineas: bool = False) -> bool:
    """Párrafo por párrafo; el texto normal, el tachado y los códigos de campo, cada uno
    por su lado (una etiqueta no cruza de uno a otro)."""
    hubo = False
    for p in raiz.iter(_w("p")):
        for marca in ("t", "delText", "instrText"):
            nodos = [t for t in p.iter(_w(marca)) if _parrafo_de(t) is p and _texto(t)]
            if not nodos:
                continue
            texto = "".join(_texto(t) for t in nodos)
            cambios = cuenta.ver(texto)
            if cambios:
                _sustituir(nodos, cambios)
                hubo = True
            if marca == "t" and guardar_lineas:
                cuenta.lineas.append(revertir(texto, cuenta.tabla))
    return hubo


def _revertir_hojas(raiz, cuenta: _Cuenta, **_) -> bool:
    """Propiedades del archivo (título, asunto, autor, empresa…): cada valor por separado."""
    hubo = False
    for el in raiz.iter():
        if len(el) == 0 and isinstance(el.tag, str) and el.text and cuenta.ver(el.text):
            el.text = revertir(el.text, cuenta.tabla)
            hubo = True
    return hubo


def _revertir_enlaces(raiz, cuenta: _Cuenta, **_) -> bool:
    """Destinos externos de los enlaces: «mailto:[CORREO_1]» (a veces con %5B…%5D)."""
    hubo = False
    for el in raiz:
        destino = el.get("Target")
        if el.get("TargetMode") != "External" or not destino:
            continue
        legible = urllib.parse.unquote(destino)
        if cuenta.ver(legible):
            el.set("Target", revertir(legible, cuenta.tabla))
            hubo = True
    return hubo


def _revertir_dibujo(raiz, cuenta: _Cuenta, **_) -> bool:
    """Gráficas y SmartArt: el texto va en <a:t> por párrafo <a:p> y en valores <c:v>."""
    hubo = False
    for p in raiz.iter(_A + "p"):
        nodos = [t for t in p.iter(_A + "t") if t.text]
        cambios = cuenta.ver("".join(t.text for t in nodos)) if nodos else []
        if cambios:
            _sustituir(nodos, cambios, espacio=False)
            hubo = True
    for v in raiz.iter(_C + "v"):
        if v.text and cuenta.ver(v.text):
            v.text = revertir(v.text, cuenta.tabla)
            hubo = True
    return hubo


def texto_de_docx(ruta: str | Path) -> str:
    """Texto de un .docx (para la vista previa); sin revertir."""
    documento = docx.Document(str(ruta))
    lineas = []
    for _, raiz in _raices(documento):
        for p in raiz.iter(_w("p")):
            lineas.append("".join(_texto(t) for t in p.iter(_w("t")) if _parrafo_de(t) is p and _texto(t)))
    return "\n".join(lineas).strip("\n")


# --- texto (Markdown) a Word -------------------------------------------------------------

_TITULO = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_VIÑETA = re.compile(r"^(\s*)[-*+•]\s+(.*)$")
_NUMERO = re.compile(r"^(\s*)(\d+[.)])\s+(.*)$")
_REGLA = re.compile(r"^\s*([-*_])(\s*\1){2,}\s*$")
_FILA = re.compile(r"^\s*\|.*\|\s*$")
_SEPARADOR = re.compile(r"^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$")
_EN_LINEA = re.compile(
    r"\\([\\`*_#\[\]()>|-])"  # carácter escapado
    r"|(_{3,}|\*{4,})"  # espacio para llenar (___): va tal cual
    r"|\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*"  # negrita y cursiva
    r"|\*\*(?![\s*])(.+?)(?<![\s*])\*\*|__(?![\s_])(.+?)(?<![\s_])__"  # negrita
    r"|(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])"  # cursiva
    r"|(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])"
    r"|`([^`]+)`"  # código
    r"|\[([^\]]+)\]\((https?://[^)\s]+)\)",  # enlace
    re.S,
)


def _en_linea(parrafo, texto: str, negrita=False, cursiva=False, codigo=False) -> None:
    pos = 0
    for m in _EN_LINEA.finditer(texto):
        _run(parrafo, texto[pos:m.start()], negrita, cursiva, codigo)
        escapado, blanco, ambas, n1, n2, c1, c2, cod, enlace, url = m.groups()
        if escapado or blanco:
            _run(parrafo, escapado or blanco, negrita, cursiva, codigo)
        elif ambas:
            _en_linea(parrafo, ambas, True, True, codigo)
        elif n1 or n2:
            _en_linea(parrafo, n1 or n2, True, cursiva, codigo)
        elif c1 or c2:
            _en_linea(parrafo, c1 or c2, negrita, True, codigo)
        elif cod:
            _run(parrafo, cod, negrita, cursiva, True)
        elif enlace:
            _en_linea(parrafo, enlace, negrita, cursiva, codigo)
            _run(parrafo, f" ({url})", negrita, cursiva, codigo)
        pos = m.end()
    _run(parrafo, texto[pos:], negrita, cursiva, codigo)


def _run(parrafo, texto: str, negrita: bool, cursiva: bool, codigo: bool) -> None:
    if not texto:
        return
    for k, trozo in enumerate(texto.split("\n")):  # salto de línea forzado
        if k:
            parrafo.add_run().add_break()
        if trozo:
            r = parrafo.add_run(trozo)
            r.bold, r.italic = negrita or None, cursiva or None
            if codigo:
                r.font.name = "Courier New"


def _estilos(documento) -> None:
    normal = documento.styles["Normal"]
    normal.font.name, normal.font.size = FUENTE, Pt(12)
    normal.element.get_or_add_rPr().get_or_add_rFonts().set(qn("w:eastAsia"), FUENTE)
    normal.paragraph_format.space_after = Pt(8)
    normal.paragraph_format.line_spacing = 1.15
    for nivel, tam in zip(range(1, 7), (16, 14, 13, 12, 12, 12)):
        estilo = documento.styles[f"Heading {nivel}"]
        estilo.font.name, estilo.font.size, estilo.font.bold = FUENTE, Pt(tam), True
        estilo.font.italic = False
        estilo.font.color.rgb = RGBColor(0, 0, 0)
        rfonts = estilo.element.get_or_add_rPr().get_or_add_rFonts()
        for atributo in ("w:asciiTheme", "w:hAnsiTheme", "w:eastAsiaTheme", "w:cstheme"):
            rfonts.attrib.pop(qn(atributo), None)
        rfonts.set(qn("w:ascii"), FUENTE)
        rfonts.set(qn("w:hAnsi"), FUENTE)
    cp = documento.core_properties  # que el documento no diga "python-docx"
    cp.author = cp.last_modified_by = cp.title = cp.subject = cp.keywords = cp.comments = ""
    quitar_miniatura(documento)


def _tabla(documento, filas: list[str]) -> None:
    celdas = [[c.strip() for c in f.strip().strip("|").split("|")] for f in filas]
    ancho = max(len(f) for f in celdas)
    t = documento.add_table(rows=len(celdas), cols=ancho)
    t.style = "Table Grid"
    for i, fila in enumerate(celdas):
        for j in range(ancho):
            p = t.cell(i, j).paragraphs[0]
            _en_linea(p, fila[j] if j < len(fila) else "", negrita=i == 0)
    documento.add_paragraph()


def markdown_a_documento(texto: str):
    """Arma un documento de Word con el Markdown de la IA (sin revertir)."""
    documento = docx.Document()
    _estilos(documento)
    lineas = texto.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    parrafo: list[str] = []
    cita = False

    def cerrar():
        """Cada renglón de la IA es un párrafo en Word, pegado al siguiente: los chats no cortan
        los párrafos a mano, y con saltos de línea Word estiraría "EXPEDIENTE: ___" a lo ancho."""
        nonlocal parrafo, cita
        for k, linea in enumerate(parrafo):
            p = documento.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            if k < len(parrafo) - 1:
                p.paragraph_format.space_after = Pt(0)
            if cita:
                p.paragraph_format.left_indent = Cm(1)
            _en_linea(p, linea.rstrip(" \\"))
        parrafo, cita = [], False

    i = 0
    while i < len(lineas):
        linea = lineas[i]
        if linea.strip().startswith("```"):
            cerrar()
            i += 1
            while i < len(lineas) and not lineas[i].strip().startswith("```"):
                p = documento.add_paragraph()
                _run(p, lineas[i], False, False, True)
                p.paragraph_format.space_after = Pt(0)
                i += 1
            i += 1
            continue
        if _FILA.match(linea) and i + 1 < len(lineas) and _SEPARADOR.match(lineas[i + 1]):
            cerrar()
            filas = [linea]
            i += 2
            while i < len(lineas) and _FILA.match(lineas[i]):
                filas.append(lineas[i])
                i += 1
            _tabla(documento, filas)
            continue
        es_cita = linea.lstrip().startswith(">")
        if es_cita:
            linea = re.sub(r"^\s*>\s?", "", linea)
            if not cita:
                cerrar()
            cita = True
        elif cita:
            cerrar()
        if not linea.strip():
            if not es_cita:
                cerrar()
        elif (m := _TITULO.match(linea)) and not es_cita:
            cerrar()
            _en_linea(documento.add_heading(level=len(m.group(1))), m.group(2))
        elif _REGLA.match(linea):
            cerrar()
        elif m := _VIÑETA.match(linea):
            cerrar()
            nivel = min(len(m.group(1).expandtabs(4)) // 2, 2)
            p = documento.add_paragraph(style="List Bullet" + (f" {nivel + 1}" if nivel else ""))
            if es_cita:
                p.paragraph_format.left_indent = Cm(1.6)
            _en_linea(p, m.group(2))
        elif m := _NUMERO.match(linea):
            cerrar()
            # El número va escrito: la numeración automática de Word no reinicia entre listas.
            p = documento.add_paragraph()
            sangria = Cm(0.9 + 0.6 * min(len(m.group(1).expandtabs(4)) // 2, 2) + (1 if es_cita else 0))
            p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = sangria, Cm(-0.7)
            p.paragraph_format.tab_stops.add_tab_stop(sangria)
            _run(p, m.group(2) + "\t", False, False, False)
            _en_linea(p, m.group(3))
        else:
            parrafo.append(linea)
        i += 1
    cerrar()
    return documento


def texto_a_docx(texto: str, salida: str | Path, tabla: dict) -> Reversion:
    """El texto de la IA → .docx con formato y con los datos reales."""
    documento = markdown_a_documento(texto)
    r = _revertir_documento(documento, tabla)
    documento.save(str(salida))
    return Reversion(revertir(texto, tabla), r.reemplazos, etiquetas_desconocidas(texto, tabla))


def markdown_a_texto(texto: str) -> str:
    """Quita las marcas de Markdown para pegar en un correo o en otro programa."""
    lineas = []
    for linea in texto.replace("\r\n", "\n").split("\n"):
        if _REGLA.match(linea) or (_SEPARADOR.match(linea) and "|" in linea):
            continue
        linea = re.sub(r"^\s*>\s?", "", linea)
        linea = re.sub(r"^#{1,6}\s+(.*?)\s*#*\s*$", r"\1", linea)
        linea = re.sub(r"^(\s*)[-*+]\s+", r"\1• ", linea)
        if _FILA.match(linea):
            linea = " · ".join(c.strip() for c in linea.strip().strip("|").split("|"))
        lineas.append(linea)
    plano = "\n".join(lineas)
    plano = re.sub(r"\*\*\*(?!\s)(.+?)(?<!\s)\*\*\*|\*\*(?![\s*])(.+?)(?<![\s*])\*\*|__(?![\s_])(.+?)(?<![\s_])__", lambda m: next(g for g in m.groups() if g), plano, flags=re.S)
    plano = re.sub(r"(?<![\w*])\*(?![\s*])(.+?)(?<![\s*])\*(?![\w*])", r"\1", plano)
    plano = re.sub(r"(?<![\w_])_(?![\s_])(.+?)(?<![\s_])_(?![\w_])", r"\1", plano)
    plano = re.sub(r"`([^`]+)`", r"\1", plano)
    plano = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r"\1 (\2)", plano)
    plano = re.sub(r"\\([\\`*_#\[\]()>|-])", r"\1", plano)
    return re.sub(r"\n{3,}", "\n\n", plano).strip()


def nombre_sugerido(origen: str | Path | None, tabla: str | Path) -> Path:
    """respuesta.docx → respuesta_revertido.docx; sin archivo, junto a la tabla."""
    if origen:
        o = Path(origen)
        base = o.with_name(f"{o.stem}_revertido.docx")
    else:
        t = Path(tabla)
        base = t.with_name(t.stem.removesuffix("_tabla") + "_respuesta_ia.docx")
    n, candidata = 1, base
    while candidata.exists():
        n += 1
        candidata = base.with_name(f"{base.stem}_{n}.docx")
    return candidata

