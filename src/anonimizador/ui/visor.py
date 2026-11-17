"""Visor del documento original, para echarle un vistazo sin salir de la revisión.

`VisorDocumento` es un componente independiente (un `CTkFrame`) con dos modos:

* PDF: las páginas se dibujan con PyMuPDF en un lienzo con desplazamiento continuo,
  zoom (ajustar al ancho, +/−) y «página X de N». Solo se dibujan las páginas visibles
  (y una de margen), una por vuelta del bucle de Tk, con una caché acotada en memoria:
  un PDF de 300 páginas abre al instante y no congela la ventana.
* Texto (.docx/.doc): el texto que ya extrajo el procesador, en un cuadro de solo lectura.

En ambos, `resaltar()` pinta los datos marcados (tenue) y los seleccionados (dorado, con
borde), y `ir_a()` lleva a la n-ésima aparición de un dato y la centra.

La búsqueda es la misma idea que `seudonimos.localizar`: sin distinguir mayúsculas ni
acentos («MARÍA» = «Maria»), con cualquier espacio o salto de línea entre palabras (un
nombre puede partirse en dos renglones) y respetando los límites de palabra. Los
identificadores (RFC, CURP, CLABE…) se encuentran con o sin guiones, puntos o espacios.

Notas de diseño:

* Hilos: PyMuPDF no suelta el GIL mientras dibuja, así que dibujar en otro hilo no
  aliviaría a Tk (medido). Se dibuja en el hilo de Tk, una página por vuelta del bucle
  (`after`), lo más cercano al centro de la vista primero; una página de texto tarda
  ~5 ms a 2x. Todo acceso al `pymupdf.Document` ocurre en el hilo de Tk.
* Nitidez (HiDPI): el zoom se lleva en píxeles reales por punto PDF y se dibuja
  directamente a ese tamaño (nunca se reescala una imagen). En Windows (CustomTkinter
  activa el modo «DPI aware») y en Linux un píxel de Tk es un píxel de pantalla, así
  que el documento sale nítido a cualquier escala. En macOS con pantalla Retina, Tk
  (8.6 y 9.0) dibuja las imágenes a un píxel por punto y el sistema las amplía 2x: el
  texto se ve algo suave al 100 %. Tk no ofrece forma de entregar una imagen a doble
  densidad; con el zoom (+) el usuario gana detalle real, porque se vuelve a dibujar.
* PDF escaneado: la imagen se ve siempre. El resaltado necesita la capa de texto: si el
  PDF no la tiene y no se pasa la del OCR (`cargar(..., texto=, cajas=)` con lo que ya
  extrajo `DocumentoPDF`), no hay resaltado e `ir_a` devuelve 0.
"""

from __future__ import annotations

import bisect
import re
import sys
import tkinter as tk
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import customtkinter as ctk
import pymupdf
from PIL import Image, ImageChops, ImageDraw, ImageTk

from ..seudonimos import plegar
from ..textos import tr

# Paleta de la app (la misma que ventana.py; se repite para no importar la ventana).
ACENTO = ("#23221e", "#b8853a")
ACENTO_HOVER = ("#45443e", "#cc9a4f")
FONDO = ("#e4e2dd", "#262523")  # gris neutro alrededor de las páginas
SOMBRA = (("#cfccc5", "#d9d6d0"), ("#141413", "#1c1b1a"))  # (cercana, lejana) por modo
TEXTO_TENUE = ("gray35", "gray65")
# Resaltado: se multiplica sobre la página, así la tinta sigue negra debajo del color.
MARCADO = (0xF2, 0xE6, 0xCC)
SELECCION = (0xE2, 0xC4, 0x8F)
BORDE_SELECCION = (0xB8, 0x85, 0x3A)
# En modo texto (colores de etiqueta de Tk, por modo claro/oscuro)
TEXTO_MARCADO = (("#f3e9d4", "#23221e"), ("#433a2a", "#f1e9da"))  # (fondo, letra)
TEXTO_SELECCION = (("#e2c48f", "#23221e"), ("#e2c48f", "#23221e"))

MARGEN = 16  # px alrededor de las páginas
SEPARACION = 12  # px entre páginas
ZOOM_MIN, ZOOM_MAX = 0.25, 6.0  # relativo al tamaño real (100 %)
PASO_ZOOM = 1.2
CACHE_BYTES = 64 * 1024 * 1024  # imágenes base de páginas ya dibujadas (~45 págs carta a 100 %)
PAGINAS_CON_CAJAS = 40  # páginas con cajas por carácter en memoria (para resaltar)
INDEXAR_POR_VUELTA = 8  # páginas de texto plano por vuelta del bucle al abrir (~15 ms)


# --- búsqueda -------------------------------------------------------------------------


def patron(termino: str) -> re.Pattern | None:
    """Patrón sobre el texto plegado (minúsculas, sin acentos; misma longitud que el original)."""
    palabras = plegar(termino).split()
    if not palabras:
        return None
    if len(palabras) == 1 and any(c.isdigit() for c in palabras[0]):
        # Identificadores, fechas y montos: con o sin separadores («ABC-123» = «ABC 123»).
        chars = [re.escape(c) for c in re.sub(r"[^0-9a-zñ&]", "", palabras[0])]
        if chars:
            return re.compile(r"[\s\-.,/]?".join(chars))
    return re.compile(r"\s+".join(re.escape(p) for p in palabras))


def _es_limite(texto: str, i: int) -> bool:
    return i < 0 or i >= len(texto) or not texto[i].isalnum()


def buscar(texto: str, terminos: Iterable[str], plegado: str | None = None) -> list[tuple[int, int]]:
    """Tramos (inicio, fin) de todas las apariciones, sin traslapes (gana la más larga), en orden."""
    plegado = plegar(texto) if plegado is None else plegado
    candidatos = []
    for t in dict.fromkeys(terminos):
        p = patron(t)
        if p is None:
            continue
        for m in p.finditer(plegado):
            if m.end() > m.start() and _es_limite(texto, m.start() - 1) and _es_limite(texto, m.end()):
                candidatos.append((m.start(), m.end()))
    candidatos.sort(key=lambda t: (t[0] - t[1], t[0]))
    elegidos: list[tuple[int, int]] = []
    for a in candidatos:
        if all(a[1] <= b[0] or a[0] >= b[1] for b in elegidos):
            elegidos.append(a)
    return sorted(elegidos)


