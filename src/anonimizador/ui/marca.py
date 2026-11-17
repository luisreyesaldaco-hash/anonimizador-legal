"""Encabezado «LEGAL ATLAS | ANONIMIZADOR» dibujado en vectores.

Una imagen en Tk se pinta a la resolución de puntos (1x): en una pantalla Retina, o en Windows
con escala, el PNG sale borroso. Aquí el texto se dibuja con la letra real del imagotipo
(Cormorant Garamond 600, empaquetada en `recursos/`, licencia OFL) y el triángulo con polígonos,
así que se ve nítido a cualquier densidad. Medidas y colores: los de `packaging/marca/logo-*.svg`.
"""

from __future__ import annotations

import ctypes
import math
import sys
import tkinter.font as tkfont
from pathlib import Path

import customtkinter as ctk
from customtkinter.windows.widgets.core_rendering import CTkCanvas

RECURSOS = Path(__file__).parent / "recursos"
ARCHIVO_FUENTE = RECURSOS / "CormorantGaramond-SemiBold.ttf"
FAMILIA_MARCA = "Cormorant Garamond SemiBold"
ALTURA_MAYUSCULA = 0.625  # sCapHeight / unitsPerEm de la fuente

# Geometría del lockup en unidades del SVG (el bloque de contenido mide 150 de alto).
_ALTO_SVG = 150.0
_TRIANGULO_ANCHO = 176.47058823529412
_SEP1_X = 216.47058823529412
_TEXTO1_X = 258.0705882352941
_HUECO_ANTES_SEP = _SEP1_X - _TRIANGULO_ANCHO  # 40: del fin de un texto a la línea
_HUECO_DESPUES_SEP = _TEXTO1_X - _SEP1_X  # 41.6: de la línea al texto
_SEP_ANCHO, _SEP_Y0, _SEP_Y1, _SEP_OPACIDAD = 1.6, 25.0, 125.0, 0.30
_TAMANO, _ESPACIADO = 82.0, 7.0
# Triángulo: viewBox "10 14 80 68" dentro de 176.47 × 150.
_TRI = [((50, 16), (12, 80), (88, 80), "cara"), ((50, 16), (12, 80), (50, 80), "luz"),
        ((50, 16), (88, 80), (50, 80), "cara"), ((12, 80), (50, 71), (88, 80), "base")]
COLORES = {  # (claro, oscuro)
    "texto": ("#22211e", "#f2efe7"),
    "cara": ("#22211e", "#f2efe7"),
    "luz": ("#565550", "#d8d3c6"),
    "base": ("#b68235", "#b68235"),
}

_registrada: bool | None = None


def registrar_fuente() -> bool:
    """Registra la fuente del imagotipo solo para este proceso. Llamar ANTES de crear la ventana."""
    global _registrada
    if _registrada is not None:
        return _registrada
    _registrada = False
    if not ARCHIVO_FUENTE.exists():
        return False
    ruta = str(ARCHIVO_FUENTE)
    try:
        if sys.platform.startswith("win"):
            gdi32 = ctypes.WinDLL("gdi32")
            gdi32.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint32, ctypes.c_void_p]
            gdi32.AddFontResourceExW.restype = ctypes.c_int
            FR_PRIVATE = 0x10
            _registrada = gdi32.AddFontResourceExW(ruta, FR_PRIVATE, None) > 0
        elif sys.platform == "darwin":
            cf = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            ct = ctypes.cdll.LoadLibrary("/System/Library/Frameworks/CoreText.framework/CoreText")
            cf.CFURLCreateFromFileSystemRepresentation.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                                                   ctypes.c_long, ctypes.c_bool]
            cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
            cf.CFRelease.argtypes = [ctypes.c_void_p]
            ct.CTFontManagerRegisterFontsForURL.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p]
            ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            datos = ruta.encode("utf-8")
            url = cf.CFURLCreateFromFileSystemRepresentation(None, datos, len(datos), False)
            if url:
                kCTFontManagerScopeProcess = 1
                _registrada = bool(ct.CTFontManagerRegisterFontsForURL(url, kCTFontManagerScopeProcess, None))
                cf.CFRelease(url)
        else:
            _registrada = bool(ctk.FontManager.load_font(ruta))
    except Exception:  # sin la fuente queda el PNG
        _registrada = False
    return _registrada


def fuente_disponible(raiz) -> bool:
    """Tk de verdad usa la fuente (no una sustituta). En Mac, si ya estaba registrada, también vale."""
    registrar_fuente()
    try:
        real = tkfont.Font(root=raiz, family=FAMILIA_MARCA, size=-20).actual("family")
    except Exception:
        return False
    return real.lower() == FAMILIA_MARCA.lower()


def _mezclar(color: str, fondo: str, opacidad: float, widget) -> str:
    """Color con opacidad sobre un fondo opaco (Tk no tiene transparencia)."""
    (r1, g1, b1), (r2, g2, b2) = widget.winfo_rgb(color), widget.winfo_rgb(fondo)
    m = lambda a, b: round((a * opacidad + b * (1 - opacidad)) / 257)  # noqa: E731
    return f"#{m(r1, r2):02x}{m(g1, g2):02x}{m(b1, b2):02x}"


_MEDIDA = 1000  # tamaño, en píxeles, al que se miden los avances de cada letra


