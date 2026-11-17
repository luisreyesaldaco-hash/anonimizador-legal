"""Flujo de trabajo de la app, sin interfaz: lo usa la ventana y se prueba sin pantalla.

Un flujo es un "proyecto": uno o varios documentos con UNA sola revisión y UNA sola tabla
de equivalencias, para que [PERSONA_1] sea la misma persona en el contrato y en la renuncia.

Cómo se arma la sesión común: cada documento se pasa por el detector por separado (así
ninguna regla del detector ve dos documentos a la vez) y los hallazgos se recorren a su
posición dentro de un texto combinado, donde los documentos van unidos por `SEPARADOR`.
El separador no es espacio ni letra, así que ningún nombre ni identificador puede
"empalmarse" entre el final de un documento y el principio del siguiente, y es más largo
que las ventanas de contexto de las reglas de agrupación (tratamientos, apellidos,
empresas que son parte), que por eso nunca miran el documento de al lado. Todo lo que
se calcula por documento (apariciones, contextos, guardado, texto limpio) se hace sobre
el texto de cada documento, con las entidades compartidas.
"""

from __future__ import annotations

import dataclasses
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .detector import detectar, ner_disponible
from .detector import modelo as m
from .idioma import IDIOMAS, detectar_idioma
from .procesadores import abrir, extension_salida, marcar_si_hay_fugas, ruta_tabla, rutas_salida
from .procesadores.pdf import DocumentoPDF
from .procesadores.texto import DocumentoTexto
from .seudonimos import MANUAL, Entidad, Sesion, aplicar, etiquetas_desconocidas, localizar, revertir
from .textos import tr

CATEGORIAS: list[tuple[str, set[str]]] = [
    ("Personas", {m.NOMBRE}),
    ("Empresas", {m.EMPRESA}),
    ("Identificaciones", {m.CURP, m.RFC, m.NSS, m.INE, m.RODNE_CISLO, m.ICO, m.DIC, m.SSN, m.NINO}),
    ("Datos bancarios", {m.CLABE, m.TARJETA, m.CUENTA}),
    ("Contacto", {m.CORREO, m.TELEFONO, m.WEB}),
    ("Domicilios", {m.DOMICILIO}),
    ("Expedientes, folios y placas", {m.EXPEDIENTE, m.FOLIO, m.PLACA}),
    ("Fechas y montos", {m.FECHA, m.MONTO}),
    ("Agregados a mano", {MANUAL}),
]

# U+2063 (separador invisible): no es espacio (\s no lo cruza) ni letra (es límite de palabra).
SEPARADOR = "\n\n" + "⁣" * 120 + "\n\n"


def categoria(tipo: str) -> str:
    return next((nombre for nombre, tipos in CATEGORIAS if tipo in tipos), "Otros")


@dataclass(frozen=True)
class Contexto:
    antes: str
    valor: str
    despues: str
    documento: str = ""  # nombre del archivo donde está esta aparición
    indice: int = 0  # posición del documento en `Flujo.documentos`


@dataclass(frozen=True)
class Ubicacion:
    """Dónde está una aparición, para que un visor salte al documento y lugar correctos."""
    indice: int  # posición del documento en `Flujo.documentos`
    documento: str  # nombre del archivo
    inicio: int  # posición en el texto de ESE documento (`DocumentoCargado.texto`)
    fin: int
    valor: str  # el texto tal como aparece
    pagina: int | None = None  # página (desde 1) en los PDF; None en Word


@dataclass
class DocumentoCargado:
    ruta: Path
    documento: object  # DocumentoPDF | DocumentoWord
    inicio: int = 0  # dónde empieza su texto dentro del texto combinado de la sesión
    usado: bool = False  # guardar() modifica el documento en memoria: para volver a guardar se reabre
    idioma: str = "es"  # "es", "cs" o "en": con qué paquete se detectó

    @property
    def nombre(self) -> str:
        return self.ruta.name

    @property
    def tipo(self) -> str:
        """'pdf' (también una imagen, que se lee como PDF), 'texto' (.txt, .md) o 'docx' (un .doc,
        .odt o .rtf se convierte y se trata como 'docx')."""
        if isinstance(self.documento, DocumentoPDF):
            return "pdf"
        return "texto" if isinstance(self.documento, DocumentoTexto) else "docx"

    @property
    def texto(self) -> str:
        return self.documento.texto

    @property
    def fin(self) -> int:
        return self.inicio + len(self.texto)

    @property
    def avisos(self) -> list[str]:
        avisos = list(self.documento.avisos)
        if not self.texto.strip():
            avisos.append(tr('No se encontró texto en el documento.'))
        return avisos