def _quitar_traslapes(tramos: list[tuple[int, int]], contra: list[tuple[int, int]]) -> list[tuple[int, int]]:
    return [a for a in tramos if all(a[1] <= b[0] or a[0] >= b[1] for b in contra)]


# --- texto del PDF, por página ----------------------------------------------------------


@dataclass
class _Pagina:
    texto: str
    plegado: str
    cajas: list  # una por carácter de `texto`: (x0, y0, x1, y1) en puntos, o None en los saltos
    girar: Any = None  # pymupdf.Matrix si la página está girada (las cajas vienen sin girar)


def _extraer_pagina(pagina: pymupdf.Page) -> _Pagina:
    datos = pagina.get_text("rawdict", flags=pymupdf.TEXTFLAGS_RAWDICT & ~pymupdf.TEXT_PRESERVE_IMAGES)
    texto: list[str] = []
    cajas: list = []
    for bloque in datos["blocks"]:
        if bloque.get("type") != 0:
            continue
        for linea in bloque["lines"]:
            for span in linea["spans"]:
                for c in span["chars"]:
                    texto.append(c["c"])
                    cajas.append(tuple(c["bbox"]))
            texto.append("\n")
            cajas.append(None)
        texto.append("\n")
        cajas.append(None)
    t = "".join(texto)
    return _Pagina(t, plegar(t), cajas, pagina.rotation_matrix if pagina.rotation else None)


def _tupla(r) -> tuple[float, float, float, float]:
    return (r.x0, r.y0, r.x1, r.y1)


def _rects_por_linea(cajas: Sequence, inicio: int, fin: int, girar=None) -> list[pymupdf.Rect]:
    """Une las cajas de los caracteres de cada renglón: un tramo que cruza líneas da varios.

    Las cajas vienen en coordenadas sin girar (así las da PyMuPDF); si la página está
    girada, se unen primero y el resultado se gira con `girar` (la `rotation_matrix`)."""
    rects: list[pymupdf.Rect] = []
    actual = None
    for r in cajas[inicio:fin]:
        if r is None:
            if actual is not None:
                rects.append(actual)
            actual = None
        elif actual is None:
            actual = pymupdf.Rect(r)
        elif abs(r[1] - actual.y0) > actual.height * 0.6:  # saltó de renglón sin separador
            rects.append(actual)
            actual = pymupdf.Rect(r)
        else:
            actual |= r
    if actual is not None:
        rects.append(actual)
    if girar is not None:
        rects = [r * girar for r in rects]
    return [r for r in rects if not r.is_empty]


def tramo_en_capa(cajas: Sequence, inicio: int, fin: int, girar=None) -> tuple[int, list[pymupdf.Rect]] | None:
    """Página (0-based) y rectángulos (uno por renglón) del tramo [inicio, fin) de una capa de
    texto con cajas por carácter (`.pagina`, `.rect`), como la de `DocumentoPDF`. Si el tramo
    cruza de página, cuenta la primera. None si el tramo no tiene cajas. `girar(página)` da la
    `rotation_matrix` de una página girada (o None)."""
    tramo = list(cajas[max(0, inicio):max(0, fin)])
    primera = next((c for c in tramo if getattr(c, "rect", None) is not None), None)
    if primera is None:
        return None
    pagina = primera.pagina
    tuplas = [_tupla(c.rect) if getattr(c, "rect", None) is not None and c.pagina == pagina else None
              for c in tramo]
    rects = _rects_por_linea(tuplas, 0, len(tuplas), girar(pagina) if girar else None)
    return (pagina, rects) if rects else None


@dataclass(frozen=True)
class Aparicion:
    pagina: int  # 0-based
    rects: tuple  # pymupdf.Rect en puntos de la página, uno por renglón


