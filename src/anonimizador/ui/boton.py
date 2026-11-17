"""Botón con relieve (estilo Windows 98, esquinas redondeadas, paleta de LegalAtlas).

Todo se dibuja en un Canvas con vectores y texto, así que se ve nítido en Retina y con escala de
Windows. Como en Windows 98: un contorno, y dentro un bisel de dos líneas, claras arriba/izquierda
y oscuras abajo/derecha. Al presionar el bisel desaparece, queda una línea oscura arriba/izquierda
y el texto baja un píxel: el botón «se hunde».

Acepta lo que esta app le pasaba a CTkButton (text, command, width, height, font, state y
configure/cget de esos mismos). Los colores de CTkButton (fg_color, hover_color, border_*,
text_color) se aceptan por compatibilidad: fg_color="transparent" equivale a variante secundaria;
los demás se ignoran, el color lo pone la variante.
"""

from __future__ import annotations

import sys
import tkinter.font as tkfont

import customtkinter as ctk
from customtkinter.windows.widgets.core_rendering import CTkCanvas, DrawEngine
from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass

# (claro, oscuro) por variante. Principal: carbón del triángulo / dorado de su base.
# luz_ext/luz_int: las dos líneas claras del bisel; sombra_ext/sombra_int: las dos oscuras.
PALETAS = {
    "principal": {
        "cara": ("#23221e", "#b8853a"),
        "cara_hover": ("#34332e", "#c49248"),
        "cara_presionada": ("#1b1a17", "#a97a32"),
        "luz_ext": ("#85827a", "#f0cd8f"),
        "luz_int": ("#45433d", "#d1a258"),
        "sombra_int": ("#121110", "#8a6326"),
        "sombra_ext": ("#050505", "#5e4116"),
        "contorno": ("#000000", "#2a1e0e"),
        "texto": ("#f7f5f0", "#1d1b16"),
    },
    "secundario": {
        "cara": ("#e8e5de", "#3c3b36"),
        "cara_hover": ("#f1efe9", "#46453f"),
        "cara_presionada": ("#dedad1", "#35342f"),
        "luz_ext": ("#ffffff", "#6a6861"),
        "luz_int": ("#f6f4ef", "#4c4a44"),
        "sombra_int": ("#b9b4a8", "#2a2925"),
        "sombra_ext": ("#8e897d", "#161614"),
        "contorno": ("#6f6b62", "#0e0e0c"),
        "texto": ("#23221e", "#ecebe6"),
    },
}
DESHABILITADO = {
    "cara": ("#e3e0d9", "#33322e"),
    "luz_ext": ("#fbfaf7", "#4a4944"),
    "luz_int": ("#efede8", "#3d3c37"),
    "sombra_int": ("#d3cfc6", "#2b2a26"),
    "sombra_ext": ("#c1bcb1", "#23221f"),
    "contorno": ("#aaa59a", "#1c1b18"),
    "texto": ("#a19c90", "#6c6a62"),
    "relieve": ("#ffffff", "#1c1b18"),  # texto grabado, como en Windows 98
}
_IGNORADOS = ("hover_color", "border_width", "border_color", "text_color", "text_color_disabled",
              "border_spacing", "anchor")


def _rect_redondo(c: CTkCanvas, x0: float, y0: float, x1: float, y1: float, r: float, color: str):
    """Rectángulo redondeado suavizado en todas las plataformas (mismo truco que CustomTkinter)."""
    r = max(0, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    if x1 <= x0 or y1 <= y0:
        return
    if r < 1:
        c.create_rectangle(x0, y0, x1, y1, fill=color, width=0)
        return
    if DrawEngine.preferred_drawing_method == "font_shapes":  # Windows y Linux: círculos de fuente
        r = round(r)
        for cx, cy in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x1 - r, y1 - r), (x0 + r, y1 - r)):
            c.create_aa_circle(cx, cy, r, fill=color)
            c.create_aa_circle(cx, cy, r, fill=color, angle=180)
        c.create_rectangle(x0 + r, y0, x1 - r, y1, fill=color, width=0)
        c.create_rectangle(x0, y0 + r, x1, y1 - r, fill=color, width=0)
    else:  # Mac: el Canvas ya suaviza; polígono con bordes gruesos redondos
        c.create_polygon(x0 + r, y0 + r, x1 - r, y0 + r, x1 - r, y1 - r, x0 + r, y1 - r,
                         fill=color, outline=color, width=2 * r, joinstyle="round")