@dataclass
class Resultado:
    salida: Path
    tabla: Path
    sustituciones: int
    limpio: bool
    fugas: list
    avisos: list[str]
    texto_limpio: str


@dataclass
class ResultadoDocumento:
    nombre: str  # del original
    original: Path
    salida: Path  # ya con _CON_DATOS_REVISAR si la verificación encontró datos
    sustituciones: int
    limpio: bool
    fugas: list
    avisos: list[str]
    texto_limpio: str


@dataclass
class ResultadoProyecto:
    documentos: list[ResultadoDocumento]
    tabla: Path
    texto_limpio: str  # todos, con un encabezado por documento (para "Copiar texto limpio")
    avisos_generales: list[str] = field(default_factory=list)

    @property
    def salidas(self) -> list[Path]:
        return [d.salida for d in self.documentos]

    @property
    def limpio(self) -> bool:
        return all(d.limpio for d in self.documentos)

    @property
    def sustituciones(self) -> int:
        return sum(d.sustituciones for d in self.documentos)

    @property
    def fugas(self) -> list:
        """Las de todos, con el nombre del documento al frente de la ubicación."""
        varios = len(self.documentos) > 1
        return [dataclasses.replace(f, ubicacion=f"{d.nombre}, {f.ubicacion}") if varios else f
                for d in self.documentos for f in d.fugas]

    @property
    def avisos(self) -> list[str]:
        varios = len(self.documentos) > 1
        return self.avisos_generales + [f"{d.nombre}: {a}" if varios else a for d in self.documentos for a in d.avisos]


def avisos_de_idioma(idiomas: set[str], usar_ner: bool = True) -> list[str]:
    """Qué advertir según los paquetes de idioma que usó la detección."""
    avisos = []
    if not usar_ner:
        return avisos
    if "cs" in idiomas:
        from .detector import cs

        if not cs.modelo_disponible():
            avisos.append(tr("El modelo checo de nombres no está instalado; solo se usan reglas. Revisa los nombres con cuidado."))
    if "en" in idiomas:
        from .detector import en

        if not en.modelo_disponible():
            avisos.append(tr("El modelo inglés de nombres no está instalado; solo se usan reglas. Revisa los nombres con cuidado."))
    if idiomas - {"cs", "en"} and not ner_disponible():
        avisos.append(tr("El detector de nombres avanzado no está disponible; revisa con más cuidado los nombres."))
    return avisos


class ErrorDeDocumento(Exception):
    """Un documento del proyecto no se pudo abrir o guardar. `ruta` dice cuál; el mensaje
    también (empieza con el nombre del archivo si el error original no lo traía)."""

    def __init__(self, ruta: Path, causa: Exception):
        self.ruta = Path(ruta)
        self.causa = causa
        texto = str(causa)
        super().__init__(texto if self.ruta.name in texto else f"{self.ruta.name}: {texto}")