class TextoPDF:
    """El texto de un PDF, perezoso y en dos niveles.

    * plano (rápido, ~1 ms/página): para saber en qué páginas aparece algo y cuántas veces;
    * con cajas por carácter (~7 ms/página): solo para las páginas que se dibujan o a las que se salta.

    Si se pasa `capa` (texto + cajas por carácter, p. ej. lo que extrajo `DocumentoPDF`,
    incluido el OCR), se usa tal cual y no se extrae nada del PDF.
    """

    def __init__(self, doc: pymupdf.Document, texto: str | None = None, cajas: Sequence | None = None):
        self.doc = doc
        self.n = len(doc)
        self._plano: list[str | None] = [None] * self.n
        # Las cajas por carácter pesan: solo se guardan las de las últimas páginas usadas.
        self._paginas: OrderedDict[int, _Pagina] = OrderedDict()
        self._limite_paginas: int | None = PAGINAS_CON_CAJAS
        self._siguiente = 0
        if texto is not None and cajas is not None and len(texto) == len(cajas):
            self._desde_capa(texto, cajas)

    def _desde_capa(self, texto: str, cajas: Sequence) -> None:
        por_pagina: dict[int, tuple[list[str], list]] = {}
        ultima = 0
        for ch, c in zip(texto, cajas):
            num = getattr(c, "pagina", ultima)
            ultima = num
            t, r = por_pagina.setdefault(num, ([], []))
            t.append(ch)
            rect = getattr(c, "rect", None)
            r.append(_tupla(rect) if rect is not None else None)
        for num in range(self.n):
            t, r = por_pagina.get(num, ([], []))
            s = "".join(t)
            pagina = self.doc[num]
            self._paginas[num] = _Pagina(s, plegar(s), r, pagina.rotation_matrix if pagina.rotation else None)
            self._plano[num] = self._paginas[num].plegado
        self._siguiente = self.n
        self._limite_paginas = None  # vienen de fuera: no se pueden volver a extraer

    @property
    def completo(self) -> bool:
        return self._siguiente >= self.n

    def indexar(self, cuantas: int | None = None) -> bool:
        """Extrae el texto plano de las siguientes `cuantas` páginas (todas si None). True si terminó."""
        fin = self.n if cuantas is None else min(self.n, self._siguiente + cuantas)
        for i in range(self._siguiente, fin):
            if self._plano[i] is None:
                self._plano[i] = plegar(self.doc[i].get_text("text"))
        self._siguiente = max(self._siguiente, fin)
        return self.completo

    def plano(self, i: int) -> str:
        if self._plano[i] is None:
            self._plano[i] = plegar(self.doc[i].get_text("text"))
        return self._plano[i]

    def pagina(self, i: int) -> _Pagina:
        p = self._paginas.get(i)
        if p is None:
            p = self._paginas[i] = _extraer_pagina(self.doc[i])
            if self._limite_paginas is not None and len(self._paginas) > self._limite_paginas:
                self._paginas.popitem(last=False)
        else:
            self._paginas.move_to_end(i)
        return p

    def conteo_por_pagina(self, terminos: Sequence[str]) -> list[tuple[int, int]]:
        """[(página, apariciones)] de las páginas donde aparece alguno de los términos."""
        self.indexar()
        salida = []
        for i in range(self.n):
            plano = self._plano[i]
            # El texto plano está plegado: los límites de palabra se ven igual en él.
            k = len(buscar(plano, terminos, plegado=plano))
            if k:
                salida.append((i, k))
        return salida

    def apariciones_en(self, i: int, terminos: Sequence[str]) -> list[Aparicion]:
        p = self.pagina(i)
        salida = []
        for ini, fin in buscar(p.texto, terminos, plegado=p.plegado):
            rects = _rects_por_linea(p.cajas, ini, fin, p.girar)
            if rects:
                salida.append(Aparicion(i, tuple(rects)))
        return salida

    def resaltados_en(self, i: int, marcados: Sequence[str], seleccionados: Sequence[str]):
        """(rects tenues, rects seleccionados) de la página; lo seleccionado tapa a lo marcado."""
        p = self.pagina(i)
        sel = buscar(p.texto, seleccionados, plegado=p.plegado) if seleccionados else []
        mar = _quitar_traslapes(buscar(p.texto, marcados, plegado=p.plegado), sel) if marcados else []
        a_rects = lambda tramos: [r for ini, fin in tramos for r in _rects_por_linea(p.cajas, ini, fin, p.girar)]  # noqa: E731
        return a_rects(mar), a_rects(sel)

    def buscar_n(self, terminos: Sequence[str], n: int = 0) -> tuple[Aparicion | None, int]:
        """La n-ésima aparición (en orden de lectura) y el total de apariciones."""
        conteos = self.conteo_por_pagina(terminos)
        total = sum(k for _, k in conteos)
        if not total:
            return None, 0
        n = max(0, min(n, total - 1))
        for i, k in conteos:
            if n < k:
                detalle = self.apariciones_en(i, terminos)
                if not detalle:  # el texto plano y el detallado no coincidieron: al menos la página
                    return Aparicion(i, ()), total
                return detalle[min(n, len(detalle) - 1)], total
            n -= k
        return None, total


# --- caché e imagen ---------------------------------------------------------------------


class CacheLRU:
    """Caché con límite de bytes: al pasarse, sale lo usado hace más tiempo."""

    def __init__(self, limite_bytes: int = CACHE_BYTES):
        self.limite = limite_bytes
        self.bytes = 0
        self._datos: OrderedDict[Any, tuple[Any, int]] = OrderedDict()

    def __len__(self) -> int:
        return len(self._datos)

    def __contains__(self, clave) -> bool:
        return clave in self._datos

    def get(self, clave):
        v = self._datos.get(clave)
        if v is None:
            return None
        self._datos.move_to_end(clave)
        return v[0]

    def put(self, clave, valor, tam: int) -> None:
        if clave in self._datos:
            self.bytes -= self._datos.pop(clave)[1]
        self._datos[clave] = (valor, tam)
        self.bytes += tam
        while self.bytes > self.limite and len(self._datos) > 1:
            _, (_, t) = self._datos.popitem(last=False)
            self.bytes -= t

    def clear(self) -> None:
        self._datos.clear()
        self.bytes = 0


def dibujar_pagina(pagina: pymupdf.Page, zoom: float) -> Image.Image:
    """La página a `zoom` píxeles por punto, sin transparencia (con anotaciones y formularios)."""
    pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False, annots=True)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def componer(base: Image.Image, tenues: Iterable, seleccionados: Iterable, zoom: float) -> Image.Image:
    """Pinta los resaltados sobre una copia de la página (multiplicando: la tinta sigue negra)."""
    tenues, seleccionados = list(tenues), list(seleccionados)
    if not tenues and not seleccionados:
        return base
    img = base.copy()
    holgura = max(1.0, zoom * 1.2)

    def caja(r):
        x0, y0 = max(0, int(r.x0 * zoom - holgura)), max(0, int(r.y0 * zoom - holgura * 0.5))
        x1, y1 = min(img.width, int(r.x1 * zoom + holgura + 1)), min(img.height, int(r.y1 * zoom + holgura * 0.5 + 1))
        return (x0, y0, x1, y1) if x1 > x0 and y1 > y0 else None

    def multiplicar(r, color):
        c = caja(r)
        if c is not None:
            region = img.crop(c)
            img.paste(ImageChops.multiply(region, Image.new("RGB", region.size, color)), c[:2])
        return c

    for r in tenues:
        multiplicar(r, MARCADO)
    lapiz = ImageDraw.Draw(img)
    grosor = max(1, round(zoom * 0.9))
    for r in seleccionados:
        c = multiplicar(r, SELECCION)
        if c is not None:
            lapiz.rectangle((c[0], c[1], c[2] - 1, c[3] - 1), outline=BORDE_SELECCION, width=grosor)
    return img


