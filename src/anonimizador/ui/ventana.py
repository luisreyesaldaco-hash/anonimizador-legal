"""Ventana principal (CustomTkinter). Toda la lógica vive en `flujo.Flujo`."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tempfile
import time
import traceback
import webbrowser
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import filedialog, ttk

import customtkinter as ctk
import pymupdf

from .. import preferencias
from ..flujo import Flujo
from ..procesadores import EXTENSIONES, IMAGENES, imagen_a_pdf
from ..reversion import markdown_a_texto, nombre_sugerido, revertir_docx, texto_a_docx, texto_de_docx
from ..seudonimos import etiquetas_desconocidas
from ..seudonimos import revertir as revertir_texto
from .boton import Boton3D
from .marca import Logotipo, fuente_disponible, registrar_fuente
from .visor import VisorDocumento
from ..idioma import IDIOMAS as IDIOMAS_DOC
from ..textos import IDIOMAS_UI, catalogo, idioma_ui, poner_idioma_ui, traducir, tr

# ANONIMIZADOR_DEPURAR=1 anota en un archivo los eventos de la interfaz (sin datos del documento).
_BITACORA = os.environ.get("ANONIMIZADOR_DEPURAR") and Path(tempfile.gettempdir()) / "anonimizador-ui.log"


def _anotar(*partes):
    if _BITACORA:
        with open(_BITACORA, "a", encoding="utf-8") as f:
            f.write(f"{time.monotonic():.3f} " + " ".join(str(p) for p in partes) + "\n")

try:  # arrastrar y soltar es opcional: sin tkinterdnd2 queda el botón
    from tkinterdnd2 import DND_FILES, TkinterDnD
except Exception:  # pragma: no cover
    TkinterDnD = None
    DND_FILES = None

# Paleta de LegalAtlas: carbón del triángulo en modo claro, dorado de su base en modo oscuro.
ACENTO = ("#23221e", "#b8853a")
ACENTO_HOVER = ("#45443e", "#cc9a4f")
RECURSOS = Path(__file__).parent / "recursos"
FILA = 28  # alto de cada fila de la tabla de hallazgos, en píxeles
# Una sola fuente en toda la app: la del sistema (Windows, Mac) o una común en Linux.
FAMILIAS = ("Segoe UI", "Helvetica Neue", "Roboto", "DejaVu Sans")
AVISO = ("#8a5a00", "#e0a94f")
ERROR = ("#a33a2a", "#ef8a78")
OK = ("#2b7a4b", "#6cc38f")
BORDE = ("#d6d2c8", "#45443e")
TENUE = ("gray35", "gray65")
FONDO_CUADRO = ("#f7f6f2", "#302f2a")
FONDO_FICHA = ("#ffffff", "#3a3934")
# Distintivo de tipo de archivo: los colores que la gente ya asocia con PDF y con Word.
_WORD = ("WORD", ("#2b579a", "#4a78c2"))
_IMAGEN = ("IMG", ("#6b5b95", "#8f7fbf"))
_TEXTO = ("TXT", ("#5f6b5a", "#869180"))
DISTINTIVOS = {".pdf": ("PDF", ("#a33a2a", "#c4553f")), ".docx": _WORD, ".doc": _WORD, ".odt": _WORD,
               ".rtf": _WORD, ".txt": _TEXTO, ".md": _TEXTO, **{e: _IMAGEN for e in IMAGENES}}
SALIDA_WORD = "Word (.docx)"


def _tipos_archivo():  # al momento: el idioma puede cambiar con la app abierta
    return [(tr('Documentos'), " ".join("*" + e for e in EXTENSIONES)), ("PDF", "*.pdf"),
            ("Word", "*.docx *.doc *.odt *.rtf"), (tr('Texto'), "*.txt *.md"),
            (tr('Imágenes'), " ".join("*" + e for e in IMAGENES))]
MARCA_SI, MARCA_NO = "☑", "☐"

_Base = ctk.CTk
if TkinterDnD is not None:

    class _Base(ctk.CTk, TkinterDnD.DnDWrapper):  # type: ignore[no-redef]
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.TkdndVersion = TkinterDnD._require(self)


class Ventana(_Base):
    def __init__(self):
        registrar_fuente()  # antes de crear la ventana: Tk solo ve las fuentes que ya existían
        super().__init__()
        ctk.set_appearance_mode("system")
        self.title("Anonimizador · LegalAtlas")
        self._poner_icono()
        self.geometry("1120x740")
        self.minsize(920, 600)
        self.flujo = Flujo()
        self._cola: queue.Queue = queue.Queue()
        self._ocupado = False
        self._editado = False
        self._activo = 0  # documento que se ve en el visor y cuya ficha está activa
        self._visor_ruta: Path | None = None  # lo que hay cargado en el visor
        self._ubic: list = []  # apariciones (flujo.Ubicacion) del hallazgo seleccionado
        self._pos_ap = 0  # cuál de ellas se está viendo
        self._etiqueta_vista: str | None = None
        self._terminos_sel: list[str] = []
        self._unificar_fuente()
        self._aplicar_paleta()
        self._fuente = ctk.CTkFont(size=14)
        self._titulo = ctk.CTkFont(size=22, weight="bold")
        self._sub = ctk.CTkFont(size=13)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self._barra_superior()
        self._pantalla_carga()
        self._pantalla_revision()
        self._mostrar(self.carga)
        if DND_FILES:  # toda la ventana recibe: en la carga abre, en la revisión agrega
            self.drop_target_register(DND_FILES)
            self.dnd_bind("<<Drop>>", self._soltar)
        self.after(100, self._atender_cola)
        self.protocol("WM_DELETE_WINDOW", self._cerrar)
        if sys.platform == "darwin":  # Cmd+Q y «Salir» del menú de la app
            self.createcommand("::tk::mac::Quit", self._cerrar)
        if _BITACORA:
            self.bind_all("<ButtonPress>", lambda e: _anotar("press", e.widget, e.num, e.x_root, e.y_root), add="+")
            self.bind_all("<Double-ButtonPress-1>", lambda e: _anotar("doble", e.widget, e.x_root, e.y_root), add="+")
            _anotar("inicio", sys.platform, self.tk.call("info", "patchlevel"))

    # --- errores ----------------------------------------------------------------

    def report_callback_exception(self, tipo, valor, rastro):
        """Un error dentro de la ventana (no en la tarea de fondo). Tk lo imprimiría en una
        consola que en Windows y Mac no existe: el usuario solo veía que «no pasó nada»."""
        ruta = registrar_error(tipo, valor, rastro)
        if self._ocupado:
            self._ocupar(False)
        try:
            self._mensaje(tr('Algo falló'), tr('La app tuvo un error y no pudo seguir: {error}\n\nEl detalle (sin datos '
                                                'del documento) quedó en:\n{ruta}', error=valor, ruta=ruta), ERROR)
        except Exception:  # si ni el diálogo se puede abrir, al menos queda el archivo
            pass

    # --- marca ------------------------------------------------------------------

    @staticmethod
    def _aplicar_paleta():
        """La paleta como tema: así también los diálogos de CustomTkinter (Renombrar…) la usan."""
        t = ctk.ThemeManager.theme
        for w in ("CTkButton", "CTkCheckBox", "CTkRadioButton"):
            t[w]["fg_color"] = list(ACENTO)
            t[w]["hover_color"] = list(ACENTO_HOVER)
        t["CTkCheckBox"]["border_color"] = list(ACENTO)
        t["CTkOptionMenu"]["fg_color"] = list(ACENTO)
        t["CTkOptionMenu"]["button_color"] = list(ACENTO_HOVER)
        t["CTkOptionMenu"]["button_hover_color"] = list(ACENTO_HOVER)
        t["CTkProgressBar"]["progress_color"] = list(ACENTO)
        t["CTkEntry"]["border_color"] = ["#c9c5bc", "#4a4943"]

    def _unificar_fuente(self):
        """CustomTkinter, ttk y los diálogos de tk usan cada uno su fuente: todos a la misma."""

        disponibles = set(tkfont.families(self))
        familia = next((f for f in FAMILIAS if f in disponibles), None)
        if familia is None:
            return
        self.familia = familia
        ctk.ThemeManager.theme["CTkFont"]["family"] = familia
        for nombre in ("TkDefaultFont", "TkTextFont", "TkHeadingFont", "TkMenuFont", "TkCaptionFont",
                       "TkSmallCaptionFont", "TkTooltipFont", "TkIconFont"):
            try:
                tkfont.nametofont(nombre, root=self).configure(family=familia)
            except tk.TclError:
                pass

    def _poner_icono(self):
        try:
            if os.name == "nt" and (RECURSOS / "icono.ico").exists():
                self.iconbitmap(default=str(RECURSOS / "icono.ico"))
            else:
                self._icono = tk.PhotoImage(file=str(RECURSOS / "icono.png"))
                self.iconphoto(True, self._icono)
        except Exception:  # sin ícono la app funciona igual
            pass

    @staticmethod
    def _logo():
        try:
            from PIL import Image
            claro = Image.open(RECURSOS / "logo-claro.png")
            oscuro = Image.open(RECURSOS / "logo-oscuro.png")
        except Exception:
            return None
        alto = 30
        return ctk.CTkImage(light_image=claro, dark_image=oscuro, size=(round(claro.width * alto / claro.height), alto))

    # --- estructura ------------------------------------------------------------

    def _barra_superior(self):
        barra = ctk.CTkFrame(self, fg_color="transparent")
        barra.grid(row=0, column=0, sticky="ew", padx=20, pady=(16, 8))
        barra.grid_columnconfigure(0, weight=1)
        marca = ctk.CTkFrame(barra, fg_color="transparent")
        marca.grid(row=0, column=0, sticky="w")
        # «LEGAL ATLAS | ANONIMIZADOR»: en vectores con la letra del imagotipo (nítido en Retina);
        # si la fuente no se pudo registrar, el PNG de siempre.
        try:
            vectorial = Logotipo(marca, alto=30) if fuente_disponible(self) else None
        except Exception:  # cualquier tropiezo dibujando: el PNG de siempre
            vectorial = None
        if vectorial is not None:
            vectorial.pack(side="left")
        elif (logo := self._logo()) is not None:
            ctk.CTkLabel(marca, image=logo, text="").pack(side="left")
        else:
            ctk.CTkLabel(marca, text="Anonimizador", font=self._titulo).pack(side="left")
        # Segunda revisión con una IA que corre en esta computadora (Ollama). Solo se ve con
        # documentos cargados; mientras trabaja, el mismo botón la detiene.
        self.caja_ia = ctk.CTkFrame(barra, fg_color="transparent")
        self.boton_ia = Boton3D(self.caja_ia, text=self._texto_boton_ia(), command=self._revisar_con_ia,
                                height=32, width=0)
        self.boton_ia.pack(side="left")
        Boton3D(self.caja_ia, text="?", command=self._explicar_ia, variante="secundario",
                height=32, width=32).pack(side="left", padx=(6, 0))
        Boton3D(barra, text=tr('Revertir respuesta de la IA…'), command=self._ventana_revertir,
                variante="secundario", height=32).grid(row=0, column=2, rowspan=2)
        # Idioma de la ventana (no el del documento, que se detecta solo).
        nombres = [n for k, n in IDIOMAS_UI.items() if k == "es" or catalogo(k)]  # solo los que ya tienen traducción
        self.idioma_ui = ctk.StringVar(value=IDIOMAS_UI[idioma_ui()])
        ctk.CTkOptionMenu(barra, values=nombres, variable=self.idioma_ui, width=110, height=32,
                          command=self._cambiar_idioma_ui).grid(row=0, column=3, rowspan=2, padx=(10, 0))

    def _cambiar_idioma_ui(self, nombre: str):
        codigo = next(k for k, v in IDIOMAS_UI.items() if v == nombre)
        if codigo == idioma_ui():
            return
        if self._ocupado:  # a media lectura o guardado no se rehace la ventana
            self.idioma_ui.set(IDIOMAS_UI[idioma_ui()])
            self._mensaje(traducir(codigo, "Idioma"),
                          traducir(codigo, "Espera a que termine lo que está haciendo y vuelve a elegir el idioma."),
                          AVISO)
            return
        poner_idioma_ui(codigo)
        self._reconstruir()

    def _reconstruir(self):
        """Vuelve a dibujar la ventana en el idioma actual sin perder el trabajo: los documentos,
        las etiquetas y lo editado viven en self.flujo; aquí solo se rehacen los widgets.
        Las ventanas aparte (Revertir) se quedan como están hasta que se cierren."""
        en_revision = bool(self.flujo.documentos) and self.revision.winfo_ismapped()
        revisado = self.revisado.get()
        pestana = list(self._pestanas).index(self._pestana_activa) if self._pestana_activa in self._pestanas else None
        activo = self._activo
        self._cerrar_edicion()
        if getattr(self, "_tarea_fichas", None):
            self.after_cancel(self._tarea_fichas)
            self._tarea_fichas = None
        # Lo viejo se esconde y se destruye después: si se destruyera ya, tkinter podría reusar el
        # nombre de un callback suyo aún pendiente (after) para uno nuevo y llamarlo mal.
        viejos = [h for h in self.winfo_children() if not isinstance(h, tk.Toplevel)]
        for hijo in viejos:
            hijo.grid_forget()
        self.after(5000, lambda: [h.destroy() for h in viejos if h.winfo_exists()])
        self._archivos_pintados = None
        self._barra_superior()
        self._pantalla_carga()
        self._pantalla_revision()
        if not en_revision:
            self._mostrar(self.carga)
            return
        editado = self._editado
        self._cargado(None)  # misma pantalla que tras cargar, con los datos que ya hay
        self._editado = editado
        self.revisado.set(revisado)
        self._actualizar_boton()
        if pestana is not None:
            self.mostrar_pestana(list(self._pestanas)[pestana])
        if activo:
            self._elegir_documento(activo, saltar=False)

    def _pantalla_carga(self):
        self.carga = ctk.CTkFrame(self, fg_color="transparent")
        zona = ctk.CTkFrame(self.carga, border_width=2, border_color=("gray70", "gray35"), corner_radius=12)
        zona.place(relx=0.5, rely=0.45, anchor="center", relwidth=0.7, relheight=0.6)
        interior = ctk.CTkFrame(zona, fg_color="transparent")
        interior.place(relx=0.5, rely=0.5, anchor="center")
        texto = tr('Arrastra aquí tus documentos') if DND_FILES else tr('Elige tus documentos')
        ctk.CTkLabel(interior, text=texto, font=ctk.CTkFont(size=18, weight="bold")).pack(pady=(0, 6))
        ctk.CTkLabel(interior, text=tr('PDF, Word, texto o fotos · uno o varios: comparten revisión y tabla'),
                     font=self._sub, text_color=("gray35", "gray65")).pack(pady=(0, 18))
        self.boton_abrir = Boton3D(interior, text=tr('Elegir archivos…'), command=self._elegir_archivo,
                                   height=40, width=170, font=self._fuente)
        self.boton_abrir.pack()
        self.estado_carga = ctk.CTkLabel(interior, text="", font=self._sub)
        self.estado_carga.pack(pady=(14, 0))
        # Barra propia de esta pantalla: la del pie solo se ve en la revisión. Sin ella, un PDF
        # escaneado (un minuto de OCR) dejaba solo un renglón gris y parecía que no pasaba nada.
        self.barra_carga = ctk.CTkProgressBar(interior, mode="indeterminate", width=260,
                                              progress_color=ACENTO)

    def _pantalla_revision(self):
        self.revision = ctk.CTkFrame(self, fg_color="transparent")
        self.revision.grid_columnconfigure(0, weight=1, uniform="c")
        self.revision.grid_columnconfigure(1, weight=1, uniform="c")
        self.revision.grid_rowconfigure(1, weight=1)

        # Encabezado: cuadro con los archivos del proyecto (una ficha por archivo: _pintar_archivos)
        self.cuadro_archivos = ctk.CTkFrame(self.revision, corner_radius=10, border_width=1, border_color=BORDE,
                                            fg_color=FONDO_CUADRO)
        self.cuadro_archivos.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(0, 10))
        self.cuadro_archivos.grid_columnconfigure(0, weight=1)
        self._fichas = ctk.CTkFrame(self.cuadro_archivos, fg_color="transparent")
        self._fichas.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=8)
        botones_archivo = ctk.CTkFrame(self.cuadro_archivos, fg_color="transparent")
        botones_archivo.grid(row=0, column=1, padx=(0, 12), pady=8)
        self._botones_archivo = botones_archivo
        self._ancho_fichas = 0
        self.cuadro_archivos.bind("<Configure>", self._al_cambiar_ancho_cuadro, add="+")
        # Idioma del documento (no el de la interfaz): con él se eligen las reglas y el modelo
        # de nombres. Se detecta solo; si se equivoca, aquí se corrige y se vuelve a leer.
        self.idioma_doc = tk.StringVar(value="")
        self.menu_idioma_doc = ctk.CTkOptionMenu(botones_archivo, values=list(IDIOMAS_DOC.values()),
                                                 variable=self.idioma_doc, width=120, height=30,
                                                 command=self._cambiar_idioma_doc)
        ctk.CTkLabel(botones_archivo, text=tr('Documento en:'), text_color=TENUE).grid(row=0, column=0, padx=(0, 6))
        self.menu_idioma_doc.grid(row=0, column=1, padx=(0, 10))
        self.boton_agregar = Boton3D(botones_archivo, text=tr('Agregar archivo…'), command=self._elegir_para_agregar,
                                     variante="secundario", width=140, height=30)
        self.boton_agregar.grid(row=0, column=2)
        self.boton_cambiar = Boton3D(botones_archivo, text=tr('Cambiar archivo'), command=self._volver_a_carga,
                                     variante="secundario", width=140, height=30)
        self.boton_cambiar.grid(row=0, column=3, padx=(6, 0))

        # Izquierda: hallazgos, con las acciones que los modifican encima
        izq = ctk.CTkFrame(self.revision)
        izq.grid(row=1, column=0, sticky="nsew", padx=(20, 8))
        izq.grid_rowconfigure(1, weight=1)
        izq.grid_columnconfigure(0, weight=1)
        cabeza = ctk.CTkFrame(izq, fg_color="transparent")
        cabeza.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        cabeza.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(cabeza, text=tr('Hallazgos'), font=self._fuente, anchor="w").grid(row=0, column=0, sticky="w")
        acciones = ctk.CTkFrame(cabeza, fg_color="transparent")
        acciones.grid(row=0, column=1, sticky="e")
        estilo = dict(variante="secundario", width=0, height=28, font=ctk.CTkFont(size=12))
        self.boton_renombrar = Boton3D(acciones, text=tr('Renombrar'), command=self._renombrar, **estilo)
        self.boton_unir = Boton3D(acciones, text=tr('Unir con…'), command=self._unir, **estilo)
        self.boton_separar = Boton3D(acciones, text=tr('Separar variante…'), command=self._separar, **estilo)
        for i, b in enumerate((self.boton_renombrar, self.boton_unir, self.boton_separar)):
            b.grid(row=0, column=i, padx=(6, 0))
        self._estilo_tabla()
        marco = tk.Frame(izq)
        marco.grid(row=1, column=0, sticky="nsew", padx=12)
        marco.grid_rowconfigure(0, weight=1)
        marco.grid_columnconfigure(0, weight=1)
        self.tabla = ttk.Treeview(marco, columns=("etiqueta", "veces"), show="tree headings",
                                  selectmode="browse", style="Anon.Treeview")
        self.tabla.heading("#0", text=tr('Dato'))
        self.tabla.heading("etiqueta", text=tr('Se cambia por'))
        self.tabla.heading("veces", text=tr('Veces'))
        self.tabla.column("#0", width=220, minwidth=160, stretch=True)
        self.tabla.column("etiqueta", width=128, minwidth=110, stretch=False)
        self.tabla.column("veces", width=60, minwidth=50, stretch=False, anchor="center")
        barra = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        self.tabla.configure(yscrollcommand=barra.set)
        self.tabla.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.tabla.bind("<<TreeviewSelect>>", lambda _e: self._mostrar_detalle())
        self.tabla.bind("<Button-1>", self._clic_tabla)
        self.tabla.bind("<Double-Button-1>", self._doble_clic_tabla)
        self.tabla.bind("<space>", lambda _e: self._alternar_seleccion())
        self.tabla.bind("<Return>", lambda _e: self._renombrar())
        self._lineas: list[tk.Frame] = []
        self.tabla.tag_configure("categoria", background=self._fondo_categoria,
                                 font=(getattr(self, "familia", "TkDefaultFont"), 11, "bold"))
        for evento in ("<Configure>", "<ButtonRelease-1>", "<B1-Motion>", "<MouseWheel>",
                       "<Button-4>", "<Button-5>", "<<TreeviewOpen>>", "<<TreeviewClose>>"):
            self.tabla.bind(evento, lambda _e: self.after_idle(self._dibujar_cuadricula), add="+")
        for evento in ("<MouseWheel>", "<Button-4>", "<Button-5>", "<<TreeviewOpen>>", "<<TreeviewClose>>"):
            self.tabla.bind(evento, lambda _e: self._cerrar_edicion(), add="+")

        manual = ctk.CTkFrame(izq, fg_color="transparent")
        manual.grid(row=2, column=0, sticky="ew", padx=12, pady=10)
        manual.grid_columnconfigure(0, weight=1)
        self.entrada_manual = ctk.CTkEntry(manual, placeholder_text=tr('Palabra, nombre o frase que no se detectó'))
        self.entrada_manual.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entrada_manual.bind("<Return>", lambda _e: self._agregar_manual())
        self.boton_manual = Boton3D(manual, text=tr('Añadir a la lista'), command=self._agregar_manual, width=0)
        self.boton_manual.grid(row=0, column=1)

        # Derecha: pestañas «Contexto | Documento» (la barra aparece cuando hay dos o más).
        der = ctk.CTkFrame(self.revision)
        der.grid(row=1, column=1, sticky="nsew", padx=(8, 20))
        der.grid_rowconfigure(1, weight=1)
        der.grid_columnconfigure(0, weight=1)
        self.panel_derecho = der
        self._barra_pestanas = ctk.CTkFrame(der, fg_color="transparent")
        self._pila_derecha = ctk.CTkFrame(der, fg_color="transparent")
        self._pila_derecha.grid(row=1, column=0, sticky="nsew")
        self._pila_derecha.grid_rowconfigure(0, weight=1)
        self._pila_derecha.grid_columnconfigure(0, weight=1)
        self._pestanas: dict = {}
        self._pestana_activa: str | None = None
        self.agregar_pestana(tr('Contexto'), self._crear_contexto)
        self.agregar_pestana(tr('Documento'), self._crear_documento)

        # Pie: avisos, confirmación y acción principal
        pie = ctk.CTkFrame(self.revision, fg_color="transparent")
        pie.grid(row=2, column=0, columnspan=2, sticky="ew", padx=20, pady=(8, 16))
        pie.grid_columnconfigure(0, weight=1)
        self.avisos = ctk.CTkLabel(pie, text="", text_color=AVISO, justify="left", anchor="w", wraplength=760)
        self.avisos.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 6))
        self.revisado = ctk.BooleanVar(value=False)
        self.check_revisado = ctk.CTkCheckBox(
            pie, text=tr('Revisé los hallazgos'),
            variable=self.revisado, command=self._actualizar_boton, fg_color=ACENTO, hover_color=ACENTO_HOVER)
        self.check_revisado.grid(row=1, column=0, sticky="w")
        # Progreso: la barra y, en tareas largas (la IA local), qué parte va.
        self.caja_progreso = ctk.CTkFrame(pie, fg_color="transparent")
        self.progreso = ctk.CTkProgressBar(self.caja_progreso, mode="indeterminate", width=160,
                                           progress_color=ACENTO)
        self.progreso.pack(side="left")
        self.texto_progreso = ctk.CTkLabel(self.caja_progreso, text="", text_color="gray")
        self.texto_progreso.pack(side="left", padx=10)
        self.boton_guardar = Boton3D(pie, text=tr('Anonimizar y guardar'), command=self._guardar,
                                     height=42, width=220, font=ctk.CTkFont(size=15, weight="bold"),
                                     state="disabled")
        self.boton_guardar.grid(row=1, column=2, sticky="e")
        # Formato de salida: se recuerda entre sesiones (hay quien quiere todo siempre en Word).
        caja_salida = ctk.CTkFrame(pie, fg_color="transparent")
        caja_salida.grid(row=1, column=1, sticky="e", padx=(0, 14))
        ctk.CTkLabel(caja_salida, text=tr('Salida:'), font=self._sub, text_color=TENUE).pack(side="left", padx=(0, 6))
        original = tr('Igual al original')
        self.salida = ctk.StringVar(value=SALIDA_WORD if preferencias.leer("salida") == "docx" else original)
        ctk.CTkSegmentedButton(
            caja_salida, values=[original, SALIDA_WORD], variable=self.salida, font=self._sub,
            selected_color=ACENTO, selected_hover_color=ACENTO_HOVER,
            command=lambda v: preferencias.guardar("salida", "docx" if v == SALIDA_WORD else "original"),
        ).pack(side="left")

    def _crear_contexto(self, master):
        pagina = ctk.CTkFrame(master, fg_color="transparent")
        pagina.grid_rowconfigure(1, weight=1)
        pagina.grid_columnconfigure(0, weight=1)
        self.titulo_detalle = ctk.CTkLabel(pagina, text=tr('Elige un hallazgo para ver dónde aparece'),
                                           font=self._fuente, anchor="w")
        self.titulo_detalle.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        self.contexto = ctk.CTkTextbox(pagina, wrap="word", font=ctk.CTkFont(size=13))
        self.contexto.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))
        self.contexto.tag_config("valor", foreground="#23221e", background="#e2c48f")
        self.contexto.tag_config("tenue", foreground="gray50")
        self.contexto.tag_config("archivo", foreground="gray50", spacing1=4, spacing3=6)
        self.contexto.configure(state="disabled")
        return pagina

    def _crear_documento(self, master):
        """El documento original, con lo marcado resaltado, y «‹ n de N ›» para recorrer las
        apariciones del hallazgo seleccionado (cruzando de documento si hace falta)."""
        pagina = ctk.CTkFrame(master, fg_color="transparent")
        pagina.grid_rowconfigure(1, weight=1)
        pagina.grid_columnconfigure(0, weight=1)
        nav = ctk.CTkFrame(pagina, fg_color="transparent")
        nav.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 4))
        nav.grid_columnconfigure(0, weight=1)
        self.titulo_visor = ctk.CTkLabel(nav, text="", font=self._fuente, anchor="w")
        self.titulo_visor.grid(row=0, column=0, sticky="ew")
        flecha = dict(variante="secundario", width=30, height=26, font=ctk.CTkFont(size=14, weight="bold"))
        self.boton_ap_ant = Boton3D(nav, text="‹", command=lambda: self._paso_aparicion(-1), **flecha)
        self.boton_ap_ant.grid(row=0, column=1)
        self.etiqueta_ap = ctk.CTkLabel(nav, text="", width=110, font=ctk.CTkFont(size=12), text_color=TENUE)
        self.etiqueta_ap.grid(row=0, column=2, padx=4)
        self.boton_ap_sig = Boton3D(nav, text="›", command=lambda: self._paso_aparicion(1), **flecha)
        self.boton_ap_sig.grid(row=0, column=3)
        self.visor = VisorDocumento(pagina)
        self.visor.grid(row=1, column=0, sticky="nsew", padx=12, pady=(2, 12))
        return pagina

    # --- panel derecho: pestañas -----------------------------------------------------------

    def agregar_pestana(self, nombre: str, crear, mostrar: bool = False):
        """Agrega una pestaña al panel derecho. `crear(master)` construye y devuelve su contenido
        sin colocarlo; se devuelve ese contenido. Ej.: agregar_pestana("Documento", Visor)."""
        pagina = crear(self._pila_derecha)
        pagina.grid(row=0, column=0, sticky="nsew")
        boton = Boton3D(self._barra_pestanas, text=nombre, variante="secundario", width=0, height=28,
                        font=ctk.CTkFont(size=12), command=lambda: self.mostrar_pestana(nombre))
        boton.pack(side="left", padx=(0, 6))
        self._pestanas[nombre] = (pagina, boton)
        if len(self._pestanas) > 1:
            self._barra_pestanas.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 0))
        self.mostrar_pestana(nombre if mostrar or self._pestana_activa is None else self._pestana_activa)
        return pagina

    def mostrar_pestana(self, nombre: str):
        self._pestana_activa = nombre
        for n, (_pagina, boton) in self._pestanas.items():
            boton.configure(hundido=(n == nombre))  # la activa queda hundida
        self._pestanas[nombre][0].tkraise()

    # --- cuadro de archivos ----------------------------------------------------------------

    def _pintar_archivos(self, archivos: list, activo: int = 0):
        """Dibuja el cuadro de archivos. Con uno: su ficha. Con varios: una ficha por archivo, como
        pestañas, la activa resaltada; un clic en otra llama a `_elegir_documento(i)`."""
        for w in self._fichas.winfo_children():
            w.destroy()
        n = len(archivos)
        varios = n > 1
        self._archivos_pintados = (list(archivos), activo)
        # Cuánto cabe: el ancho del cuadro menos los botones, repartido entre las fichas de una fila
        escala = ctk.ScalingTracker.get_widget_scaling(self)
        self._ancho_fichas = self.cuadro_archivos.winfo_width()
        libre = self._ancho_fichas - self._botones_archivo.winfo_reqwidth() - round(36 * escala)
        por_ficha = libre / min(n, 3) - round((100 if varios else 70) * escala)
        familia = getattr(self, "familia", "TkDefaultFont")
        f_nombre = tkfont.Font(family=familia, size=-round((13 if varios else 14) * escala), weight="bold")
        f_detalle = tkfont.Font(family=familia, size=-round(12 * escala))
        for i, ruta in enumerate(map(Path, archivos)):
            sigla, color = DISTINTIVOS.get(ruta.suffix.lower(), (ruta.suffix.lstrip(".").upper() or "?", TENUE))
            actual = i == activo
            ficha = ctk.CTkFrame(self._fichas, corner_radius=8, border_width=1 if varios else 0,
                                 border_color=ACENTO if actual else BORDE,
                                 fg_color=FONDO_FICHA if varios and actual else "transparent")
            # Varios: en filas de 3 (con la ventana angosta, los nombres se acortan)
            ficha.grid(row=i // 3, column=i % 3, sticky="w", padx=(0, 6) if varios else 0,
                       pady=(0, 6) if varios and i + 3 < n else 0)
            m = 6 if varios else 0  # con borde, el contenido no lo pisa
            ctk.CTkLabel(ficha, text=sigla, fg_color=color, text_color="#ffffff", corner_radius=4,
                         width=42 if varios else 46, height=22, font=ctk.CTkFont(size=11, weight="bold")).grid(
                row=0, column=0, rowspan=2, padx=(m + 2, 8 if varios else 10), pady=4)
            ctk.CTkLabel(ficha, text=_caber(ruta.name, f_nombre, por_ficha), anchor="w", height=18,
                         font=ctk.CTkFont(size=13 if varios else 14, weight="bold")).grid(
                row=0, column=1, sticky="sw", padx=(0, 2 if varios else 0), pady=(m, 0))
            ctk.CTkLabel(ficha, text=_caber(_detalle_archivo(ruta), f_detalle, por_ficha), anchor="w", height=16, text_color=TENUE,
                         font=ctk.CTkFont(size=12)).grid(row=1, column=1, sticky="nw", pady=(0, m))
            if varios:
                for w in (ficha, *ficha.winfo_children()):
                    w.bind("<Button-1>", lambda _e, i=i: self._elegir_documento(i))
                    if not actual:
                        tk.Misc.configure(w, cursor="hand2")  # también en el lienzo de CTkFrame
                ctk.CTkButton(ficha, text="×", width=22, height=22, corner_radius=11, fg_color="transparent",
                              hover_color=("#e7e4dd", "#4a4943"), text_color=TENUE, font=ctk.CTkFont(size=15),
                              command=lambda i=i: self._quitar_documento(i)).grid(
                    row=0, column=2, rowspan=2, padx=(0, m), sticky="n", pady=(m - 2, 0))
        self.boton_cambiar.configure(text=tr('Cambiar archivos') if varios else tr('Cambiar archivo'))

    def _al_cambiar_ancho_cuadro(self, evento):
        """Al cambiar el ancho de la ventana, las fichas se vuelven a medir (con una pausa)."""
        if not getattr(self, "_archivos_pintados", None) or abs(evento.width - self._ancho_fichas) < 8:
            return
        if getattr(self, "_tarea_fichas", None):
            self.after_cancel(self._tarea_fichas)
        self._tarea_fichas = self.after(150, lambda: (setattr(self, "_tarea_fichas", None),
                                                       self._pintar_archivos(*self._archivos_pintados)))

    def _elegir_documento(self, indice: int, saltar: bool = True):
        """Pasa el visor (y la ficha activa) al documento `indice`; con un hallazgo
        seleccionado, a su primera aparición en ese documento."""
        if self._ocupado or not 0 <= indice < len(self.flujo.documentos):
            return
        cambia = indice != self._activo
        self._activo = indice
        if cambia:
            self._pintar_archivos([d.ruta for d in self.flujo.documentos], indice)
        self._cargar_visor()
        if saltar:
            k = next((k for k, u in enumerate(self._ubic) if u.indice == indice), None)
            if k is not None:
                self._ir_a_aparicion(k)
        self._actualizar_nav()

    def _cargar_visor(self):
        """El documento activo en el visor (por ruta: el procesador lo tacha al guardar)."""
        if not self.flujo.documentos:
            return
        self._activo = max(0, min(self._activo, len(self.flujo.documentos) - 1))
        d = self.flujo.documentos[self._activo]
        if self._visor_ruta != d.ruta:
            if d.tipo == "pdf":
                fuente = d.ruta
                if d.ruta.suffix.lower() in IMAGENES:  # una foto se ve como el PDF en que se convirtió
                    try:
                        fuente = pymupdf.open("pdf", imagen_a_pdf(d.ruta))
                    except Exception:
                        pass
                self.visor.cargar(fuente, texto=d.texto, cajas=getattr(d.documento, "_chars", None))
            else:
                self.visor.cargar_texto(d.texto, d.nombre)
            self._visor_ruta = d.ruta
        self._resaltar_visor()

    def _resaltar_visor(self):
        if self.flujo.sesion is None or self._visor_ruta is None:
            return
        marcados = [v for e in self.flujo.sesion.entidades if e.marcada for v in e.todas_las_variantes()]
        self.visor.resaltar(marcados, self._terminos_sel)

    def _ir_a_aparicion(self, k: int, mostrar: bool = False):
        """Lleva el visor a la aparición `k` del hallazgo seleccionado, en su documento."""
        if not self._ubic or self._ocupado:
            return
        k %= len(self._ubic)
        self._pos_ap = k
        u = self._ubic[k]
        if u.indice != self._activo:
            self._elegir_documento(u.indice, saltar=False)
        if not self.visor.ir_a_posicion(u.inicio, u.fin):  # PDF sin capa de texto: por búsqueda
            n = sum(1 for x in self._ubic[:k] if x.indice == u.indice)
            self.visor.ir_a(self._terminos_sel or [u.valor], n)
        if mostrar:
            self.mostrar_pestana(tr('Documento'))
        self._actualizar_nav()

    def _paso_aparicion(self, delta: int):
        if self._ubic and not self._ocupado:
            self._ir_a_aparicion(self._pos_ap + delta)

    def _actualizar_nav(self):
        n = len(self._ubic)
        self.etiqueta_ap.configure(text=tr('aparición {actual} de {n}', actual=self._pos_ap + 1, n=n) if n else "")
        for b in (self.boton_ap_ant, self.boton_ap_sig):
            b.configure(state="normal" if n > 1 else "disabled")

    def _estilo_tabla(self):
        oscuro = ctk.get_appearance_mode() == "Dark"
        fondo, texto, sel = ("#262521", "#ecebe6", "#5a4523") if oscuro else ("#ffffff", "#23221e", "#efe3cf")
        self._color_linea = "#3a3934" if oscuro else "#e7e4dd"
        self._fondo_categoria = "#2f2e29" if oscuro else "#f5f3ee"
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Anon.Treeview", background=fondo, fieldbackground=fondo, foreground=texto,
                    rowheight=FILA, borderwidth=0, font=(getattr(self, "familia", "TkDefaultFont"), 11))
        s.map("Anon.Treeview", background=[("selected", sel)], foreground=[("selected", texto)])
        s.configure("Anon.Treeview.Heading", background=fondo, foreground=texto, relief="flat",
                    font=(getattr(self, "familia", "TkDefaultFont"), 11, "bold"))

    def _dibujar_cuadricula(self):
        """Cuadrícula tenue: ttk.Treeview no la tiene, se dibuja con líneas de 1 px encima.
        Las filas avanzan de una en una al desplazar, así que las horizontales no se mueven."""
        t = self.tabla
        for linea in self._lineas:
            linea.destroy()
        self._lineas = []
        alto, ancho = t.winfo_height(), t.winfo_width()
        if alto <= 1:
            return
        y0 = next((y for y in range(80) if t.identify_region(4, y) != "heading"), 0)
        color = self._color_linea
        x = 0
        for col in ("#0", "etiqueta"):
            x += t.column(col, "width")
            self._lineas.append(tk.Frame(t, width=1, bg=color))
            self._lineas[-1].place(x=x - 1, y=0, height=alto)
        for y in range(y0 + FILA - 1, alto, FILA):
            self._lineas.append(tk.Frame(t, height=1, bg=color))
            self._lineas[-1].place(x=0, y=y, width=ancho)
        for linea in self._lineas:  # un clic que cae justo en la línea se le pasa a la tabla
            linea.bind("<Button-1>", lambda e: t.event_generate(
                "<Button-1>", x=e.x + e.widget.winfo_x(), y=e.y + e.widget.winfo_y()))
            linea.bind("<Double-Button-1>", lambda e: self._doble_clic_tabla(
                _Punto(e.x + e.widget.winfo_x(), e.y + e.widget.winfo_y())))

    def _mostrar(self, pantalla):
        for p in (self.carga, self.revision):
            p.grid_forget()
        pantalla.grid(row=1, column=0, sticky="nsew")
        if pantalla is self.revision:
            self.caja_ia.grid(row=0, column=1, rowspan=2, padx=(0, 10))
        else:
            self.caja_ia.grid_forget()

    # --- carga -------------------------------------------------------------------

    def _elegir_archivo(self):
        rutas = filedialog.askopenfilenames(title=tr('Elige los documentos'), filetypes=_tipos_archivo())
        if rutas:
            self._cargar(list(rutas))

    def _elegir_para_agregar(self):
        rutas = filedialog.askopenfilenames(title=tr('Agregar al proyecto'), filetypes=_tipos_archivo())
        if rutas:
            self._agregar(list(rutas))

    def _soltar(self, evento):
        rutas = list(self.tk.splitlist(evento.data))
        if not rutas or self._ocupado:
            return
        if self.revision.winfo_ismapped():
            self._agregar(rutas)
        else:
            self._cargar(rutas)

    def _cargar(self, rutas):
        if self._ocupado:
            return
        rutas = [rutas] if isinstance(rutas, (str, Path)) else list(rutas)
        if not rutas:
            return
        que = Path(rutas[0]).name if len(rutas) == 1 else tr('{n} documentos', n=len(rutas))
        self.estado_carga.configure(text=tr('Leyendo {que}…', que=que), text_color=("gray20", "gray85"))
        self.barra_carga.pack(pady=(10, 0))
        self.barra_carga.start()
        # Con una sola ruta, los errores salen tal cual; con varias, dicen qué archivo falló.
        objetivo = rutas[0] if len(rutas) == 1 else rutas
        self._en_segundo_plano(lambda: self.flujo.cargar(objetivo, avance=self._avisar_ocr), self._cargado,
                               self._error_carga)

    def _avisar_ocr(self, nombre: str, pagina: int, total: int):
        """Desde el hilo de la carga: la ventana se actualiza en su propio hilo, por la cola."""
        self._cola.put((self._avance_carga, (nombre, pagina, total)))

    def _avance_carga(self, datos):
        nombre, pagina, total = datos
        texto = tr('{nombre}: página {pagina} de {total} escaneada, leyéndola con OCR (unos segundos por página)…',
                   nombre=nombre, pagina=pagina, total=total)
        self.estado_carga.configure(text=texto)
        self.texto_progreso.configure(text=texto)

    def _fin_barra_carga(self):
        self.barra_carga.stop()
        self.barra_carga.pack_forget()

    def _cargado(self, _):
        _anotar("cargado", len(self.flujo.documentos))
        self._fin_barra_carga()
        self.after(1500, lambda: _anotar("tabla en pantalla", self.tabla.winfo_rootx(), self.tabla.winfo_rooty(),
                                         self.tabla.winfo_width(), self.tabla.winfo_height(),
                                         [self.tabla.bbox(i) for i in self.flujo.sesion.entidades[:2] and
                                          [e.etiqueta for e in self.flujo.sesion.entidades[:2]]]))
        self.estado_carga.configure(text="")
        self._activo = 0
        self._visor_ruta = None
        self._etiqueta_vista = None
        self._ubic, self._terminos_sel = [], []
        self.revisado.set(False)
        self._editado = False
        self._pintar_avisos()
        self._actualizar_boton()
        self.idioma_doc.set(IDIOMAS_DOC.get(self.flujo.idioma, self.flujo.idioma))
        self._mostrar(self.revision)
        self.update_idletasks()  # las fichas y el visor miden su ancho
        self._pintar_archivos([d.ruta for d in self.flujo.documentos], 0)
        self._cargar_visor()
        self._llenar_tabla()
        hay_pdf = any(d.tipo == "pdf" for d in self.flujo.documentos)
        self.mostrar_pestana(tr('Documento') if hay_pdf else tr('Contexto'))

    def _cambiar_idioma_doc(self, nombre: str):
        codigo = next((k for k, v in IDIOMAS_DOC.items() if v == nombre), None)
        if codigo is None or codigo == self.flujo.idioma or self._ocupado:
            return
        if self._editado and not self._confirmar(
                tr('Cambiar el idioma del documento'),
                tr('Se vuelve a leer el documento con las reglas de ese idioma y se pierde la revisión hecha. ¿Seguir?'),
                tr('Cambiar idioma')):
            self.idioma_doc.set(IDIOMAS_DOC.get(self.flujo.idioma, ""))
            return
        self._en_segundo_plano(lambda: self.flujo.cambiar_idioma(codigo), self._cargado, self._error_carga)

    def _error_carga(self, err: Exception):
        _anotar("error de carga", type(err).__name__)
        self._fin_barra_carga()
        registrar_error(type(err), err, err.__traceback__)
        self.estado_carga.configure(text=str(err), text_color=ERROR)

    def _pintar_avisos(self):
        self.avisos.configure(text="\n".join(f"⚠ {a}" for a in self.flujo.avisos))

    def _agregar(self, rutas: list):
        """Suma archivos al proyecto: la revisión hecha se conserva, lo nuevo entra a la lista."""
        if self._ocupado or not rutas:
            return
        self._en_segundo_plano(lambda: self.flujo.agregar(rutas, avance=self._avisar_ocr), self._agregados,
                               lambda err: self._mensaje(tr('No se agregó'), str(err), ERROR))

    def _agregados(self, nuevos):
        if not nuevos:
            return
        self._activo = next(i for i, d in enumerate(self.flujo.documentos) if d is nuevos[0])
        self._revision_cambio()
        self._pintar_archivos([d.ruta for d in self.flujo.documentos], self._activo)
        self._pintar_avisos()
        self._cargar_visor()
        self._llenar_tabla(self._seleccion())

    def _quitar_documento(self, indice: int):
        if self._ocupado or len(self.flujo.documentos) < 2:
            return
        d = self.flujo.documentos[indice]
        if self._editado and not self._confirmar(
                tr('¿Quitar del proyecto?'), tr('«{nombre}» sale del proyecto. Lo que solo aparecía ahí deja la lista; lo demás conserva tu revisión.', nombre=_acortar(d.nombre, 60)), tr('Quitar')):
            return
        self.flujo.quitar(indice)
        if self._activo > indice or self._activo >= len(self.flujo.documentos):
            self._activo -= 1
        self._revision_cambio()
        self._pintar_archivos([x.ruta for x in self.flujo.documentos], self._activo)
        self._pintar_avisos()
        self._cargar_visor()
        self._llenar_tabla(self._seleccion())

    def _volver_a_carga(self):
        if self._ocupado:
            return
        if self._editado and not self._confirmar(
                tr('¿Cambiar de archivo?'), tr('Se pierden los cambios que hiciste en la revisión.'),
                tr('Cambiar de archivo')):
            return
        self.visor.cerrar()
        self._visor_ruta = None
        self._mostrar(self.carga)

    # --- tabla ---------------------------------------------------------------------

    def _llenar_tabla(self, seleccionar: str | None = None):
        abiertas = {self.tabla.item(i, "text").split("  (")[0] for i in self.tabla.get_children()
                    if self.tabla.item(i, "open")}
        self.tabla.delete(*self.tabla.get_children())
        for categoria, entidades in self.flujo.entidades_por_categoria():
            marcadas = sum(e.marcada for e in entidades)
            # El texto empieza con el nombre de la categoría y "  (": así se recuerda cuáles estaban abiertas.
            nombre = tr(categoria)
            padre = self.tabla.insert("", "end", text=tr("{categoria}  ({marcadas} de {total})", categoria=nombre,
                                                         marcadas=marcadas, total=len(entidades)),
                                      open=(not abiertas) or nombre in abiertas, tags=("categoria",))
            for e in entidades:
                marca = MARCA_SI if e.marcada else MARCA_NO
                variantes = e.canonico if len(e.variantes) == 1 else f"{e.canonico}  (+{len(e.variantes) - 1})"
                if e.sugerida:  # al principio: en los datos largos, un aviso al final se cortaría
                    variantes = "✦ " + variantes
                self.tabla.insert(padre, "end", iid=e.etiqueta, text=f"{marca}  {variantes}",
                                  values=(e.marcador, self.flujo.apariciones(e.etiqueta)))
        if seleccionar and self.tabla.exists(seleccionar):
            self.tabla.selection_set(seleccionar)
            self.tabla.see(seleccionar)
        self._mostrar_detalle()
        self.after_idle(self._dibujar_cuadricula)

    def _clic_tabla(self, evento):
        fila = self.tabla.identify_row(evento.y)
        _anotar("clic", evento.x, evento.y, getattr(evento, "num", ""), "fila" if fila else "-")
        if fila and self.tabla.parent(fila) and self.tabla.identify_column(evento.x) == "#0":
            bbox = self.tabla.bbox(fila, "#0")
            if bbox and evento.x < bbox[0] + 48:  # clic sobre la casilla
                self.tabla.selection_set(fila)
                self._alternar_seleccion()
                return "break"
        return None

    def _doble_clic_tabla(self, evento):
        """Doble clic en un hallazgo: Renombrar. El segundo clic de un doble clic solo dispara este
        evento (no `<Button-1>`), así que la casilla no se alterna dos veces; si cae sobre la
        casilla, no se hace nada más. En una categoría queda lo normal (abrir/cerrar)."""
        fila = self.tabla.identify_row(evento.y)
        _anotar("doble_clic", evento.x, evento.y, "fila" if fila else "-", self.tabla.identify_column(evento.x))
        if not fila or not self.tabla.parent(fila):
            return None
        bbox = self.tabla.bbox(fila, "#0")
        if self.tabla.identify_column(evento.x) == "#0" and bbox and evento.x < bbox[0] + 48:
            return "break"
        self.tabla.selection_set(fila)
        self.after(120, self._renombrar)  # cuando ya se soltó el botón del ratón
        return "break"

    def _alternar_seleccion(self):
        etiqueta = self._seleccion()
        if etiqueta and not self._ocupado:
            e = self.flujo.sesion.entidad(etiqueta)
            self.flujo.sesion.marcar(etiqueta, not e.marcada)
            self._revision_cambio()
            self._llenar_tabla(etiqueta)

    def _seleccion(self) -> str | None:
        sel = self.tabla.selection()
        return sel[0] if sel and self.tabla.parent(sel[0]) else None

    def _mostrar_detalle(self):
        """Contexto y visor del hallazgo seleccionado. Al elegir otro hallazgo, el visor salta a
        su primera aparición (en el documento activo si está ahí); al refrescar el mismo (tras
        marcar, renombrar…), solo se repinta."""
        etiqueta = self._seleccion()
        hay = etiqueta is not None
        for b in (self.boton_renombrar, self.boton_unir, self.boton_separar):
            b.configure(state="normal" if hay else "disabled")
        self.contexto.configure(state="normal")
        self.contexto.delete("1.0", "end")
        for t in self.contexto.tag_names():
            if t.startswith("ap"):
                self.contexto.tag_delete(t)
        if not hay:
            self.titulo_detalle.configure(text=tr('Elige un hallazgo para ver dónde aparece'))
            self.titulo_visor.configure(text=tr('Elige un hallazgo para verlo aquí'))
            self.contexto.configure(state="disabled")
            self._ubic, self._terminos_sel, self._etiqueta_vista = [], [], None
            self._resaltar_visor()
            self._actualizar_nav()
            return
        e = self.flujo.sesion.entidad(etiqueta)
        estado = tr('se ocultará') if e.marcada else tr('NO se ocultará')
        self.titulo_detalle.configure(text=tr('{marcador} — {estado}', marcador=e.marcador, estado=estado))
        self.titulo_visor.configure(text=tr('{marcador} — {estado}', marcador=e.marcador, estado=estado))
        if len(e.variantes) > 1:
            self.contexto.insert("end", tr('Variantes: ') + " · ".join(e.variantes) + "\n\n", "tenue")
        contextos = self.flujo.contextos(etiqueta)
        varios = len(self.flujo.documentos) > 1
        por_doc = self.flujo.apariciones_por_documento(etiqueta) if varios else []
        previo = None
        for k, c in enumerate(contextos):
            if varios and c.indice != previo:
                previo = c.indice
                veces = por_doc[c.indice]
                linea = (tr("{documento} · 1 vez\n", documento=c.documento) if veces == 1
                         else tr("{documento} · {veces} veces\n", documento=c.documento, veces=veces))
                self.contexto.insert("end", linea, "archivo")
            tag = f"ap{k}"
            self.contexto.insert("end", c.antes, (tag,))
            self.contexto.insert("end", c.valor, ("valor", tag))
            self.contexto.insert("end", c.despues + "\n\n", (tag,))
            self.contexto.tag_bind(tag, "<Button-1>", lambda _e, k=k: self._ir_a_aparicion(k, mostrar=True))
            self.contexto.tag_bind(tag, "<Enter>", lambda _e: self.contexto.configure(cursor="hand2"))
            self.contexto.tag_bind(tag, "<Leave>", lambda _e: self.contexto.configure(cursor=""))
        if not contextos:
            self.contexto.insert("end", tr('No aparece en el texto de los documentos.'), "tenue")
        self.contexto.configure(state="disabled")
        self.boton_separar.configure(state="normal" if len(e.variantes) > 1 else "disabled")

        self._ubic = self.flujo.ubicaciones(etiqueta)
        self._terminos_sel = e.todas_las_variantes()
        mismo = etiqueta == self._etiqueta_vista
        self._etiqueta_vista = etiqueta
        self._resaltar_visor()
        if mismo or not self._ubic:
            self._pos_ap = max(0, min(self._pos_ap, len(self._ubic) - 1))
            if self._ubic and self._ubic[self._pos_ap].indice != self._activo:  # cambiaron los documentos
                k = next((k for k, u in enumerate(self._ubic) if u.indice == self._activo), None)
                if k is not None:
                    self._ir_a_aparicion(k)
                    return
            self._actualizar_nav()
            return
        k = next((k for k, u in enumerate(self._ubic) if u.indice == self._activo), 0)
        self._ir_a_aparicion(k)

    def _revision_cambio(self):
        """Cualquier cambio obliga a confirmar de nuevo la revisión."""
        self._editado = True
        self.revisado.set(False)
        self._actualizar_boton()

    # --- acciones de revisión ----------------------------------------------------------

    def _agregar_manual(self):
        valor = self.entrada_manual.get().strip()
        if not valor or self._ocupado:
            return
        try:
            e = self.flujo.sesion.agregar_manual(valor)
        except ValueError as err:
            self._mensaje(tr('No se añadió'), str(err), AVISO)
            return
        self.entrada_manual.delete(0, "end")
        self._revision_cambio()
        self._llenar_tabla(e.etiqueta)

    def _texto_boton_ia(self) -> str:
        return tr('■ Detener la IA') if getattr(self, "_ia_tarea", None) else "✦ " + tr('Revisar con IA local')

    def _revisar_con_ia(self):
        if getattr(self, "_ia_tarea", None):
            self._detener_ia()
            return
        if self._ocupado or not self.flujo.documentos:
            return
        from .. import ia_local
        from ..flujo import pedir_sugerencias

        try:
            modelo = ia_local.elegir_modelo()
        except ia_local.FaltaInstalar:
            self._explicar_ia()
            return
        except ia_local.SinIALocal as err:
            self._mensaje(tr('IA local'), str(err), AVISO)
            return
        self.estado_ia = modelo
        tarea = object()  # identifica esta revisión: si se detiene, lo que llegue después se ignora
        self._ia_tarea = tarea
        tapados = self.flujo.textos_tapados()  # aquí, no en el hilo: el hilo no toca la sesión
        self._ocupar(True)
        self.texto_progreso.configure(text=tr('Preparando la IA local ({modelo})…', modelo=modelo))

        def correr():
            try:
                resultado = pedir_sugerencias(
                    tapados, modelo,
                    avance=lambda parte, total: self._cola.put((self._avance_ia, (tarea, parte, total))),
                    cancelado=lambda: self._ia_tarea is not tarea)
                self._cola.put((self._fin_ia, (tarea, resultado, None)))
            except ia_local.Cancelada:
                pass
            except Exception as err:  # se muestra al usuario
                self._cola.put((self._fin_ia, (tarea, None, err)))

        threading.Thread(target=correr, daemon=True).start()

    def _detener_ia(self):
        """Se suelta la revisión en curso: la respuesta que esté esperando se descarta al llegar.
        No se agrega nada de lo que alcanzó a sugerir."""
        self._ia_tarea = None
        self._ocupar(False)

    def _fin_ia(self, datos):
        tarea, sugerencias, error = datos
        if tarea is not getattr(self, "_ia_tarea", None):  # se detuvo: llega tarde
            return
        self._ia_tarea = None
        self._ocupar(False)
        if error is not None:
            self._mensaje(tr('IA local'), str(error), ERROR)
            return
        self._revisado_con_ia(self.flujo.aplicar_sugerencias(sugerencias))

    def _explicar_ia(self):
        """Cómo funciona la revisión con IA y, si falta algo, qué instalar (con los comandos)."""
        from .. import ia_local

        try:
            instalados = ia_local.modelos_instalados()
        except ia_local.SinIALocal:
            instalados = []
        modelo = next((m for m in ia_local.MODELOS_PREFERIDOS if m in instalados), None)
        falta = modelo is None
        v = self._dialogo(tr('Revisión con IA local'), "560x520" if falta else "560x340", self)
        ctk.CTkLabel(v, text="✦ " + tr('Revisión con IA local'), font=ctk.CTkFont(size=16, weight="bold"),
                     text_color=ACENTO).pack(anchor="w", padx=20, pady=(18, 6))
        explica = tr('Es una segunda revisión, después del detector. Una IA lee el documento ya tapado y '
                     'busca lo que se escapó: fechas en letra, folios, números de escritura o de notaría, '
                     'colonias, sellos. Lo que sugiere entra a la lista marcado y con una ✦: tú decides '
                     'qué se queda.') + "\n\n" + tr(
                     'Corre completa en esta computadora, con Ollama: el documento no sale de aquí. Solo '
                     'funciona con gemma3 de 27b (más precisa; pide 32 GB de memoria) o de 12b (cabe en '
                     'una laptop de 16 GB). Es lenta: cerca de un minuto por cada parte del documento.')
        ctk.CTkLabel(v, text=explica, wraplength=520, justify="left", anchor="w").pack(fill="x", padx=20)
        if not falta:
            ctk.CTkLabel(v, text=tr('En esta computadora: {modelo} ✓', modelo=modelo), anchor="w",
                         text_color=OK).pack(fill="x", padx=20, pady=(14, 0))
        else:
            ctk.CTkLabel(v, text=tr('En esta computadora falta instalarla:'), anchor="w", text_color=AVISO,
                         font=ctk.CTkFont(weight="bold")).pack(fill="x", padx=20, pady=(14, 0))

            def paso(texto, comando=None, enlace=None):
                fila = ctk.CTkFrame(v, fg_color="transparent")
                fila.pack(fill="x", padx=20, pady=(8, 0))
                ctk.CTkLabel(fila, text=texto, anchor="w", justify="left").pack(side="left")
                if enlace:
                    Boton3D(fila, text=tr('Abrir ollama.com'), width=0, variante="secundario",
                            command=lambda: webbrowser.open(enlace)).pack(side="right")
                if comando:
                    def copiar():
                        self.clipboard_clear()
                        self.clipboard_append(comando)
                        boton.configure(text=tr('Copiado'))
                    boton = Boton3D(fila, text=tr('Copiar'), width=80, variante="secundario", command=copiar)
                    boton.pack(side="right")
                    ctk.CTkLabel(fila, text=comando, font=ctk.CTkFont(family="Courier", size=13)).pack(
                        side="right", padx=10)

            n = 1
            if not instalados:
                paso(tr('{n}. Instala Ollama (gratis).', n=n), enlace="https://ollama.com/download")
                n += 1
            paso(tr('{n}. En la Terminal, una de dos:', n=n))
            paso("   27b", comando="ollama pull gemma3:27b")
            paso("   12b", comando="ollama pull gemma3:12b")
            ctk.CTkLabel(v, text=tr('Cuando termine la descarga, vuelve a presionar «Revisar con IA local».'),
                         wraplength=520, justify="left", anchor="w", text_color="gray").pack(
                fill="x", padx=20, pady=(12, 0))
        cerrar = Boton3D(v, text=tr('Aceptar'), width=100, command=v.destroy)
        cerrar.pack(side="bottom", anchor="e", padx=20, pady=16)
        v.bind("<Escape>", lambda _e: v.destroy())
        v.after(50, lambda: (v.grab_set(), cerrar.focus_set()))

    def _avance_ia(self, datos):
        tarea, parte, total = datos
        if tarea is not getattr(self, "_ia_tarea", None):
            return
        self.texto_progreso.configure(text=tr('IA local ({modelo}): parte {parte} de {total} · cerca de un '
                                              'minuto cada una', modelo=self.estado_ia, parte=parte, total=total))

    def _revisado_con_ia(self, nuevas):
        if not nuevas:
            self._mensaje(tr('IA local'), tr('La IA local ({modelo}) no encontró nada más que tapar.',
                                             modelo=self.estado_ia), OK)
            return
        self._revision_cambio()
        self._llenar_tabla(nuevas[0].etiqueta)
        self._mensaje(tr('IA local'), tr('La IA local ({modelo}) sugirió {n} datos más. Ya están marcados y llevan '
                                         'una ✦: revísalos y desmarca los que no haga falta tapar.',
                                         modelo=self.estado_ia, n=len(nuevas)), OK)

    def _renombrar(self):
        """Edita la etiqueta en la misma tabla (columna «Se cambia por»): Enter guarda, Esc cancela."""
        etiqueta = self._seleccion()
        if not etiqueta or self._ocupado:
            return
        self._cerrar_edicion()
        t = self.tabla
        t.see(etiqueta)
        t.update_idletasks()
        caja = t.bbox(etiqueta, "etiqueta")
        _anotar("renombrar", "caja", caja)
        if not caja:
            return
        x, y, ancho, alto = caja
        edicion = tk.Entry(t, font=(getattr(self, "familia", "TkDefaultFont"), 11), relief="solid", bd=1,
                           highlightthickness=1, highlightcolor="#b8853a")
        edicion.insert(0, etiqueta)
        edicion.select_range(0, "end")
        edicion.place(x=x, y=y, width=ancho, height=alto)
        edicion.lift()
        edicion.focus_force()
        self._edicion = edicion
        abierta = time.monotonic()

        def guardar(_e=None):
            nueva = edicion.get()
            self._cerrar_edicion()
            self._aplicar_renombre(etiqueta, nueva)
            return "break"

        edicion.bind("<Return>", guardar)
        edicion.bind("<KP_Enter>", guardar)
        edicion.bind("<Escape>", lambda _e: (self._cerrar_edicion(), t.focus_set(), "break")[-1])
        def foco_perdido(_e):
            _anotar("edicion", "foco perdido", round(time.monotonic() - abierta, 3))
            if self._edicion is not edicion:
                return
            if time.monotonic() - abierta < 0.6:  # el foco aún se está acomodando tras el doble clic
                edicion.after(10, edicion.focus_force)
                return
            guardar()  # clic en otra parte: se queda lo escrito, como en una hoja de cálculo

        edicion.bind("<FocusOut>", foco_perdido)
        _anotar("edicion", "abierta", edicion.winfo_ismapped())

    def _cerrar_edicion(self):
        edicion = getattr(self, "_edicion", None)
        self._edicion = None
        if edicion is not None:
            try:
                edicion.destroy()
            except tk.TclError:
                pass

    def _aplicar_renombre(self, etiqueta: str, nueva: str):
        if not nueva or nueva.strip().strip("[]").upper() == etiqueta:
            return
        try:
            final = self.flujo.sesion.renombrar(etiqueta, nueva)
        except ValueError as err:
            self._mensaje(tr('No se pudo renombrar'), str(err), ERROR)
            return
        self._revision_cambio()
        self._llenar_tabla(final)

    def _unir(self):
        etiqueta = self._seleccion()
        if not etiqueta or self._ocupado:
            return
        actual = self.flujo.sesion.entidad(etiqueta)
        otras = [e for e in self.flujo.sesion.entidades if e.etiqueta != etiqueta]
        if not otras:
            return
        opciones = {f"{e.marcador}  {e.canonico}": e.etiqueta for e in otras}
        elegido = self._elegir(tr('Unir hallazgos'), tr('¿Con cuál se une {marcador} ({canonico})?\nQuedará todo bajo la etiqueta que elijas.', marcador=actual.marcador, canonico=actual.canonico), list(opciones))
        if elegido:
            destino = opciones[elegido]
            self.flujo.sesion.fusionar(destino, etiqueta)
            self._revision_cambio()
            self._llenar_tabla(destino)

    def _separar(self):
        etiqueta = self._seleccion()
        if not etiqueta or self._ocupado:
            return
        e = self.flujo.sesion.entidad(etiqueta)
        elegido = self._elegir(tr('Separar variante'), tr('¿Qué variante es otra persona o dato distinto?'), e.variantes[1:] or e.variantes)
        if elegido:
            nueva = self.flujo.sesion.separar(etiqueta, elegido)
            self._revision_cambio()
            self._llenar_tabla(nueva.etiqueta)

    # --- guardado ----------------------------------------------------------------------

    def _actualizar_boton(self):
        listo = self.revisado.get() and not self._ocupado
        self.boton_guardar.configure(state="normal" if listo else "disabled")

    def _guardar(self, carpeta: str | None = None):
        """Escribe todos los documentos anonimizados (cada uno junto a su original, sin pisar
        nada) y UNA tabla. Si ahí no se puede escribir, pide otra carpeta."""
        self.flujo.revisado = True
        formato = "docx" if self.salida.get() == SALIDA_WORD else "original"
        self._en_segundo_plano(lambda: self.flujo.guardar_todos(carpeta, formato=formato), self._guardado,
                               self._error_guardar)

    def _error_guardar(self, err: Exception):
        if isinstance(getattr(err, "causa", err), PermissionError):
            carpeta = filedialog.askdirectory(title=tr('Sin permiso para escribir ahí: elige otra carpeta'))
            if carpeta:
                self._guardar(carpeta)
                return
        self._mensaje(tr('No se pudo guardar'), str(err), ERROR)

    def _guardado(self, r):
        self._ultima_tabla = str(r.tabla)
        self._editado = False  # lo revisado ya quedó en los archivos y en la tabla
        n = len(r.documentos)
        sucios = [d for d in r.documentos if not d.limpio]
        v = self._dialogo(tr('Resultado'), "680x420" if n > 1 else "620x360", self)
        v.grab_set()
        if not sucios:
            titulo, color = tr('Listo'), OK
        elif n == 1:
            titulo, color = tr('Atención: quedaron datos en el archivo'), ERROR
        else:
            titulo, color = tr('Atención: {sucios} de {total} con datos por revisar', sucios=len(sucios), total=n), ERROR
        ctk.CTkLabel(v, text=titulo, font=ctk.CTkFont(size=18, weight="bold"), text_color=color).pack(
            anchor="w", padx=20, pady=(18, 6))
        caja = ctk.CTkTextbox(v, wrap="word", height=200)
        caja.pack(fill="both", expand=True, padx=20)
        caja.tag_config("ok", foreground=caja._apply_appearance_mode(OK))
        caja.tag_config("mal", foreground=caja._apply_appearance_mode(ERROR))
        caja.tag_config("tenue", foreground=caja._apply_appearance_mode(TENUE))
        for d in r.documentos:
            if d.limpio:
                caja.insert("end", "✓  ", "ok")
                caja.insert("end", d.salida.name)
                caja.insert("end", tr('   {sustituciones} sustituciones, sin datos marcados\n', sustituciones=d.sustituciones), "tenue")
            else:
                caja.insert("end", "✗  ", "mal")
                caja.insert("end", d.salida.name)
                caja.insert("end", tr('   quedaron datos originales; se nombró así para que no se comparta por error\n'), "mal")
                for f in d.fugas[:6]:
                    caja.insert("end", f"      • {f.ubicacion}: {f.fragmento}\n", "tenue")
        caja.insert("end", tr('\nTabla: {tabla}  ', tabla=r.tabla.name), ())
        caja.insert("end", tr('(privada: tiene los datos reales; sirve para revertir)\n'), "tenue")
        carpetas = {p.parent for p in (*r.salidas, r.tabla)}
        if len(carpetas) == 1:
            caja.insert("end", tr('Carpeta: {carpeta}\n', carpeta=r.tabla.parent), "tenue")
        if r.avisos:
            caja.insert("end", "\n" + "\n".join(f"⚠ {a}" for a in r.avisos))
        caja.configure(state="disabled")
        botones = ctk.CTkFrame(v, fg_color="transparent")
        botones.pack(fill="x", padx=20, pady=14)
        Boton3D(botones, text=tr('Copiar texto limpio'), command=lambda: self._copiar(r.texto_limpio),
                state="normal" if r.limpio else "disabled").pack(side="left")
        Boton3D(botones, text=tr('Abrir carpeta'), variante="secundario",
                command=lambda: _abrir_carpeta(r.tabla)).pack(side="left", padx=8)
        cerrar = Boton3D(botones, text=tr('Cerrar'), width=90, variante="secundario", command=v.destroy)
        cerrar.pack(side="right")
        v.bind("<Escape>", lambda _e: v.destroy())

    def _copiar(self, texto: str):
        self.clipboard_clear()
        self.clipboard_append(texto)
        self._mensaje(tr('Copiado'), tr('Texto limpio copiado.'), OK)

    # --- revertir ------------------------------------------------------------------------

    def _ventana_revertir(self):
        v = self._dialogo(tr('Revertir respuesta de la IA'), "820x680", self)
        v.grid_columnconfigure(0, weight=1)
        v.grid_rowconfigure(2, weight=1)
        v.grid_rowconfigure(4, weight=1)
        estado = {"tabla": getattr(self, "_ultima_tabla", None), "archivo": None, "datos": None, "pendiente": None}

        fila = ctk.CTkFrame(v, fg_color="transparent")
        fila.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 6))
        etiqueta_tabla = ctk.CTkLabel(fila, text="")
        etiqueta_tabla.pack(side="left")
        Boton3D(fila, text=tr('Elegir tabla…'), variante="secundario",
                command=lambda: poner_tabla(filedialog.askopenfilename(
                    parent=v, title=tr('Tabla de equivalencias'), filetypes=[(tr('Tabla'), "*.json")]))).pack(side="right")

        fila2 = ctk.CTkFrame(v, fg_color="transparent")
        fila2.grid(row=1, column=0, sticky="ew", padx=20)
        texto_entrada = (tr('2. Pega la respuesta de la IA, o arrastra su archivo (.docx, .md, .txt):') if DND_FILES
                         else tr('2. Pega la respuesta de la IA, o abre su archivo (.docx, .md, .txt):'))
        etiqueta_entrada = ctk.CTkLabel(fila2, text=texto_entrada, anchor="w")
        etiqueta_entrada.pack(side="left")
        quitar = Boton3D(fila2, text=tr('Quitar archivo'), variante="secundario", command=lambda: quitar_archivo())
        Boton3D(fila2, text=tr('Abrir archivo…'), variante="secundario",
                command=lambda: abrir(filedialog.askopenfilename(
                    parent=v, title=tr('Respuesta de la IA'),
                    filetypes=[(tr('Respuesta'), "*.docx *.md *.txt"), ("Word", "*.docx"), (tr('Texto'), "*.md *.txt")]))
                ).pack(side="right")
        entrada = ctk.CTkTextbox(v, wrap="word")
        entrada.grid(row=2, column=0, sticky="nsew", padx=20, pady=6)

        fila3 = ctk.CTkFrame(v, fg_color="transparent")
        fila3.grid(row=3, column=0, sticky="ew", padx=20)
        ctk.CTkLabel(fila3, text=tr('3. Vista previa con los datos reales:'), anchor="w").pack(side="left")
        aviso = ctk.CTkLabel(fila3, text="", text_color=AVISO, font=self._sub)
        aviso.pack(side="right")
        salida = ctk.CTkTextbox(v, wrap="word", state="disabled")
        salida.grid(row=4, column=0, sticky="nsew", padx=20, pady=6)

        botones = ctk.CTkFrame(v, fg_color="transparent")
        botones.grid(row=5, column=0, sticky="ew", padx=20, pady=(6, 16))
        guardar = Boton3D(botones, text=tr('Guardar .docx'), command=lambda: guardar_docx())
        guardar.pack(side="left")
        copiar = Boton3D(botones, text=tr('Copiar texto'), variante="secundario", command=lambda: copiar_texto())
        copiar.pack(side="left", padx=8)
        Boton3D(botones, text=tr('Cerrar'), width=90, variante="secundario", command=v.destroy).pack(side="right")
        v.bind("<Escape>", lambda _e: v.destroy())

        def poner_tabla(ruta):
            if not ruta:
                return
            try:
                datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
                revertir_texto("", datos)  # valida que sea una tabla del anonimizador
            except (ValueError, OSError) as err:
                self._mensaje(tr('No es una tabla'), str(err), ERROR, v)
                return
            estado["tabla"], estado["datos"] = ruta, datos
            etiqueta_tabla.configure(text=tr('1. Tabla: {ruta}', ruta=Path(ruta).name))
            actualizar()

        def abrir(ruta):
            if not ruta:
                return
            ruta = Path(ruta)
            if ruta.suffix.lower() == ".json":
                poner_tabla(str(ruta))
                return
            try:
                if ruta.suffix.lower() == ".docx":
                    contenido = texto_de_docx(ruta)
                    estado["archivo"] = ruta
                else:
                    contenido = ruta.read_text(encoding="utf-8-sig")
                    estado["archivo"] = None
                    estado["origen"] = ruta
            except (ValueError, OSError, UnicodeDecodeError, KeyError) as err:
                self._mensaje(tr('No se pudo abrir'), f"{ruta.name}: {err}", ERROR, v)
                return
            entrada.configure(state="normal")
            entrada.delete("1.0", "end")
            entrada.insert("1.0", contenido)
            if estado["archivo"]:  # un .docx se revierte tal cual, con su formato: no se edita aquí
                entrada.configure(state="disabled")
                etiqueta_entrada.configure(text=tr('2. Archivo de Word: {ruta} (conserva su formato)', ruta=ruta.name))
                quitar.pack(side="right", padx=8)
            actualizar()

        def quitar_archivo():
            estado["archivo"] = None
            entrada.configure(state="normal")
            entrada.delete("1.0", "end")
            etiqueta_entrada.configure(text=texto_entrada)
            quitar.pack_forget()
            actualizar()

        def soltar(evento):
            for ruta in v.tk.splitlist(evento.data):
                abrir(ruta)
            return evento.action

        def actualizar(_e=None):
            if estado["pendiente"]:
                v.after_cancel(estado["pendiente"])
            estado["pendiente"] = v.after(250, refrescar)

        def refrescar():
            estado["pendiente"] = None
            texto = entrada.get("1.0", "end-1c")
            listo = bool(estado["datos"] and texto.strip())
            resultado = revertir_texto(texto, estado["datos"]) if listo else ""
            salida.configure(state="normal")
            salida.delete("1.0", "end")
            salida.insert("1.0", resultado if estado["archivo"] else markdown_a_texto(resultado))
            salida.configure(state="disabled")
            desconocidas = etiquetas_desconocidas(texto, estado["datos"]) if listo else []
            aviso.configure(text=(tr('Sin revertir (la tabla no las conoce): {desconocidas}', desconocidas=', '.join(desconocidas[:4]))
                                  + ("…" if len(desconocidas) > 4 else "")) if desconocidas else "")
            for b in (guardar, copiar):
                b.configure(state="normal" if listo else "disabled")

        def guardar_docx():
            if not estado["datos"]:
                self._mensaje(tr('Falta la tabla'), tr('Elige primero el archivo _tabla.json del documento.'), AVISO, v)
                return
            sugerido = nombre_sugerido(estado["archivo"] or estado.get("origen"), estado["tabla"])
            ruta = filedialog.asksaveasfilename(parent=v, title=tr('Guardar respuesta con los datos reales'),
                                                initialdir=str(sugerido.parent), initialfile=sugerido.name,
                                                defaultextension=".docx", filetypes=[("Word", "*.docx")])
            if not ruta:
                return
            try:
                if estado["archivo"]:
                    revertir_docx(estado["archivo"], ruta, estado["datos"])
                else:
                    texto_a_docx(entrada.get("1.0", "end-1c"), ruta, estado["datos"])
            except (ValueError, OSError) as err:
                self._mensaje(tr('No se pudo guardar'), str(err), ERROR, v)
                return
            _abrir(Path(ruta))

        def copiar_texto():
            self.clipboard_clear()
            self.clipboard_append(salida.get("1.0", "end-1c"))
            self._mensaje(tr('Copiado'), tr('Texto con los datos reales copiado.'), OK, v)

        entrada.bind("<<Modified>>", lambda _e: (entrada.edit_modified(False), actualizar()))
        if DND_FILES:
            for destino in (v, entrada._textbox, salida._textbox):
                destino.drop_target_register(DND_FILES)
                destino.dnd_bind("<<Drop>>", soltar)
        if estado["tabla"]:
            poner_tabla(estado["tabla"])
        else:
            etiqueta_tabla.configure(text=tr('1. Elige la tabla de equivalencias (_tabla.json) del documento.'))
            refrescar()

    # --- utilidades ------------------------------------------------------------------

    def _dialogo(self, titulo: str, geometria: str, padre=None) -> ctk.CTkToplevel:
        """Diálogo centrado sobre su ventana y al frente. En Mac, un Toplevel recién creado
        puede quedar detrás de la principal; con su grab activo la app parece congelada."""
        padre = padre or self
        v = ctk.CTkToplevel(padre)
        v.title(titulo)
        ancho, alto = (int(x) for x in geometria.split("x"))
        padre.update_idletasks()
        x = padre.winfo_rootx() + max(0, (padre.winfo_width() - ancho) // 2)
        y = padre.winfo_rooty() + max(0, (padre.winfo_height() - alto) // 3)
        v.geometry(f"{ancho}x{alto}+{x}+{y}")
        v.transient(padre)

        def al_frente():
            try:
                v.deiconify()
                v.lift()
                v.attributes("-topmost", True)
                v.focus_force()
                v.after(300, lambda: v.winfo_exists() and v.attributes("-topmost", False))
            except tk.TclError:  # ya se cerró
                pass

        def redibujar():
            """macOS (Tk 8.6) a veces deja en blanco un Toplevel nuevo hasta que cambia de tamaño:
            un empujón de 1 px lo obliga a pintarse."""
            try:
                v.update_idletasks()
                v.geometry(f"{ancho + 1}x{alto}")
                v.update_idletasks()
                v.geometry(f"{ancho}x{alto}")
            except tk.TclError:
                pass

        v.after(10, al_frente)
        v.after(250, al_frente)  # CTkToplevel reacomoda la ventana tras ~200 ms
        v.after(300, redibujar)
        return v

    def _mensaje(self, titulo: str, texto: str, color=None, padre=None):
        v = self._dialogo(titulo, "460x200", padre or self)
        ctk.CTkLabel(v, text=titulo, font=ctk.CTkFont(size=16, weight="bold"), text_color=color).pack(
            anchor="w", padx=20, pady=(18, 6))
        ctk.CTkLabel(v, text=texto, wraplength=420, justify="left", anchor="w").pack(fill="x", padx=20)
        boton = Boton3D(v, text=tr('Aceptar'), width=100, command=v.destroy)
        boton.pack(side="bottom", anchor="e", padx=20, pady=16)
        v.bind("<Escape>", lambda _e: v.destroy())
        v.after(50, lambda: (v.grab_set(), boton.focus_set()))

    def _confirmar(self, titulo: str, pregunta: str, si: str) -> bool:
        v = self._dialogo(titulo, "460x170", self)
        respuesta = {"si": False}
        ctk.CTkLabel(v, text=titulo, font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=20, pady=(18, 4))
        ctk.CTkLabel(v, text=pregunta, wraplength=420, justify="left", anchor="w").pack(fill="x", padx=20)

        def aceptar():
            respuesta["si"] = True
            v.destroy()

        fila = ctk.CTkFrame(v, fg_color="transparent")
        fila.pack(side="bottom", fill="x", padx=20, pady=16)
        Boton3D(fila, text=si, command=aceptar, width=0).pack(side="right")
        cancelar = Boton3D(fila, text=tr('Cancelar'), width=100, command=v.destroy, variante="secundario")
        cancelar.pack(side="right", padx=8)
        v.bind("<Escape>", lambda _e: v.destroy())
        v.after(50, lambda: (v.grab_set(), cancelar.focus_set()))  # lo seguro, a la mano del Enter
        self.wait_window(v)
        return respuesta["si"]

    def _elegir(self, titulo: str, pregunta: str, opciones: list[str]) -> str | None:
        v = self._dialogo(titulo, "560x220", self)
        resultado = {"valor": None}
        ctk.CTkLabel(v, text=pregunta, wraplength=520, justify="left", anchor="w").pack(fill="x", padx=20, pady=(18, 10))
        var = ctk.StringVar(value=opciones[0])
        ctk.CTkOptionMenu(v, values=opciones, variable=var, width=520, fg_color=ACENTO,
                          button_color=ACENTO_HOVER).pack(padx=20)

        def aceptar():
            resultado["valor"] = var.get()
            v.destroy()

        fila = ctk.CTkFrame(v, fg_color="transparent")
        fila.pack(side="bottom", fill="x", padx=20, pady=16)
        aceptar_b = Boton3D(fila, text=tr('Aceptar'), width=100, command=aceptar)
        aceptar_b.pack(side="right")
        Boton3D(fila, text=tr('Cancelar'), width=100, command=v.destroy, variante="secundario").pack(side="right", padx=8)
        v.bind("<Escape>", lambda _e: v.destroy())
        v.after(50, lambda: (v.grab_set(), aceptar_b.focus_set()))
        self.wait_window(v)
        return resultado["valor"]

    def _cerrar(self):
        """Cerrar con una tarea en curso (la IA local esperando respuesta) trababa la salida:
        Tk se finaliza mientras otro hilo sigue vivo. Si hay tarea, se sale sin esperarla."""
        ocupado = self._ocupado
        self.destroy()
        if ocupado:
            os._exit(0)

    def _en_segundo_plano(self, trabajo, al_terminar, al_fallar):
        self._ocupar(True)

        def correr():
            try:
                self._cola.put((al_terminar, trabajo()))
            except Exception as err:  # se muestra al usuario
                self._cola.put((al_fallar, err))

        threading.Thread(target=correr, daemon=True).start()

    def _atender_cola(self):
        try:
            while True:
                funcion, valor = self._cola.get_nowait()
                if funcion not in (self._avance_ia, self._fin_ia, self._avance_carga):  # avisos a media tarea
                    self._ocupar(False)
                funcion(valor)
        except queue.Empty:
            pass
        self.after(100, self._atender_cola)

    def _ocupar(self, ocupado: bool):
        """Mientras procesa: botones bloqueados y barra de progreso (evita el doble clic)."""
        self._ocupado = ocupado
        estado = "disabled" if ocupado else "normal"
        for b in (self.boton_abrir, self.boton_manual, self.boton_ia, self.check_revisado, self.boton_agregar,
                  self.boton_cambiar, self.menu_idioma_doc):
            b.configure(state=estado)
        if ocupado:
            self.caja_progreso.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))
            self.progreso.start()
            self.configure(cursor="watch")
        else:
            self.progreso.stop()
            self.texto_progreso.configure(text="")
            self.caja_progreso.grid_forget()
            self.configure(cursor="")
        self.boton_ia.configure(text=self._texto_boton_ia(),
                                state="normal" if not ocupado or getattr(self, "_ia_tarea", None) else "disabled")
        self._actualizar_boton()


def _acortar(texto: str, maximo: int) -> str:
    """Corta por en medio: el principio y la extensión del nombre son lo que más dice."""
    if len(texto) <= maximo:
        return texto
    cola = maximo // 3
    return texto[: maximo - cola - 1] + "…" + texto[-cola:]


def _caber(texto: str, fuente, ancho_px: float) -> str:
    """Acorta `texto` (por en medio) hasta que mida `ancho_px` o menos con `fuente`."""
    if ancho_px <= 0 or fuente.measure(texto) <= ancho_px:
        return texto
    maximo = len(texto)
    while maximo > 8 and fuente.measure(_acortar(texto, maximo)) > ancho_px:
        maximo -= 1
    return _acortar(texto, maximo)


def _detalle_archivo(ruta: Path) -> str:
    tipo = {".pdf": "PDF", ".docx": "Word", ".doc": "Word 97-2003", ".odt": "OpenDocument", ".rtf": "RTF",
            ".txt": tr('Texto'), ".md": "Markdown"}.get(ruta.suffix.lower(),
                                                    tr('Imagen') if ruta.suffix.lower() in IMAGENES else ruta.suffix)
    try:
        tam = ruta.stat().st_size
    except OSError:
        return tipo
    medida = f"{tam / 1_048_576:.1f} MB" if tam >= 1_048_576 else f"{max(1, round(tam / 1024))} KB"
    return f"{tipo} · {medida} · {ruta.resolve().parent.name or ruta.resolve().parent}"


def _abrir_carpeta(ruta: Path):
    _abrir(ruta.parent)


def _abrir(ruta: Path):
    """Abre un archivo o carpeta con el programa del sistema (Word, Finder, Explorador…)."""
    if sys.platform == "win32":
        os.startfile(str(ruta))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.run(["open", str(ruta)], check=False)
    else:
        subprocess.run(["xdg-open", str(ruta)], check=False)


class _Punto:
    def __init__(self, x, y):
        self.x, self.y = x, y


def registrar_error(tipo, valor, rastro) -> Path:
    """Anota el error en errores.log, junto a las preferencias. Solo el rastro del código:
    los mensajes pueden traer el nombre del archivo, pero nunca su contenido."""
    ruta = preferencias._carpeta() / "errores.log"
    try:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(f"--- {time.strftime('%Y-%m-%d %H:%M:%S')} · {sys.platform}\n")
            f.write("".join(traceback.format_exception(tipo, valor, rastro)))
    except OSError:
        pass
    return ruta


def main(rutas: list[str] | None = None) -> None:
    ventana = Ventana()
    if rutas:
        ventana.after(300, lambda: ventana._cargar(rutas))
    ventana.mainloop()