class Flujo:
    def __init__(self, usar_ner: bool = True, usar_ocr: bool = True, idioma: str | None = None):
        self.documentos: list[DocumentoCargado] = []
        self.sesion: Sesion | None = None
        self.revisado = False
        self.usar_ner = usar_ner
        self.usar_ocr = usar_ocr
        self.idioma_forzado = idioma  # None = cada documento se detecta solo

    # Compatibilidad con la ventana de un solo documento: el primero del proyecto.
    @property
    def ruta(self) -> Path | None:
        return self.documentos[0].ruta if self.documentos else None

    @property
    def documento(self):
        return self.documentos[0].documento if self.documentos else None

    # --- carga ---------------------------------------------------------------

    def cargar(self, rutas: str | Path | Iterable[str | Path], avance=None) -> None:
        """Abre uno o varios documentos como un proyecto nuevo (descarta el anterior).

        Con una sola ruta, los errores al abrir salen tal cual (como siempre); con una lista,
        como `ErrorDeDocumento`, que dice cuál falló. Si uno falla no se carga ninguno.
        `avance(nombre, pagina, total)`: cada página escaneada que se lee con OCR."""
        varios = not isinstance(rutas, (str, Path))
        lista = [Path(r) for r in rutas] if varios else [Path(rutas)]
        if not lista:
            raise ValueError(tr('Elige al menos un documento.'))
        self._sin_repetidos(lista)
        docs = [self._abrir(r, envolver=varios, avance=avance) for r in lista]
        hallazgos = []
        pos = 0
        for d in docs:
            d.inicio = pos
            hallazgos += [dataclasses.replace(h, inicio=h.inicio + pos, fin=h.fin + pos) for h in self._detectar(d)]
            pos += len(d.texto) + len(SEPARADOR)
        self.documentos = docs
        self.sesion = Sesion(self._texto_combinado(), hallazgos, idioma=self.idioma)
        self.revisado = False

    def agregar(self, rutas: str | Path | Iterable[str | Path], avance=None) -> list[DocumentoCargado]:
        """Suma documentos al proyecto cargado conservando la revisión hecha (marcas, etiquetas,
        uniones, separaciones y agregados a mano); lo nuevo que encuentre el detector entra con
        etiquetas nuevas. La revisión queda pendiente otra vez. Si uno falla no se agrega ninguno."""
        if self.sesion is None:
            self.cargar(rutas, avance)
            return list(self.documentos)
        lista = [Path(rutas)] if isinstance(rutas, (str, Path)) else [Path(r) for r in rutas]
        self._sin_repetidos([d.ruta for d in self.documentos] + lista)
        nuevos = [self._abrir(r, envolver=True, avance=avance) for r in lista]
        for d in nuevos:
            self.documentos.append(d)
            self._recalcular_posiciones()
            self.sesion.incorporar(d.texto, self._detectar(d), self._texto_combinado())
        self.revisado = False
        return nuevos

    def quitar(self, documento: int | str | Path) -> DocumentoCargado:
        """Saca un documento del proyecto (por índice o ruta). Las entidades que solo aparecían
        ahí se retiran; las demás conservan su revisión."""
        d = self._buscar(documento)
        if len(self.documentos) == 1:
            raise ValueError(tr('El proyecto necesita al menos un documento.'))
        self.documentos.remove(d)
        self._recalcular_posiciones()
        self.sesion.retirar_ausentes(self._texto_combinado())
        return d

    def _abrir(self, ruta: Path, envolver: bool, avance=None) -> DocumentoCargado:
        por_pagina = (lambda pagina, total: avance(ruta.name, pagina, total)) if avance else None
        try:
            d = DocumentoCargado(ruta, abrir(ruta, usar_ocr=self.usar_ocr, avance=por_pagina))
        except Exception as err:
            if envolver:
                raise ErrorDeDocumento(ruta, err) from err
            raise
        d.idioma = self.idioma_forzado or detectar_idioma(d.texto)
        return d

    def _detectar(self, d: DocumentoCargado):
        return detectar(d.texto, usar_ner=self.usar_ner, idioma=d.idioma)

    @property
    def idioma(self) -> str:
        """El del proyecto: el elegido a mano o, si no, el que más texto tiene."""
        if self.idioma_forzado:
            return self.idioma_forzado
        peso: dict[str, int] = {}
        for d in self.documentos:
            peso[d.idioma] = peso.get(d.idioma, 0) + len(d.texto)
        return max(peso, key=peso.get) if peso else "es"

    def cambiar_idioma(self, idioma: str | None) -> None:
        """Vuelve a abrir el proyecto con otro idioma (None = detectar). Descarta la revisión."""
        if idioma is not None and idioma not in IDIOMAS:
            raise ValueError(f"Idioma desconocido: {idioma}")
        self.idioma_forzado = idioma
        if self.documentos:
            rutas = [d.ruta for d in self.documentos]
            self.cargar(rutas if len(rutas) > 1 else rutas[0])

    @staticmethod
    def _sin_repetidos(rutas: list[Path]) -> None:
        vistas: set[Path] = set()
        for r in rutas:
            k = r.resolve()
            if k in vistas:
                raise ValueError(tr('{r} ya está en el proyecto.', r=r.name))
            vistas.add(k)

    def _buscar(self, documento: int | str | Path) -> DocumentoCargado:
        if isinstance(documento, int):
            return self.documentos[documento]
        k = Path(documento).resolve()
        for d in self.documentos:
            if d.ruta.resolve() == k:
                return d
        raise KeyError(str(documento))

    def _recalcular_posiciones(self) -> None:
        pos = 0
        for d in self.documentos:
            d.inicio = pos
            pos += len(d.texto) + len(SEPARADOR)

    def _texto_combinado(self) -> str:
        return SEPARADOR.join(d.texto for d in self.documentos)

    @property
    def avisos(self) -> list[str]:
        varios = len(self.documentos) > 1
        avisos = [f"{d.nombre}: {a}" if varios else a for d in self.documentos for a in d.avisos]
        avisos += avisos_de_idioma({d.idioma for d in self.documentos} or {"es"}, self.usar_ner)
        return avisos

    # --- revisión ------------------------------------------------------------

    def entidades_por_categoria(self) -> list[tuple[str, list[Entidad]]]:
        grupos: dict[str, list[Entidad]] = {}
        for e in self.sesion.entidades:
            grupos.setdefault(categoria(e.tipo), []).append(e)
        orden = [c for c, _ in CATEGORIAS] + ["Otros"]
        return [(c, sorted(grupos[c], key=lambda e: _orden_etiqueta(e.etiqueta))) for c in orden if c in grupos]

    def texto_tapado(self, indice: int) -> str:
        """El texto del documento `indice` con lo marcado ya sustituido por su etiqueta."""
        return texto_tapado(self.documentos[indice].texto, self.sesion)

    def textos_tapados(self) -> list[str]:
        return [texto_tapado(d.texto, self.sesion) for d in self.documentos]

    def aplicar_sugerencias(self, sugerencias: list) -> list[Entidad]:
        nuevas = aplicar_sugerencias(self.sesion, sugerencias)
        if nuevas:
            self.revisado = False
        return nuevas

    def sugerir_con_ia(self, modelo: str | None = None, avance=None) -> list[Entidad]:
        """Segunda revisión con la IA local (ver ia_local). Devuelve los hallazgos nuevos."""
        nuevas = sugerir_con_ia(self.sesion, [d.texto for d in self.documentos], modelo, avance)
        if nuevas:
            self.revisado = False
        return nuevas

    def contextos(self, etiqueta: str, ancho: int = 60) -> list[Contexto]:
        """Cada aparición con su contexto, documento por documento y en orden."""
        e = self.sesion.entidad(etiqueta)
        salida = []
        for i, d in enumerate(self.documentos):
            texto = d.texto
            for a in localizar(texto, [e], solo_marcadas=False):
                antes = texto[max(0, a.inicio - ancho):a.inicio]
                despues = texto[a.fin:a.fin + ancho]
                salida.append(Contexto(_una_linea(antes, izquierda=True), texto[a.inicio:a.fin], _una_linea(despues),
                                       d.nombre, i))
        return salida

    def apariciones(self, etiqueta: str) -> int:
        return sum(self.apariciones_por_documento(etiqueta))

    def apariciones_por_documento(self, etiqueta: str) -> list[int]:
        """Cuántas veces aparece en cada documento, en el orden de `documentos`."""
        e = self.sesion.entidad(etiqueta)
        return [len(localizar(d.texto, [e], solo_marcadas=False)) for d in self.documentos]

    def ubicaciones(self, etiqueta: str) -> list[Ubicacion]:
        """Todas las apariciones con documento, posición en su texto y página (PDF)."""
        e = self.sesion.entidad(etiqueta)
        salida = []
        for i, d in enumerate(self.documentos):
            pagina = d.documento.pagina_de if isinstance(d.documento, DocumentoPDF) else (lambda _p: None)
            for a in localizar(d.texto, [e], solo_marcadas=False):
                salida.append(Ubicacion(i, d.nombre, a.inicio, a.fin, d.texto[a.inicio:a.fin], pagina(a.inicio)))
        return salida

    # --- guardado ------------------------------------------------------------

    def rutas_sugeridas(self) -> tuple[Path, Path]:
        return rutas_salida(self.ruta, extension_salida(self.documento))

    def guardar(self, salida: str | Path) -> Resultado:
        """Proyecto de un solo documento: lo guarda en `salida` (y la tabla junto a él)."""
        if len(self.documentos) != 1:
            raise ValueError("El proyecto tiene varios documentos: usa guardar_todos().")
        if not self.revisado:
            raise ValueError(tr('Primero revisa los hallazgos y confirma la revisión.'))
        salida = Path(salida)
        if salida.resolve() == self.ruta.resolve():
            raise ValueError(tr('No se puede sobrescribir el documento original. Elige otro nombre.'))
        d = self._listo_para_guardar(self.documentos[0])
        tabla = ruta_tabla(salida)
        informe = _guardar_documento(d.documento, salida, self.sesion.entidades)
        datos = self.sesion.tabla(self.ruta, self.ruta.read_bytes())
        tabla.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
        final = marcar_si_hay_fugas(informe.salida, informe.limpio)
        return Resultado(final, tabla, informe.apariciones, informe.limpio, informe.verificacion.fugas,
                         informe.avisos, d.documento.texto_limpio(self.sesion.entidades))

    def guardar_todos(self, carpeta: str | Path | None = None, tabla: str | Path | None = None,
                      formato: str = "original") -> ResultadoProyecto:
        """Escribe cada documento anonimizado y UNA tabla con todas las etiquetas.

        Sin `carpeta`, cada salida va junto a su original (documento_anonimizado.ext, sin pisar
        nada). La tabla va junto a la primera salida: con un solo documento se llama como la de
        `guardar` (documento_tabla.json); con varios, primero_proyecto_tabla.json. `tabla`
        permite elegir su ruta exacta. `formato`: "original" (cada uno en su formato) o
        "docx" (todo sale en Word: un PDF o una imagen pierden el diseño, no el texto)."""
        if formato not in ("original", "docx"):
            raise ValueError(tr('Formato de salida desconocido: {formato}', formato=formato))
        if not self.revisado:
            raise ValueError(tr('Primero revisa los hallazgos y confirma la revisión.'))
        if not self.documentos:
            raise ValueError(tr('No hay documentos cargados.'))
        if carpeta is not None:
            Path(carpeta).mkdir(parents=True, exist_ok=True)
        originales = {d.ruta.resolve() for d in self.documentos}
        salidas: list[Path] = []
        for d in self.documentos:
            salidas.append(_salida_libre(d.ruta, extension_salida(d.documento, formato), carpeta, salidas, originales))
        if tabla is not None:
            ruta_t = Path(tabla)
            if ruta_t.resolve() in originales | {s.resolve() for s in salidas}:
                raise ValueError(tr('La tabla no puede ocupar el lugar de un documento.'))
        elif len(self.documentos) == 1:
            ruta_t = ruta_tabla(salidas[0])
        else:
            ruta_t = _libre(salidas[0].with_name(f"{self.documentos[0].ruta.stem}_proyecto_tabla.json"))

        # La tabla primero: si un documento falla a medias, lo ya escrito se puede revertir.
        entidades = self.sesion.entidades
        primero = self.documentos[0].ruta
        datos = self.sesion.tabla(primero, primero.read_bytes())
        datos["documentos"] = [
            {"archivo": d.nombre, "sha256": _sha256(d.ruta), "salida": s.name}
            for d, s in zip(self.documentos, salidas)
        ]
        ruta_t.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")

        resultados = []
        for d, salida in zip(self.documentos, salidas):
            d = self._listo_para_guardar(d)
            try:
                informe = _guardar_documento(d.documento, salida, entidades)
            except Exception as err:
                raise ErrorDeDocumento(d.ruta, err) from err
            final = marcar_si_hay_fugas(informe.salida, informe.limpio)
            resultados.append(ResultadoDocumento(d.nombre, d.ruta, final, informe.apariciones, informe.limpio,
                                                 informe.verificacion.fugas, informe.avisos,
                                                 d.documento.texto_limpio(entidades)))
        avisos = avisos_de_idioma({d.idioma for d in self.documentos} or {"es"}, self.usar_ner)
        return ResultadoProyecto(resultados, ruta_t, self._texto_limpio_combinado(resultados), avisos)

    def _listo_para_guardar(self, d: DocumentoCargado) -> DocumentoCargado:
        """Guardar redacta el documento en memoria; para guardarlo otra vez se reabre del disco."""
        if d.usado:
            d.documento = abrir(d.ruta, usar_ocr=self.usar_ocr)
        d.usado = True
        return d

    def _texto_limpio_combinado(self, resultados: list[ResultadoDocumento]) -> str:
        if len(resultados) == 1:
            return resultados[0].texto_limpio
        n = len(resultados)
        partes = [tr('===== Documento {i} de {n}: {nombre} =====\n\n{texto_limpio}', i=i, n=n, nombre=self._nombre_limpio(r.nombre), texto_limpio=r.texto_limpio.strip())
                  for i, r in enumerate(resultados, 1)]
        return "\n\n".join(partes) + "\n"

    def _nombre_limpio(self, nombre: str) -> str:
        """El nombre del archivo va a la IA: se le aplican las mismas sustituciones."""
        legible = re.sub(r"[_]+", " ", nombre)
        marcadas = [e for e in self.sesion.entidades if e.marcada]
        return aplicar(legible, localizar(legible, self.sesion.entidades), marcadas)


