"""Idioma de la interfaz: tr("texto en español") devuelve el texto en el idioma elegido.

El español es el texto fuente (lo que está escrito en el código); cada catálogo (textos_en.py,
textos_cs.py) traduce de ahí. Lo que no está en un catálogo sale en español, así que un texto
nuevo nunca rompe nada: solo queda sin traducir (tests/test_textos.py dice cuáles faltan).

    tr("Copiar texto")                 → "Copy text"
    tr("{n} documentos", n=3)          → "3 documents"

Al escribir un texto nuevo en la interfaz: envolverlo en tr(), con los valores variables como
{nombre} y pasados por nombre (no f-strings), y agregarlo a los catálogos.

El idioma de la interfaz es independiente del idioma del documento: un abogado mexicano puede
anonimizar un contrato en inglés con la ventana en español. Se guarda en preferencias
("idioma_ui"); si no hay, se toma el del sistema. Cambiarlo rehace la ventana al momento, sin perder el trabajo.
"""

from __future__ import annotations

import locale
import os
import sys
from functools import lru_cache

from . import preferencias

IDIOMAS_UI = {"es": "Español", "en": "English", "cs": "Čeština"}
_actual: str | None = None


def _idioma_del_sistema() -> str:
    codigo = ""
    try:
        if sys.platform == "win32":
            import ctypes

            codigo = locale.windows_locale.get(ctypes.windll.kernel32.GetUserDefaultUILanguage(), "")
        else:
            codigo = locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        pass
    codigo = (codigo or "").lower()
    if codigo.startswith("es") or not codigo:
        return "es"
    if codigo.startswith(("cs", "sk")):
        return "cs"
    return "en"


def _disponible(idioma: str) -> str:
    """Un idioma sin catálogo todavía cae a inglés (o a español si no hay ni ese)."""
    if idioma == "es" or catalogo(idioma):
        return idioma
    return "en" if catalogo("en") else "es"


def idioma_ui() -> str:
    global _actual
    if _actual is None:
        elegido = os.environ.get("ANONIMIZADOR_IDIOMA_UI") or preferencias.leer("idioma_ui")
        _actual = _disponible(elegido if elegido in IDIOMAS_UI else _idioma_del_sistema())
    return _actual


def poner_idioma_ui(idioma: str, guardar: bool = True, ahora: bool = True) -> None:
    """`ahora=False`: solo se guarda (la ventana abierta sigue en su idioma, sin mezclar)."""
    global _actual
    if idioma not in IDIOMAS_UI:
        raise ValueError(idioma)
    if ahora:
        _actual = _disponible(idioma)
    if guardar:
        preferencias.guardar("idioma_ui", idioma)


@lru_cache(maxsize=None)
def catalogo(idioma: str) -> dict[str, str]:
    # Importes explícitos (no dinámicos): PyInstaller solo empaqueta lo que ve importado.
    try:
        if idioma == "en":
            from .textos_en import TEXTOS
        elif idioma == "cs":
            from .textos_cs import TEXTOS
        else:
            return {}
    except ImportError:
        return {}
    return TEXTOS


def tr(texto: str, **valores) -> str:
    return traducir(idioma_ui(), texto, **valores)


def traducir(idioma: str, texto: str, **valores) -> str:
    """Como tr(), pero a un idioma dado (p. ej. avisar en el idioma recién elegido)."""
    idioma = _disponible(idioma)
    traducido = texto if idioma == "es" else catalogo(idioma).get(texto, texto)
    return traducido.format(**valores) if valores else traducido
