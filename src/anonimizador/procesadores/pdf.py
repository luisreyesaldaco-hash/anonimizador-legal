"""Procesador de PDF.

Usa redacción real de PyMuPDF: el texto original se elimina del contenido de la página
(no se tapa con un rectángulo), y en las páginas escaneadas se borran los píxeles de la
imagen bajo cada hallazgo. Encima se escribe la etiqueta ([PERSONA_1]).

Antes de extraer el texto se "hornean" formularios y anotaciones en la página, para que
los valores de los campos se traten como texto normal y no sobrevivan como datos.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from ..seudonimos import Entidad, aplicar, localizar, plegar
from ..verificacion import Fuga, ResultadoVerificacion, buscar_en_cadenas
from . import ocr
from ..textos import tr

FUENTE = "helv"
TAM_MIN = 4.0
ESCALA_MIN = 0.55  # cuánto se puede angostar una etiqueta antes de achicarla
MARGEN_OCR = 0.25  # las cajas del OCR son aproximadas: se agrandan esta fracción de la altura


class DocumentoNoSoportado(Exception):
    pass


@dataclass
class _Caracter:
    pagina: int
    rect: pymupdf.Rect | None  # None = separador sintético (salto de línea)
    tam: float = 0.0
    origen: tuple[float, float] = (0.0, 0.0)  # punto de la línea base


@dataclass
class Informe:
    salida: Path
    apariciones: int
    verificacion: ResultadoVerificacion
    avisos: list[str] = field(default_factory=list)

    @property
    def limpio(self) -> bool:
        return self.verificacion.limpio


def _texto_de_pagina(pagina: pymupdf.Page, textpage=None) -> tuple[str, list[_Caracter]]:
    datos = pagina.get_text("rawdict", textpage=textpage, flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    texto: list[str] = []
    chars: list[_Caracter] = []
    for bloque in datos["blocks"]:
        if bloque.get("type") != 0:
            continue
        for linea in bloque["lines"]:
            for span in linea["spans"]:
                for c in span["chars"]:
                    texto.append(c["c"])
                    chars.append(_Caracter(pagina.number, pymupdf.Rect(c["bbox"]), span["size"], tuple(c["origin"])))
            texto.append("\n")
            chars.append(_Caracter(pagina.number, None))
        texto.append("\n")
        chars.append(_Caracter(pagina.number, None))
    return "".join(texto), chars


class DocumentoPDF:
    def __init__(self, ruta: str | Path, usar_ocr: bool = True, datos: bytes | None = None, avance=None):
        """`datos`: el PDF ya en memoria (una foto o un escaneo convertido aquí); `ruta` sigue
        siendo el archivo original, para nombres y para no sobrescribirlo."""
        self.ruta = Path(ruta)
        try:
            self._doc = pymupdf.open("pdf", datos) if datos is not None else pymupdf.open(str(self.ruta))
        except Exception as e:
            raise DocumentoNoSoportado(tr('No pude abrir {ruta} como PDF: {e}', ruta=self.ruta.name, e=e)) from e
        if self._doc.needs_pass:
            raise DocumentoNoSoportado(
                tr('{ruta} está protegido con contraseña. Quita la protección y vuelve a intentarlo.', ruta=self.ruta.name)
            )
        if not self._doc.is_pdf:
            raise DocumentoNoSoportado(tr('{ruta} no es un PDF.', ruta=self.ruta.name))
        self.avisos: list[str] = []
        self.paginas_ocr: list[int] = []
        self._doc.bake(annots=True, widgets=True)
        self.texto, self._chars = self._extraer(usar_ocr, avance)

    def _extraer(self, usar_ocr: bool, avance=None) -> tuple[str, list[_Caracter]]:
        """`avance(pagina, total)` antes de cada página que va al OCR: tarda varios segundos
        por página y la ventana tiene que mostrar que sigue trabajando."""
        partes, chars = [], []
        sin_texto = []
        for pagina in self._doc:
            t, c = _texto_de_pagina(pagina)
            if not t.strip() and pagina.get_images():
                if usar_ocr and ocr.disponible():
                    if avance:
                        avance(pagina.number + 1, self._doc.page_count)
                    t, c = _texto_de_pagina(pagina, textpage=ocr.textpage(pagina))
                    self.paginas_ocr.append(pagina.number + 1)
                else:
                    sin_texto.append(pagina.number + 1)
            partes.append(t)
            chars += c
        if sin_texto:
            paginas = ", ".join(map(str, sin_texto))
            self.avisos.append(
                tr('Las páginas {paginas} parecen escaneadas y no se pudieron leer (falta el OCR). Sus datos NO se anonimizaron.', paginas=paginas)
            )
        if self.paginas_ocr:
            paginas = ", ".join(map(str, self.paginas_ocr))
            self.avisos.append(
                tr('Página(s) {paginas} escaneada(s): se leyeron con OCR. Las firmas, sellos y lo escrito a mano siguen visibles; revísalas antes de compartir.', paginas=paginas)
            )
        return "".join(partes), chars

    def pagina_de(self, posicion: int) -> int | None:
        """Página (desde 1) donde está el carácter `posicion` de `self.texto`."""
        if 0 <= posicion < len(self._chars):
            return self._chars[posicion].pagina + 1
        return None

    def cortes_de_pagina(self) -> list[int]:
        """Posiciones de `self.texto` donde empieza cada página (salvo la primera)."""
        cortes, anterior = [], None
        for i, c in enumerate(self._chars):
            if anterior is not None and c.pagina != anterior:
                cortes.append(i)
            anterior = c.pagina
        return cortes

    def guardar_word(self, salida: str | Path, entidades: list[Entidad]) -> Informe:
        """Salida en .docx: el texto seudonimizado, editable, sin el diseño del PDF."""
        from .a_word import guardar_como_word

        salida = Path(salida)
        apariciones, verificacion = guardar_como_word(self.texto, entidades, salida, self.cortes_de_pagina())
        avisos = self.avisos + [tr('Salida en Word: se conserva el texto, no el diseño del PDF; las firmas, sellos e imágenes no se copian.')] + verificacion.avisos
        return Informe(salida, len(apariciones), verificacion, avisos)

    @property
    def escaneado_sin_ocr(self) -> bool:
        return any("escaneadas" in a for a in self.avisos)

    def texto_limpio(self, entidades: list[Entidad]) -> str:
        marcadas = [e for e in entidades if e.marcada]
        return aplicar(self.texto, localizar(self.texto, entidades), marcadas)

    def guardar(self, salida: str | Path, entidades: list[Entidad]) -> Informe:
        salida = Path(salida)
        if salida.resolve() == self.ruta.resolve():
            raise ValueError(tr('La salida no puede ser el archivo original; elige otro nombre.'))
        marcadas = [e for e in entidades if e.marcada]
        apariciones = localizar(self.texto, entidades)  # las desmarcadas reservan su lugar
        marcadores = {e.etiqueta: e.marcador for e in marcadas}

        for pagina in self._doc:  # notas, enlaces y demás anotaciones fuera
            for annot in list(pagina.annots() or []):
                pagina.delete_annot(annot)

        etiquetas = []  # se escriben después de redactar, sobre la línea base original
        for a in apariciones:
            for i, (num, rect, tam, origen) in enumerate(self._rects_por_linea(a.inicio, a.fin)):
                self._doc[num].add_redact_annot(rect, fill=(1, 1, 1), cross_out=False)
                if i == 0:
                    etiquetas.append((num, rect, tam, origen, marcadores[a.etiqueta]))
        for pagina in self._doc:
            pagina.apply_redactions(
                images=pymupdf.PDF_REDACT_IMAGE_PIXELS,
                graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                text=pymupdf.PDF_REDACT_TEXT_REMOVE,
            )
        for num, rect, tam, origen, etiqueta in etiquetas:
            self._escribir_etiqueta(self._doc[num], rect, tam, origen, etiqueta)

        self._limpiar(entidades)
        self._doc.save(str(salida), garbage=4, deflate=True, clean=True)
        verificacion = verificar_pdf(salida, entidades, todas=entidades,
                                     paginas_ocr=[n - 1 for n in self.paginas_ocr])
        return Informe(salida, len(apariciones), verificacion, self.avisos + verificacion.avisos)

    def _rects_crudos(self, inicio: int, fin: int):
        """Une los rectángulos de los caracteres de cada línea (un nombre puede partirse en dos)."""
        actual = None
        for c in self._chars[inicio:fin]:
            if c.rect is None:
                if actual:
                    yield actual
                actual = None
                continue
            if actual is None:
                actual = [c.pagina, pymupdf.Rect(c.rect), c.tam, c.origen, 1]
            else:
                actual[1] |= c.rect
                actual[2] = max(actual[2], c.tam)
                actual[4] += 1
        if actual:
            yield tuple(actual)

    def _rects_por_linea(self, inicio: int, fin: int):
        ocr_ = {n - 1 for n in self.paginas_ocr}
        for num, rect, tam, origen, n in self._rects_crudos(inicio, fin):
            if num in ocr_:
                # El OCR reparte el ancho de la palabra entre sus letras: los bordes pueden
                # quedar corridos hasta media letra. Se agranda un carácter promedio por lado.
                mv = rect.height * MARGEN_OCR
                mh = max(mv, rect.width / n)
                rect = pymupdf.Rect(rect.x0 - mh, rect.y0 - mv, rect.x1 + mh, rect.y1 + mv)
            yield num, rect, tam, origen

    @staticmethod
    def _escribir_etiqueta(pagina, rect, tam, origen, etiqueta) -> None:
        """La etiqueta va en el hueco del dato. Si no cabe ("IMV" → "[EMPRESA_1]"), primero se
        angosta (conserva la altura y se lee) y solo después se achica."""
        tam = tam or rect.height * 0.8
        ancho = pymupdf.get_text_length(etiqueta, fontname=FUENTE, fontsize=1) * tam
        disponible = max(rect.width - 0.5, 1)
        escala = 1.0
        if ancho > disponible:
            escala = max(ESCALA_MIN, disponible / ancho)
            tam = max(TAM_MIN, tam * min(1.0, disponible / (ancho * escala)))
        punto = pymupdf.Point(rect.x0, origen[1])
        pagina.insert_text(punto, etiqueta, fontname=FUENTE, fontsize=tam, color=(0, 0, 0),
                           morph=(punto, pymupdf.Matrix(escala, 1)) if escala < 1 else None)

    def _limpiar(self, entidades: list[Entidad]) -> None:
        def sust(s: str) -> str:
            aps = localizar(s, entidades)
            return aplicar(s, aps, entidades) if aps else s

        toc = self._doc.get_toc(simple=False)
        if toc:
            self._doc.set_toc([[nivel, sust(titulo), pag, *resto] for nivel, titulo, pag, *resto in toc])
        self._doc.scrub(
            attached_files=True, clean_pages=True, embedded_files=True, hidden_text=False,
            javascript=True, metadata=True, redactions=True, remove_links=True,
            reset_fields=True, reset_responses=True, thumbnails=True, xml_metadata=True,
        )
        self._doc.set_metadata({})
        self._doc.del_xml_metadata()


def verificar_pdf(ruta: str | Path, entidades: list[Entidad], todas: list[Entidad] | None = None,
                 paginas_ocr: list[int] = ()) -> ResultadoVerificacion:
    """Reabre la salida y busca los valores originales.

    En las páginas que eran imagen, el texto del archivo solo tiene las etiquetas: lo que
    importa son los píxeles. Esas páginas se vuelven a leer con OCR y se buscan ahí tanto los
    valores marcados como cualquier dato nuevo que el detector encuentre (algo que la
    primera lectura no vio y por lo tanto sigue visible en la imagen).
    """
    fugas, avisos = [], []
    conocidos = {plegar(v) for e in (todas or entidades) for v in e.variantes}
    with pymupdf.open(str(ruta)) as doc:
        for pagina in doc:
            fugas += buscar_en_cadenas(tr('página {number}', number=pagina.number + 1), [pagina.get_text()], entidades)
            for annot in pagina.annots() or []:
                fugas += buscar_en_cadenas(tr('anotación p. {number}', number=pagina.number + 1), [annot.info.get("content", "")], entidades)
            if pagina.number in paginas_ocr and ocr.disponible():
                fugas += _verificar_imagen(pagina, entidades, conocidos)
            elif pagina.get_images() and not pagina.get_text().strip():
                avisos.append(tr('Página {number}: imagen sin texto, no se puede verificar.', number=pagina.number + 1))
        fugas += buscar_en_cadenas("metadatos", [str(v) for v in doc.metadata.values() if v], entidades)
        fugas += buscar_en_cadenas("XMP", [doc.get_xml_metadata()], entidades)
        fugas += buscar_en_cadenas("marcadores", [t[1] for t in doc.get_toc()], entidades)
        if doc.embfile_count():
            fugas.append(Fuga(tr('archivos adjuntos'), "-", tr('el PDF todavía tiene archivos incrustados')))
    return ResultadoVerificacion(fugas, avisos)


def _verificar_imagen(pagina: pymupdf.Page, entidades: list[Entidad], conocidos: set[str]) -> list[Fuga]:
    from ..detector import detectar

    donde = tr('imagen de la página {number}', number=pagina.number + 1)
    texto, _ = _texto_de_pagina(pagina, textpage=ocr.textpage(pagina))
    fugas = buscar_en_cadenas(donde, [texto], entidades)
    for h in detectar(texto, usar_ner=False):
        if plegar(h.valor) not in conocidos and not _es_etiqueta(texto, h.inicio, h.fin):
            fugas.append(Fuga(donde, h.tipo, texto[max(0, h.inicio - 30):h.fin + 30].replace("\n", " ")))
    return fugas


def _es_etiqueta(texto: str, inicio: int, fin: int) -> bool:
    return texto.rfind("[", 0, inicio + 1) > texto.rfind("]", 0, inicio) and "]" in texto[fin:fin + 2]