def texto_tapado(texto: str, sesion: Sesion) -> str:
    marcadas = [e for e in sesion.entidades if e.marcada]
    return aplicar(texto, localizar(texto, sesion.entidades), marcadas)


def pedir_sugerencias(tapados: list[str], modelo: str, avance=None, cancelado=None) -> list:
    """Solo consulta a la IA (puede ir en un hilo aparte): no toca la sesión.

    `avance(parte, total)` cuenta las consultas (cada una tarda del orden de un minuto)."""
    from . import ia_local

    total = sum(len(ia_local.trozos(t)) for t in tapados)
    cuenta = [0]

    def siguiente():
        cuenta[0] += 1
        if avance:
            avance(cuenta[0], total)

    sugerencias = []
    for t in tapados:
        sugerencias += ia_local.sugerir(t, modelo, avance=siguiente, cancelado=cancelado)
    return sugerencias


def aplicar_sugerencias(sesion: Sesion, sugerencias: list) -> list[Entidad]:
    """Lo que sugirió la IA y aparece en el documento entra como hallazgo nuevo, marcado y con
    `sugerida=True`."""
    nuevas: list[Entidad] = []
    for s in sugerencias:
        antes = {id(e) for e in sesion.entidades}
        e = None
        # Un folio con comas o signos («84,215», un sello en base64) no casa con la búsqueda
        # de identificadores: entonces entra tal cual, como agregado a mano.
        for tipo in dict.fromkeys((s.tipo, MANUAL)):
            try:
                e = sesion.agregar_manual(s.texto, tipo)
                break
            except ValueError:
                continue
        if e is not None and id(e) not in antes:
            e.sugerida = True
            nuevas.append(e)
    return nuevas


