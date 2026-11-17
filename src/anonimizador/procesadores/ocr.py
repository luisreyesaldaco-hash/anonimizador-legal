"""OCR local con Tesseract (vía PyMuPDF) para páginas escaneadas.

PyMuPDF trae Tesseract adentro: solo hace falta el archivo del idioma
(spa.traineddata). Los paquetes de Windows y Mac lo traen en una carpeta propia;
aquí se busca primero esa carpeta y después la instalación del sistema.
"""

from __future__ import annotations

import functools
import os
import sys
from pathlib import Path

import pymupdf

IDIOMA = "spa"  # el que debe estar siempre
EXTRA = ("ces", "eng")  # paquetes de idioma: se usan si su archivo está instalado
DPI = 300


def _carpetas_candidatas() -> list[Path]:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[3]))
    return [base / "tesseract" / "tessdata", base / "vendor" / "tesseract" / "tessdata"]


@functools.lru_cache(maxsize=1)
def tessdata() -> str | None:
    if os.environ.get("TESSDATA_PREFIX") and (Path(os.environ["TESSDATA_PREFIX"]) / f"{IDIOMA}.traineddata").exists():
        return os.environ["TESSDATA_PREFIX"]
    for c in _carpetas_candidatas():
        if (c / f"{IDIOMA}.traineddata").exists():
            return str(c)
    try:
        encontrado = pymupdf.get_tessdata()
    except Exception:
        return None
    if encontrado and (Path(encontrado) / f"{IDIOMA}.traineddata").exists():
        return encontrado
    return None


@functools.lru_cache(maxsize=1)
def idiomas() -> str:
    """"spa+ces+eng" con los que haya: Tesseract lee varios a la vez (algo más lento)."""
    carpeta = tessdata()
    if carpeta is None:
        return IDIOMA
    presentes = [i for i in EXTRA if (Path(carpeta) / f"{i}.traineddata").exists()]
    return "+".join([IDIOMA, *presentes])


def disponible() -> bool:
    return tessdata() is not None


def _tesseract_propio() -> Path | None:
    for c in _carpetas_candidatas():
        exe = c.parent / ("tesseract.exe" if os.name == "nt" else "tesseract")
        if exe.exists():
            return exe
    return None


def textpage(pagina: pymupdf.Page):
    propio = _tesseract_propio()
    if propio is not None:
        os.environ["PATH"] = str(propio.parent) + os.pathsep + os.environ.get("PATH", "")
    return pagina.get_textpage_ocr(language=idiomas(), dpi=DPI, full=True, tessdata=tessdata())