def _avance(medidor, letra: str, siguiente: str) -> int:
    """Avance de `letra` con el interletraje (kerning) respecto de la que sigue, si Tk lo aplica."""
    if not siguiente or siguiente == " ":
        return medidor.measure(letra)
    return medidor.measure(letra + siguiente) - medidor.measure(siguiente)


def _hex(color: str, widget) -> str:
    """Cualquier color de Tk («gray92», «#fff»…) como #rrggbb, para PIL."""
    r, g, b = (v // 257 for v in widget.winfo_rgb(color))
    return f"#{r:02x}{g:02x}{b:02x}"


class Logotipo(ctk.CTkFrame):
    """El lockup completo (triángulo | LEGAL ATLAS | ANONIMIZADOR) en un Canvas.

    `alto` es la altura del bloque en puntos (sin escalar); el ancho sale del texto.
    """

    def __init__(self, master, alto: int = 30, textos=("LEGAL ATLAS", "ANONIMIZADOR"), **kw):
        super().__init__(master, fg_color="transparent", corner_radius=0, border_width=0,
                         width=10, height=alto, **kw)
        self._alto = alto
        self._textos = textos
        self._lienzo = CTkCanvas(self, highlightthickness=0, borderwidth=0)
        self._lienzo.place(x=0, y=0, relwidth=1, relheight=1)
        self._imagen_tri = None
        self._pintar()

    # CTkFrame llama a _draw al cambiar modo claro/oscuro o escala.
    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        if hasattr(self, "_lienzo"):
            self._pintar()

    def _pintar(self):
        c = self._lienzo
        c.delete("all")
        s = self._get_widget_scaling()
        k = self._alto * s / _ALTO_SVG  # píxeles de pantalla por unidad del SVG
        fondo = self._apply_appearance_mode(self._bg_color)
        c.configure(bg=fondo)
        col = {n: self._apply_appearance_mode(v) for n, v in COLORES.items()}

        self._triangulo(c, k, col, fondo)

        fuente_px = max(1, round(_TAMANO * k))
        fuente = tkfont.Font(root=self, family=FAMILIA_MARCA, size=-fuente_px)
        # Los avances se miden en grande: a 16 px el redondeo a enteros de cada letra se acumula.
        medidor = tkfont.Font(root=self, family=FAMILIA_MARCA, size=-_MEDIDA)
        bajada = fuente.metrics("descent")
        linea_base = 75 * k + ALTURA_MAYUSCULA * _TAMANO * k / 2
        sep = _mezclar(col["texto"], fondo, _SEP_OPACIDAD, self)
        grosor = max(1.0, _SEP_ANCHO * k) if sys.platform == "darwin" else max(1, round(_SEP_ANCHO * k))
        x_sep = _SEP1_X * k
        x = _TEXTO1_X * k
        for i, texto in enumerate(self._textos):
            if i:  # la línea tenue separa cada bloque, con los mismos huecos que el maestro
                x_sep = x + _HUECO_ANTES_SEP * k
                x = x_sep + _HUECO_DESPUES_SEP * k
            c.create_rectangle(x_sep, _SEP_Y0 * k, x_sep + grosor, _SEP_Y1 * k, fill=sep, width=0)
            texto = texto.upper()
            for i_l, letra in enumerate(texto):  # letra por letra: Tk no tiene espaciado entre letras
                c.create_text(round(x), linea_base + bajada, text=letra, anchor="sw", font=fuente,
                              fill=col["texto"])
                x += _avance(medidor, letra, texto[i_l + 1:i_l + 2]) * fuente_px / _MEDIDA + _ESPACIADO * k
        ancho = math.ceil(x - _ESPACIADO * k) + 1
        alto = math.ceil(_ALTO_SVG * k)
        if (round(self._apply_widget_scaling(self._desired_width)), round(self._apply_widget_scaling(self._desired_height))) != (ancho, alto):
            self._set_dimensions(width=ancho / s, height=alto / s)

    def _triangulo(self, c, k, col, fondo):
        e = _TRIANGULO_ANCHO / 80  # unidades del SVG por unidad del viewBox del triángulo
        a_px = lambda p: ((p[0] - 10) * e * k, (p[1] - 14) * e * k)  # noqa: E731
        if sys.platform == "darwin":  # el Canvas de Mac suaviza los bordes (CoreGraphics)
            for *pts, nombre in _TRI:
                c.create_polygon(*[v for p in pts for v in a_px(p)], fill=col[nombre], outline="")
            return
        # Windows y Linux dibujan polígonos sin suavizar: se rasteriza con PIL a 4x y se reduce,
        # al tamaño exacto en píxeles de pantalla (no se reescala después, así que queda nítido).
        try:
            from PIL import Image, ImageDraw, ImageTk
        except Exception:
            for *pts, nombre in _TRI:
                c.create_polygon(*[v for p in pts for v in a_px(p)], fill=col[nombre], outline="")
            return
        f = 4
        w, h = math.ceil(_TRIANGULO_ANCHO * k), math.ceil(_ALTO_SVG * k)
        img = Image.new("RGB", (w * f, h * f), _hex(fondo, self))
        d = ImageDraw.Draw(img)
        for *pts, nombre in _TRI:
            d.polygon([(x * f, y * f) for x, y in map(a_px, pts)], fill=col[nombre])
        self._imagen_tri = ImageTk.PhotoImage(img.resize((w, h), Image.LANCZOS), master=self)
        c.create_image(0, 0, image=self._imagen_tri, anchor="nw")