def sugerir_con_ia(sesion: Sesion, textos: list[str], modelo: str | None = None,
                   avance=None) -> list[Entidad]:
    """Pasa cada texto, ya tapado, por la IA local y agrega lo que sugiera (ver arriba)."""
    from . import ia_local

    modelo = modelo or ia_local.elegir_modelo()
    tapados = [texto_tapado(t, sesion) for t in textos]
    return aplicar_sugerencias(sesion, pedir_sugerencias(tapados, modelo, avance))


def _guardar_documento(documento, salida: Path, entidades):
    """Un PDF, una imagen o un texto que se pide en .docx va por su salida en Word."""
    if Path(salida).suffix.lower() == ".docx" and hasattr(documento, "guardar_word"):
        return documento.guardar_word(salida, entidades)
    return documento.guardar(salida, entidades)


def revertir_con_archivo(tabla: str | Path, texto: str) -> tuple[str, list[str]]:
    """Devuelve la respuesta con los valores reales y las etiquetas que la tabla no conoce."""
    datos = json.loads(Path(tabla).read_text(encoding="utf-8"))
    return revertir(texto, datos), etiquetas_desconocidas(texto, datos)


def _sha256(ruta: Path) -> str:
    import hashlib

    return hashlib.sha256(ruta.read_bytes()).hexdigest()