@dataclass
class Disposicion:
    """Dónde va cada página en el lienzo, en píxeles, para un zoom dado."""

    tamanos: list[tuple[float, float]]  # (ancho, alto) en puntos
    zoom: float
    ancho_vista: int = 0

    def __post_init__(self):
        self.tops: list[int] = []
        y = MARGEN
        for _, h in self.tamanos:
            self.tops.append(y)
            y += round(h * self.zoom) + SEPARACION
        self.alto = y - SEPARACION + MARGEN if self.tamanos else 0
        mas_ancha = max((round(w * self.zoom) for w, _ in self.tamanos), default=0)
        self.ancho = max(self.ancho_vista, mas_ancha + 2 * MARGEN)

    def caja(self, i: int) -> tuple[int, int, int, int]:
        w, h = self.tamanos[i]
        pw, ph = round(w * self.zoom), round(h * self.zoom)
        x = (self.ancho - pw) // 2
        return x, self.tops[i], x + pw, self.tops[i] + ph

    def pagina_en(self, y: float) -> int:
        """Página que ocupa (o la última que empezó antes de) la altura `y`."""
        return max(0, min(len(self.tops) - 1, bisect.bisect_right(self.tops, y) - 1))

    def visibles(self, y0: float, y1: float, margen: int = 1) -> list[int]:
        if not self.tamanos:
            return []
        a, b = self.pagina_en(y0), self.pagina_en(y1)
        return list(range(max(0, a - margen), min(len(self.tamanos), b + margen + 1)))


def zoom_para_ancho(tamanos: Sequence[tuple[float, float]], ancho_vista: int) -> float:
    """Píxeles por punto para que la página más ancha llene el ancho de la vista."""
    mas_ancha = max((w for w, _ in tamanos), default=0)
    if mas_ancha <= 0 or ancho_vista <= 2 * MARGEN:
        return 1.0
    return (ancho_vista - 2 * MARGEN) / mas_ancha


# --- el componente ----------------------------------------------------------------------