class Boton3D(CTkBaseClass):
    RELLENO_X = 16  # margen horizontal mínimo del texto, en puntos

    def __init__(self, master, text: str = "", command=None, width: int = 140, height: int = 32,
                 font=None, state: str = "normal", variante: str = "principal", corner_radius: int = 7,
                 hundido: bool = False, bg_color="transparent", **kwargs):
        if kwargs.pop("fg_color", None) == "transparent":
            variante = "secundario"
        for k in _IGNORADOS:
            kwargs.pop(k, None)
        super().__init__(master, bg_color=bg_color, width=width, height=height, **kwargs)
        self._texto = text
        self._command = command
        self._estado = state
        self._variante = variante
        self._radio = corner_radius
        self._hundido = hundido  # fijo hundido: pestaña activa, interruptor encendido
        self._ancho_pedido = width
        self._font = self._check_font_type(font) if font is not None else ctk.CTkFont()
        if isinstance(self._font, ctk.CTkFont):
            self._font.add_size_configure_callback(self._cambio_fuente)
        self._sobre = self._presionado = self._foco = False

        self._canvas = CTkCanvas(self, highlightthickness=0, borderwidth=0,
                                 takefocus=1 if state != "disabled" else 0)
        self._canvas.place(x=0, y=0, relwidth=1, relheight=1)
        for evento, f in (("<Enter>", self._entrar), ("<Leave>", self._salir),
                          ("<ButtonPress-1>", self._presionar), ("<ButtonRelease-1>", self._soltar),
                          ("<FocusIn>", lambda _e: self._con_foco(True)),
                          ("<FocusOut>", lambda _e: self._con_foco(False)),
                          ("<Return>", self._tecla), ("<KP_Enter>", self._tecla), ("<space>", self._tecla)):
            self._canvas.bind(evento, f)
        self._ajustar_ancho()
        self._draw()

    # --- API compatible con CTkButton ------------------------------------------------------

    def invoke(self):
        if self._estado != "disabled" and self._command is not None:
            return self._command()
        return None

    def configure(self, require_redraw=False, **kwargs):
        if kwargs.get("fg_color") == "transparent":
            self._variante = "secundario"
        kwargs.pop("fg_color", None)
        for k in _IGNORADOS:
            kwargs.pop(k, None)
        ancho = False
        if "text" in kwargs:
            self._texto = kwargs.pop("text")
            ancho = True
        if "command" in kwargs:
            self._command = kwargs.pop("command")
        if "state" in kwargs:
            self._estado = kwargs.pop("state")
            self._canvas.configure(takefocus=0 if self._estado == "disabled" else 1)
            if self._estado == "disabled":
                self._presionado = False
            require_redraw = True
        if "variante" in kwargs:
            self._variante = kwargs.pop("variante")
            require_redraw = True
        if "hundido" in kwargs:
            self._hundido = kwargs.pop("hundido")
            require_redraw = True
        if "corner_radius" in kwargs:
            self._radio = kwargs.pop("corner_radius")
            require_redraw = True
        if "font" in kwargs:
            if isinstance(self._font, ctk.CTkFont):
                self._font.remove_size_configure_callback(self._cambio_fuente)
            self._font = self._check_font_type(kwargs.pop("font"))
            if isinstance(self._font, ctk.CTkFont):
                self._font.add_size_configure_callback(self._cambio_fuente)
            ancho = True
        if "width" in kwargs:
            self._ancho_pedido = kwargs.pop("width")
            ancho = True
        super().configure(require_redraw=False, **kwargs)
        if ancho:
            self._ajustar_ancho()
            require_redraw = True
        if require_redraw:
            self._draw()

    def cget(self, attribute_name: str):
        valores = {"text": self._texto, "command": self._command, "state": self._estado,
                   "font": self._font, "variante": self._variante, "hundido": self._hundido,
                   "corner_radius": self._radio}
        if attribute_name in valores:
            return valores[attribute_name]
        return super().cget(attribute_name)

    def bind(self, sequence=None, command=None, add=True):
        return self._canvas.bind(sequence, command, add="+" if add in (True, "+") else add)

    def unbind(self, sequence=None, funcid=None):
        self._canvas.unbind(sequence, funcid)

    def focus_set(self):
        self._canvas.focus_set()

    focus = focus_set

    def destroy(self):
        if isinstance(self._font, ctk.CTkFont):
            self._font.remove_size_configure_callback(self._cambio_fuente)
        super().destroy()

    # --- medidas -------------------------------------------------------------------------

    def _fuente_escalada(self):
        s = self._get_widget_scaling()
        if isinstance(self._font, ctk.CTkFont):
            return self._font.create_scaled_tuple(s)
        familia, tam, *resto = self._font
        return (familia, -abs(round(tam * s)), *resto)

    def _ancho_texto(self) -> float:
        """Ancho del texto en puntos (sin escalar)."""
        if isinstance(self._font, ctk.CTkFont):
            return self._font.measure(self._texto)
        familia, tam, *resto = self._font
        return tkfont.Font(root=self, font=(familia, -abs(tam), *resto)).measure(self._texto)

    def _ajustar_ancho(self):
        self._set_dimensions(width=max(self._ancho_pedido, self._ancho_texto() + 2 * self.RELLENO_X))

    def _cambio_fuente(self):
        self._ajustar_ancho()
        self._draw()

    def _set_scaling(self, *args, **kwargs):
        super()._set_scaling(*args, **kwargs)
        self._draw()

    def _set_appearance_mode(self, mode_string):
        super()._set_appearance_mode(mode_string)  # ya redibuja

    # --- eventos -------------------------------------------------------------------------

    def _entrar(self, _e=None):
        self._sobre = True
        self._draw()

    def _salir(self, _e=None):
        self._sobre = False
        self._draw()

    def _presionar(self, _e=None):
        if self._estado == "disabled":
            return
        self._presionado = True
        self._draw()

    def _soltar(self, e=None):
        if not self._presionado:
            return
        self._presionado = False
        self._draw()
        dentro = e is None or (0 <= e.x < self._canvas.winfo_width() and 0 <= e.y < self._canvas.winfo_height())
        if dentro:
            self.invoke()

    def _tecla(self, _e=None):
        if self._estado == "disabled":
            return "break"
        self._presionado = True
        self._draw()
        self.after(90, self._soltar_tecla)
        return "break"

    def _soltar_tecla(self):
        if not self.winfo_exists():
            return
        self._presionado = False
        self._draw()
        self.invoke()

    def _con_foco(self, foco: bool):
        self._foco = foco
        self._draw()

    # --- dibujo --------------------------------------------------------------------------

    def _draw(self, no_color_updates=False):
        super()._draw(no_color_updates)
        if not hasattr(self, "_canvas"):
            return
        c = self._canvas
        c.delete("all")
        c._aa_circle_canvas_ids.clear()
        s = self._get_widget_scaling()
        w = round(self._apply_widget_scaling(self._current_width))
        h = round(self._apply_widget_scaling(self._current_height))
        modo = self._apply_appearance_mode
        c.configure(bg=modo(self._bg_color), cursor="")
        apagado = self._estado == "disabled"
        p = DESHABILITADO if apagado else PALETAS.get(self._variante, PALETAS["secundario"])
        hundido = not apagado and (self._presionado or self._hundido)
        if apagado:
            cara = p["cara"]
        elif hundido:
            cara = p["cara_presionada"]
        else:
            cara = p["cara_hover"] if self._sobre else p["cara"]

        u = max(1, round(s))  # un «píxel» lógico
        r = self._radio * s
        # Cada capa tapa a la anterior salvo una franja de un píxel: abajo/derecha o arriba/izquierda.
        _rect_redondo(c, 0, 0, w, h, r, modo(p["contorno"]))
        if hundido:  # una línea oscura arriba/izquierda y la cara: el botón «se hunde»
            _rect_redondo(c, u, u, w - u, h - u, r - u, modo(p["sombra_ext"]))
            _rect_redondo(c, 2 * u, 2 * u, w - u, h - u, r - 2 * u, modo(cara))
            dx = dy = u
        else:
            _rect_redondo(c, u, u, w - u, h - u, r - u, modo(p["sombra_ext"]))
            _rect_redondo(c, u, u, w - 2 * u, h - 2 * u, r - u, modo(p["luz_ext"]))
            _rect_redondo(c, 2 * u, 2 * u, w - 2 * u, h - 2 * u, r - 2 * u, modo(p["sombra_int"]))
            _rect_redondo(c, 2 * u, 2 * u, w - 3 * u, h - 3 * u, r - 2 * u, modo(p["luz_int"]))
            _rect_redondo(c, 3 * u, 3 * u, w - 3 * u, h - 3 * u, r - 3 * u, modo(cara))
            dx = dy = 0

        fuente = self._fuente_escalada()
        cx, cy = w / 2 - u / 2 + dx, h / 2 - u / 2 + dy
        if apagado:
            c.create_text(cx + u, cy + u, text=self._texto, font=fuente, fill=modo(p["relieve"]))
        c.create_text(cx, cy, text=self._texto, font=fuente, fill=modo(p["texto"]))

        if self._foco and not apagado:  # anillo punteado de foco, como en Windows 98
            m = 4 * u
            c.create_rectangle(m + dx, m + dy, w - m - u + dx, h - m - u + dy, outline=modo(p["texto"]),
                               width=1, dash=(1, 2) if sys.platform != "darwin" else (2, 2))