def _salida_libre(original: Path, extension: str, carpeta, reservadas: list[Path], originales: set[Path]) -> Path:
    """documento.pdf → documento_anonimizado.pdf (en `carpeta` o junto al original), sin pisar
    nada que exista, ni otra salida de este mismo guardado, ni un original."""
    base = Path(carpeta) / original.name if carpeta is not None else original
    n = 1
    while True:
        salida = base.with_name(f"{base.stem}_anonimizado{'' if n == 1 else f'_{n}'}{extension}")
        if not salida.exists() and salida not in reservadas and salida.resolve() not in originales:
            return salida
        n += 1


def _libre(ruta: Path) -> Path:
    n = 1
    while True:
        candidata = ruta if n == 1 else ruta.with_name(f"{ruta.stem}_{n}{ruta.suffix}")
        if not candidata.exists():
            return candidata
        n += 1


def _una_linea(s: str, izquierda: bool = False) -> str:
    s = re.sub(r"\s+", " ", s)
    return ("…" + s.lstrip()) if izquierda else (s.rstrip() + "…")


def _orden_etiqueta(etiqueta: str):
    m_ = re.match(r"(.*?)_(\d+)$", etiqueta)
    return (m_.group(1), int(m_.group(2))) if m_ else (etiqueta, 0)