class VisorDocumento(ctk.CTkFrame):
    """Visor embebible. API: cargar, cargar_texto, resaltar, ir_a, ir_a_posicion, ir_a_pagina, cerrar."""

    def __init__(self, master, **kw):
        kw.setdefault("fg_color", "transparent")
        super().__init__(master, **kw)
        self._doc: pymupdf.Document | None = None
        self._propio = False  # True si lo abrió el visor (y entonces lo cierra él)
        self._texto: TextoPDF | None = None
        self._modo: str | None = None  # "pdf" | "texto" | None
        self._tamanos: list[tuple[float, float]] = []
        self._disp: Disposicion | None = None
        self._zoom = 1.0  # píxeles por punto
        self._ajustar = True
        self._cache = CacheLRU()
        self._fotos: dict[int, ImageTk.PhotoImage] = {}
        self._items: dict[int, int] = {}  # página → id de la imagen en el lienzo
        self._version = 0  # sube con cada resaltar(); invalida lo ya compuesto
        self._mostradas: dict[int, tuple] = {}  # página → (zoom, versión) de lo que se ve
        self._resaltes: dict[int, tuple] = {}  # página → rects (tenues, seleccionados), por versión
        self._marcados: list[str] = []
        self._seleccionados: list[str] = []
        self._tarea = None
        self._tarea_indice = None
        self._tarea_ajuste = None
        self._ancho_previo = 0
        self._tam_letra = 13
        self._texto_plano = ""
        self._plegado = ""
        self._cajas: Sequence | None = None  # la capa de texto que se pasó a cargar(), si coincide

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._barra()
        self._zona = ctk.CTkFrame(self, fg_color=FONDO, corner_radius=8)
        self._zona.grid(row=1, column=0, sticky="nsew")
        self._zona.grid_columnconfigure(0, weight=1)
        self._zona.grid_rowconfigure(0, weight=1)

        self.lienzo = tk.Canvas(self._zona, highlightthickness=0, bd=0, yscrollincrement=20, xscrollincrement=20,
                                bg=self._apply_appearance_mode(FONDO), takefocus=1)
        self._barra_v = ctk.CTkScrollbar(self._zona, orientation="vertical", command=self.lienzo.yview)
        self._barra_h = ctk.CTkScrollbar(self._zona, orientation="horizontal", command=self.lienzo.xview)
        self.lienzo.configure(yscrollcommand=self._al_desplazar_y, xscrollcommand=self._al_desplazar_x)
        self.lienzo.bind("<Configure>", self._al_redimensionar)
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<Shift-MouseWheel>",
                   "<Control-MouseWheel>", "<Command-MouseWheel>" if sys.platform == "darwin" else "<Control-Button-4>",
                   "<Control-Button-5>"):
            try:
                self.lienzo.bind(ev, self._rueda)
            except tk.TclError:
                pass
        self.lienzo.bind("<Button-1>", lambda _e: self.lienzo.focus_set())
        for tecla, accion in (("<Prior>", lambda: self._paso_pagina(-1)), ("<Next>", lambda: self._paso_pagina(1)),
                              ("<Up>", lambda: self.lienzo.yview_scroll(-2, "units")),
                              ("<Down>", lambda: self.lienzo.yview_scroll(2, "units")),
                              ("<Home>", lambda: self.ir_a_pagina(1)),
                              ("<End>", lambda: self.ir_a_pagina(len(self._tamanos)))):
            self.lienzo.bind(tecla, lambda _e, a=accion: (a(), "break")[1])

        self.cuadro = ctk.CTkTextbox(self._zona, wrap="word", font=ctk.CTkFont(size=self._tam_letra),
                                     corner_radius=6, border_spacing=14)
        self.cuadro._textbox.configure(spacing3=5)  # aire entre párrafos
        self._colorear_etiquetas()
        self.cuadro.configure(state="disabled")
        self._aviso = ctk.CTkLabel(self._zona, text=tr('Sin documento'), text_color=TEXTO_TENUE,
                                   font=ctk.CTkFont(size=13))
        self._mostrar_vacio(tr('Sin documento'))

    # --- barra ----------------------------------------------------------------------------

    def _barra(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew", pady=(0, 6))
        barra.grid_columnconfigure(0, weight=1)
        fuente = ctk.CTkFont(size=12)
        boton = dict(width=28, height=26, fg_color="transparent", text_color=("gray20", "gray85"),
                     hover_color=("gray85", "gray25"), font=ctk.CTkFont(size=15), corner_radius=6)
        self._nombre = ctk.CTkLabel(barra, text="", font=fuente, text_color=TEXTO_TENUE, anchor="w")
        self._nombre.grid(row=0, column=0, sticky="ew", padx=(2, 8))

        self._grupo_pag = ctk.CTkFrame(barra, fg_color="transparent")
        self._grupo_pag.grid(row=0, column=1, padx=(0, 10))
        ctk.CTkButton(self._grupo_pag, text="‹", command=lambda: self._paso_pagina(-1), **boton).pack(side="left")
        self._entrada_pag = ctk.CTkEntry(self._grupo_pag, width=40, height=26, font=fuente, justify="center",
                                         border_width=1)
        self._entrada_pag.pack(side="left", padx=2)
        self._entrada_pag.bind("<Return>", self._pagina_tecleada)
        self._total_pag = ctk.CTkLabel(self._grupo_pag, text="de 0", font=fuente, text_color=TEXTO_TENUE)
        self._total_pag.pack(side="left", padx=(2, 2))
        ctk.CTkButton(self._grupo_pag, text="›", command=lambda: self._paso_pagina(1), **boton).pack(side="left")

        self._grupo_zoom = ctk.CTkFrame(barra, fg_color="transparent")
        self._grupo_zoom.grid(row=0, column=2)
        ctk.CTkButton(self._grupo_zoom, text="−", command=lambda: self.zoom(1 / PASO_ZOOM), **boton).pack(side="left")
        self._etiqueta_zoom = ctk.CTkLabel(self._grupo_zoom, text="100 %", width=46, font=fuente)
        self._etiqueta_zoom.pack(side="left")
        ctk.CTkButton(self._grupo_zoom, text="+", command=lambda: self.zoom(PASO_ZOOM), **boton).pack(side="left")
        self._boton_ajustar = ctk.CTkButton(
            self._grupo_zoom, text=tr('Ajustar'), width=64, height=26, font=fuente, command=self.ajustar,
            fg_color="transparent", border_width=1, text_color=("gray20", "gray85"),
            border_color=("gray65", "gray40"), hover_color=("gray85", "gray25"), corner_radius=6)
        self._boton_ajustar.pack(side="left", padx=(6, 0))

    def _actualizar_barra(self):
        n = len(self._tamanos)
        self._total_pag.configure(text=f"de {n}")
        self._entrada_pag.delete(0, "end")
        if n:
            self._entrada_pag.insert(0, str(self.pagina_actual))
        if self._modo == "pdf":
            self._etiqueta_zoom.configure(text=f"{round(self._zoom / self._px_por_punto() * 100)} %")
        elif self._modo == "texto":
            self._etiqueta_zoom.configure(text=f"{round(self._tam_letra / 13 * 100)} %")
        self._boton_ajustar.configure(border_color=ACENTO if self._ajustar and self._modo == "pdf"
                                      else ("gray65", "gray40"))

    # --- carga ----------------------------------------------------------------------------

    def cargar(self, fuente: str | Path | pymupdf.Document, *, texto: str | None = None,
               cajas: Sequence | None = None) -> bool:
        """Abre un PDF (ruta o `pymupdf.Document` ya abierto). Devuelve False si no se pudo.

        `texto` + `cajas` (opcionales): la capa de texto que ya extrajo el procesador
        (`DocumentoPDF.texto` y su lista de caracteres con `.pagina` y `.rect`); con ella el
        resaltado coincide con el detector y funciona en páginas leídas con OCR.
        Un documento ya abierto se usa (en el hilo de Tk) y no se cierra al cambiar de archivo.
        """
        self.cerrar()
        nombre = ""
        try:
            if isinstance(fuente, pymupdf.Document):
                doc, self._propio = fuente, False
                nombre = Path(fuente.name).name if fuente.name else ""
            else:
                nombre = Path(fuente).name
                doc, self._propio = pymupdf.open(str(fuente)), True
            if doc.needs_pass:
                if self._propio:
                    doc.close()
                self._mostrar_vacio(tr('El documento está protegido con contraseña'))
                return False
        except Exception:
            self._mostrar_vacio(tr('No se pudo abrir el documento'))
            return False
        self._doc = doc
        self._modo = "pdf"
        self._texto = TextoPDF(doc, texto, cajas)
        self._cajas = cajas if texto is not None and cajas is not None and len(texto) == len(cajas) else None
        self._tamanos = [(p.rect.width, p.rect.height) for p in doc]
        self._nombre.configure(text=nombre)
        self._ajustar = True
        self._mostrar_lienzo()
        self.update_idletasks()
        self._zoom = self._zoom_ajustado()
        self._ancho_previo = self.lienzo.winfo_width()
        self._disponer(conservar=False)
        self._tarea_indice = self.after(250, self._indexar)  # primero, que se vea la página
        return True

    def cargar_texto(self, texto: str, nombre: str = "") -> None:
        """Modo texto (.docx/.doc): el texto ya extraído, de solo lectura, con el mismo resaltado."""
        self.cerrar()
        self._modo = "texto"
        self._texto_plano = texto
        self._plegado = plegar(texto)
        self._nombre.configure(text=nombre)
        self.cuadro.configure(state="normal")
        self.cuadro.delete("1.0", "end")
        self.cuadro.insert("1.0", texto)
        self.cuadro.configure(state="disabled")
        self.cuadro.yview_moveto(0)
        self._mostrar_cuadro()
        self._pintar_texto()
        self._actualizar_barra()

    def cerrar(self) -> None:
        """Suelta el documento, las imágenes y la caché (se llama solo al cargar otro)."""
        for t in (self._tarea, self._tarea_indice, self._tarea_ajuste):
            if t is not None:
                self.after_cancel(t)
        self._tarea = self._tarea_indice = self._tarea_ajuste = None
        self.lienzo.delete("all")
        self._fotos.clear()
        self._items.clear()
        self._mostradas.clear()
        self._resaltes.clear()
        self._cache.clear()
        if self._doc is not None and self._propio:
            self._doc.close()
            pymupdf.TOOLS.store_shrink(100)  # fuentes e imágenes que MuPDF guardaba de ese PDF
        self._doc = None
        self._texto = None
        self._tamanos = []
        self._disp = None
        self._modo = None
        self._texto_plano = ""
        self._plegado = ""
        self._cajas = None
        self.cuadro.configure(state="normal")
        self.cuadro.delete("1.0", "end")
        self.cuadro.configure(state="disabled")
        self._nombre.configure(text="")
        self._mostrar_vacio(tr('Sin documento'))

    def destroy(self):
        self.cerrar()
        super().destroy()

    def _mostrar_vacio(self, mensaje: str):
        self.lienzo.grid_remove()
        self._barra_v.grid_remove()
        self._barra_h.grid_remove()
        self.cuadro.grid_remove()
        self._aviso.configure(text=mensaje)
        self._aviso.grid(row=0, column=0)
        self._grupo_pag.grid_remove()
        self._grupo_zoom.grid_remove()

    def _mostrar_lienzo(self):
        self._aviso.grid_remove()
        self.cuadro.grid_remove()
        self.lienzo.grid(row=0, column=0, sticky="nsew")
        self._barra_v.grid(row=0, column=1, sticky="ns", padx=(0, 2), pady=4)
        self._grupo_pag.grid()
        self._grupo_zoom.grid()

    def _mostrar_cuadro(self):
        self._aviso.grid_remove()
        self.lienzo.grid_remove()
        self._barra_v.grid_remove()
        self._barra_h.grid_remove()
        self.cuadro.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        self._grupo_pag.grid_remove()
        self._grupo_zoom.grid()

    def _indexar(self):
        """Texto plano de todo el PDF, en tandas, para que `ir_a` no tenga que esperar."""
        self._tarea_indice = None
        if self._texto is None:
            return
        if self._tarea is not None:  # hay páginas por dibujar: tienen prioridad
            self._tarea_indice = self.after(30, self._indexar)
        elif not self._texto.indexar(INDEXAR_POR_VUELTA):
            self._tarea_indice = self.after(1, self._indexar)

    # --- propiedades ----------------------------------------------------------------------

    @property
    def modo(self) -> str | None:
        return self._modo

    @property
    def num_paginas(self) -> int:
        return len(self._tamanos)

    @property
    def pagina_actual(self) -> int:
        """1-based: la página que ocupa el centro de la vista."""
        if self._disp is None:
            return 0
        y = self.lienzo.canvasy(0) + self.lienzo.winfo_height() / 2
        return self._disp.pagina_en(y) + 1

    # --- zoom y disposición ---------------------------------------------------------------

    def _px_por_punto(self) -> float:
        """Píxeles por punto al 100 % (tamaño real en esta pantalla)."""
        try:
            return self.winfo_fpixels("1i") / 72.0
        except tk.TclError:
            return 1.0

    def _zoom_ajustado(self) -> float:
        ancho = max(self.lienzo.winfo_width(), 50)
        z = zoom_para_ancho(self._tamanos, ancho - 2)
        base = self._px_por_punto()
        return max(ZOOM_MIN * base, min(ZOOM_MAX * base, z))

    def zoom(self, factor: float) -> None:
        if self._modo == "texto":
            self._tam_letra = max(8, min(40, round(self._tam_letra * factor)))
            self.cuadro.configure(font=ctk.CTkFont(size=self._tam_letra))
            self._actualizar_barra()
            return
        if self._modo != "pdf":
            return
        base = self._px_por_punto()
        nuevo = max(ZOOM_MIN * base, min(ZOOM_MAX * base, self._zoom * factor))
        if abs(nuevo - self._zoom) < 1e-6:
            return
        self._ajustar = False
        self._zoom = nuevo
        self._disponer()

    def ajustar(self) -> None:
        """Ajusta al ancho del panel (y lo mantiene al cambiar el tamaño de la ventana)."""
        if self._modo == "texto":
            self._tam_letra = 13
            self.cuadro.configure(font=ctk.CTkFont(size=self._tam_letra))
            self._actualizar_barra()
            return
        if self._modo != "pdf":
            return
        self._ajustar = True
        self._zoom = self._zoom_ajustado()
        self._disponer()

    def _disponer(self, conservar: bool = True):
        """Rehace la disposición (zoom o ancho nuevos) conservando el punto de lectura."""
        ancla = None
        centro_x = None
        if conservar and self._disp is not None and self._disp.ancho > 0:
            a, b = self.lienzo.xview()
            centro_x = (a + b) / 2
        if conservar and self._disp is not None:
            y = self.lienzo.canvasy(0)
            i = self._disp.pagina_en(y)
            alto = max(1, self._disp.caja(i)[3] - self._disp.tops[i])
            ancla = (i, (y - self._disp.tops[i]) / alto)
        self._disp = Disposicion(self._tamanos, self._zoom, self.lienzo.winfo_width())
        self.lienzo.delete("all")
        self._fotos.clear()
        self._items.clear()
        self._mostradas.clear()
        cerca, lejos = SOMBRA[self._modo_oscuro()]
        for i in range(len(self._tamanos)):
            x0, y0, x1, y1 = self._disp.caja(i)
            self.lienzo.create_rectangle(x0 - 1, y0, x1 + 3, y1 + 4, fill=lejos, outline="", tags="sombra_lejana")
            self.lienzo.create_rectangle(x0, y0, x1 + 1, y1 + 2, fill=cerca, outline="", tags="sombra")
            self.lienzo.create_rectangle(x0, y0, x1, y1, fill="white", outline="", tags="hoja")
        self.lienzo.configure(scrollregion=(0, 0, self._disp.ancho, self._disp.alto))
        if ancla is not None:
            i, f = ancla
            y = self._disp.tops[i] + f * (self._disp.caja(i)[3] - self._disp.tops[i])
            self.lienzo.yview_moveto(y / max(1, self._disp.alto))
        elif not conservar:
            self.lienzo.yview_moveto(0)
        self._mostrar_barra_h()
        if centro_x is not None and self._disp.ancho > self.lienzo.winfo_width():
            mitad = self.lienzo.winfo_width() / 2 / self._disp.ancho
            self.lienzo.xview_moveto(max(0.0, centro_x - mitad))
        self._actualizar_barra()
        self._programar()

    def _mostrar_barra_h(self):
        if self._disp is not None and self._disp.ancho > self.lienzo.winfo_width() + 1:
            self._barra_h.grid(row=1, column=0, sticky="ew", padx=4, pady=(0, 2))
        else:
            self._barra_h.grid_remove()
            self.lienzo.xview_moveto(0)

    def _al_redimensionar(self, evento):
        if self._modo != "pdf" or evento.width == self._ancho_previo:
            return
        self._ancho_previo = evento.width
        if self._tarea_ajuste is not None:
            self.after_cancel(self._tarea_ajuste)
        self._tarea_ajuste = self.after(120, self._reajustar)

    def _reajustar(self):
        self._tarea_ajuste = None
        if self._modo != "pdf":
            return
        if self._ajustar:
            self._zoom = self._zoom_ajustado()
        self._disponer()

    # --- desplazamiento -------------------------------------------------------------------

    def _al_desplazar_y(self, a, b):
        self._barra_v.set(a, b)
        if self._modo == "pdf":
            self._entrada_pag_sin_foco()
            self._programar()

    def _al_desplazar_x(self, a, b):
        self._barra_h.set(a, b)
        if self._modo == "pdf":
            self._programar()

    def _entrada_pag_sin_foco(self):
        if self.focus_get() is not self._entrada_pag._entry:
            self._entrada_pag.delete(0, "end")
            self._entrada_pag.insert(0, str(self.pagina_actual))

    def _rueda(self, e):
        if self._modo != "pdf":
            return None
        if e.num == 4:
            d = -1.0
        elif e.num == 5:
            d = 1.0
        elif sys.platform == "win32":
            d = -e.delta / 120
        else:
            d = -float(e.delta)
        if e.state & 0x0004 or (sys.platform == "darwin" and e.state & 0x0008):  # Control / Command
            self.zoom(PASO_ZOOM if d < 0 else 1 / PASO_ZOOM)
            return "break"
        pasos = int(round(d * 3)) or (1 if d > 0 else -1)
        if e.state & 0x0001:  # Shift: horizontal
            self.lienzo.xview_scroll(pasos, "units")
        else:
            self.lienzo.yview_scroll(pasos, "units")
        return "break"

    def _paso_pagina(self, delta: int):
        self.ir_a_pagina(self.pagina_actual + delta)

    def _pagina_tecleada(self, _e=None):
        try:
            n = int(self._entrada_pag.get().strip())
        except ValueError:
            n = self.pagina_actual
        self.ir_a_pagina(n)
        self.lienzo.focus_set()

    def ir_a_pagina(self, numero: int) -> None:
        """Lleva el inicio de la página `numero` (1-based) arriba de la vista."""
        if self._disp is None or not self._tamanos:
            return
        i = max(0, min(len(self._tamanos) - 1, numero - 1))
        y = self._disp.tops[i] - SEPARACION // 2
        self.lienzo.yview_moveto(max(0, y) / max(1, self._disp.alto))
        self._actualizar_barra()

    def _centrar(self, pagina: int, rect: pymupdf.Rect | None):
        d = self._disp
        x0, y0, x1, y1 = d.caja(pagina)
        if rect is None:
            cy, cx = y0 + (y1 - y0) / 2, x0 + (x1 - x0) / 2
        else:
            cy, cx = y0 + (rect.y0 + rect.y1) / 2 * self._zoom, x0 + (rect.x0 + rect.x1) / 2 * self._zoom
        alto, ancho = self.lienzo.winfo_height(), self.lienzo.winfo_width()
        self.lienzo.yview_moveto(max(0.0, cy - alto / 2) / max(1, d.alto))
        if d.ancho > ancho:
            self.lienzo.xview_moveto(max(0.0, cx - ancho / 2) / max(1, d.ancho))
        self._actualizar_barra()

    # --- dibujo perezoso ------------------------------------------------------------------

    def _visibles(self, margen: int = 1) -> list[int]:
        if self._disp is None:
            return []
        y0 = self.lienzo.canvasy(0)
        return self._disp.visibles(y0, y0 + max(1, self.lienzo.winfo_height()), margen)

    def _programar(self):
        if self._tarea is None and self._modo == "pdf":
            self._tarea = self.after(1, self._trabajar)

    def _trabajar(self):
        """Dibuja UNA página pendiente (la más cercana al centro) y se vuelve a programar."""
        self._tarea = None
        if self._modo != "pdf" or self._disp is None:
            return
        visibles = self._visibles(margen=1)
        conservar = set(self._visibles(margen=2))
        for i in [i for i in self._fotos if i not in conservar]:
            self.lienzo.delete(self._items.pop(i))
            del self._fotos[i]
            self._mostradas.pop(i, None)
        centro = self._disp.pagina_en(self.lienzo.canvasy(0) + self.lienzo.winfo_height() / 2)
        estado = (round(self._zoom, 4), self._version)
        for i in sorted(visibles, key=lambda i: abs(i - centro)):
            if self._mostradas.get(i) != estado:
                self._dibujar(i, estado)
                self._tarea = self.after(1, self._trabajar)
                return

    def _base(self, i: int) -> Image.Image:
        clave = (i, round(self._zoom, 4))
        img = self._cache.get(clave)
        if img is None:
            img = dibujar_pagina(self._doc[i], self._zoom)
            self._cache.put(clave, img, img.width * img.height * 3)
        return img

    def _dibujar(self, i: int, estado: tuple):
        base = self._base(i)
        tenues, sel = self._resaltes_de(i)
        foto = ImageTk.PhotoImage(componer(base, tenues, sel, self._zoom))
        x0, y0, _, _ = self._disp.caja(i)
        if i in self._items:
            self.lienzo.itemconfigure(self._items[i], image=foto)
        else:
            self._items[i] = self.lienzo.create_image(x0, y0, image=foto, anchor="nw", tags="pagina")
        self._fotos[i] = foto  # Tk no guarda la referencia: sin esto la imagen desaparece
        self._mostradas[i] = estado

    def _resaltes_de(self, i: int):
        if not self._marcados and not self._seleccionados:
            return [], []
        guardado = self._resaltes.get(i)
        if guardado is None or guardado[0] != self._version:
            guardado = (self._version, *self._texto.resaltados_en(i, self._marcados, self._seleccionados))
            self._resaltes[i] = guardado
        return guardado[1], guardado[2]

    # --- resaltado y saltos ---------------------------------------------------------------

    def resaltar(self, terminos_marcados: Iterable[str], seleccionados: Iterable[str] = ()) -> None:
        """Pinta lo marcado en tono tenue y lo seleccionado en dorado con borde.

        Pasa las variantes tal como aparecen (p. ej. `Entidad.todas_las_variantes()`);
        se buscan sin distinguir mayúsculas ni acentos y aunque crucen de renglón.
        """
        self._marcados = [t for t in dict.fromkeys(terminos_marcados) if t and t.strip()]
        self._seleccionados = [t for t in dict.fromkeys(seleccionados) if t and t.strip()]
        self._version += 1
        self._resaltes.clear()
        if self._modo == "pdf":
            self._programar()
        elif self._modo == "texto":
            self._pintar_texto()

    def ir_a(self, termino: str | Iterable[str], n: int = 0) -> int:
        """Salta a la n-ésima aparición (0-based, se acota) y la centra. Devuelve cuántas hay."""
        terminos = [termino] if isinstance(termino, str) else list(termino)
        terminos = [t for t in terminos if t and t.strip()]
        if not terminos:
            return 0
        if self._modo == "texto":
            tramos = buscar(self._texto_plano, terminos, plegado=self._plegado)
            if tramos:
                ini, _ = tramos[max(0, min(n, len(tramos) - 1))]
                self._centrar_texto(f"1.0+{ini}c")
            return len(tramos)
        if self._modo != "pdf":
            return 0
        aparicion, total = self._texto.buscar_n(terminos, n)
        if aparicion is not None:
            self._centrar(aparicion.pagina, _unir(aparicion.rects))
        return total

    def ir_a_posicion(self, inicio: int, fin: int) -> bool:
        """Centra el tramo [inicio, fin) del texto con que se cargó (el de `cargar_texto`, o el
        `texto` de `cargar` con su capa). Exacto aunque el dato se repita. False si no se puede
        ubicar así (PDF abierto sin capa): entonces queda `ir_a`."""
        if self._modo == "texto":
            if not 0 <= inicio < max(1, len(self._texto_plano)):
                return False
            self._centrar_texto(f"1.0+{inicio}c")
            return True
        if self._modo != "pdf" or self._cajas is None or self._disp is None:
            return False
        doc = self._doc
        lugar = tramo_en_capa(self._cajas, inicio, fin,
                              lambda i: doc[i].rotation_matrix if doc[i].rotation else None)
        if lugar is None or not 0 <= lugar[0] < len(self._tamanos):
            return False
        self._centrar(lugar[0], _unir(lugar[1]))
        return True

    # --- modo texto -----------------------------------------------------------------------

    def _modo_oscuro(self) -> int:
        return 1 if ctk.get_appearance_mode() == "Dark" else 0

    def _colorear_etiquetas(self):
        m = self._modo_oscuro()
        fondo, letra = TEXTO_MARCADO[m]
        self.cuadro.tag_config("marcado", background=fondo, foreground=letra)
        fondo, letra = TEXTO_SELECCION[m]
        self.cuadro.tag_config("seleccion", background=fondo, foreground=letra, relief="solid", borderwidth=1)
        self.cuadro.tag_raise("seleccion")

    def _pintar_texto(self):
        self.cuadro.tag_remove("marcado", "1.0", "end")
        self.cuadro.tag_remove("seleccion", "1.0", "end")
        if not self._texto_plano:
            return
        sel = buscar(self._texto_plano, self._seleccionados, plegado=self._plegado) if self._seleccionados else []
        mar = buscar(self._texto_plano, self._marcados, plegado=self._plegado) if self._marcados else []
        for etiqueta, tramos in (("marcado", _quitar_traslapes(mar, sel)), ("seleccion", sel)):
            for ini, fin in tramos:
                self.cuadro.tag_add(etiqueta, f"1.0+{ini}c", f"1.0+{fin}c")

    def _centrar_texto(self, indice: str):
        caja = self.cuadro._textbox
        caja.see(indice)
        self.update_idletasks()
        try:
            hasta = caja.count("1.0", indice, "ypixels")
            total = caja.count("1.0", "end", "ypixels")
            hasta = hasta[0] if isinstance(hasta, tuple) else (hasta or 0)
            total = total[0] if isinstance(total, tuple) else (total or 0)
            if total:
                caja.yview_moveto(max(0.0, hasta - caja.winfo_height() / 2) / total)
        except tk.TclError:
            pass
        # Recién mostrado el cuadro, Tk aún no mide todos los renglones y la cuenta sale corta:
        # entonces basta con que se vea.
        if caja.bbox(indice) is None:
            caja.see(indice)

    # --- claro/oscuro ---------------------------------------------------------------------

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)
        try:
            self.lienzo.configure(bg=self._apply_appearance_mode(FONDO))
            cerca, lejos = SOMBRA[self._modo_oscuro()]
            self.lienzo.itemconfigure("sombra", fill=cerca)
            self.lienzo.itemconfigure("sombra_lejana", fill=lejos)
            self._colorear_etiquetas()
        except (AttributeError, tk.TclError):  # todavía construyéndose
            pass


def _unir(rects) -> pymupdf.Rect | None:
    if not rects:
        return None
    r = pymupdf.Rect(rects[0])
    for x in rects[1:]:
        r |= x
    return r


# --- demo: python -m anonimizador.ui.visor <archivo> [término …] ------------------------------


def _demo(argv: list[str]) -> None:
    import argparse

    ap = argparse.ArgumentParser(prog="python -m anonimizador.ui.visor", description="Visor de documento (demo).")
    ap.add_argument("archivo")
    ap.add_argument("terminos", nargs="*", help="datos a resaltar; el primero se marca como seleccionado")
    ap.add_argument("--n", type=int, default=0, help="aparición del primer término a la que saltar")
    ap.add_argument("--modo", choices=["claro", "oscuro", "sistema"], default="sistema")
    a = ap.parse_args(argv)

    ctk.set_appearance_mode({"claro": "light", "oscuro": "dark", "sistema": "system"}[a.modo])
    raiz = ctk.CTk()
    raiz.title(f"Visor · {Path(a.archivo).name}")
    raiz.geometry("760x900")
    visor = VisorDocumento(raiz)
    visor.pack(fill="both", expand=True, padx=16, pady=16)
    ruta = Path(a.archivo)
    if ruta.suffix.lower() == ".pdf":
        visor.cargar(ruta)
    else:
        from ..procesadores import abrir

        visor.cargar_texto(abrir(ruta).texto, ruta.name)
    if a.terminos:
        visor.resaltar(a.terminos, a.terminos[:1])
        raiz.after(300, lambda: print(f"«{a.terminos[0]}»: {visor.ir_a(a.terminos[0], a.n)} apariciones", flush=True))
    raiz.mainloop()


if __name__ == "__main__":
    _demo(sys.argv[1:])
