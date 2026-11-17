# -*- mode: python ; coding: utf-8 -*-
# PyInstaller, modo carpeta (onedir): arranca más rápido y da menos falsos positivos
# de antivirus que un .exe de un solo archivo.
#
#   pyinstaller packaging/anonimizador.spec --noconfirm
#
# OCR: si existe vendor/tesseract/tessdata/spa.traineddata se incluye en la app (PyMuPDF trae
# Tesseract adentro; solo falta el idioma). El CI lo descarga antes de compilar.
# En Mac además se arma Anonimizador.app (BUNDLE).

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_all, collect_data_files

RAIZ = Path(SPECPATH).parent

datas, binaries, hiddenimports = [], [], []
for paquete in ("customtkinter", "tkinterdnd2", "spacy", "thinc", "es_core_news_md", "srsly",
                "blis", "cymem", "preshed", "murmurhash", "spacy_legacy", "spacy_loggers", "langcodes",
                "en_core_web_md", "cs_ner_sm"):
    try:
        d, b, h = collect_all(paquete)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h
datas += collect_data_files("pymupdf")
datas.append((str(RAIZ / "src" / "anonimizador" / "ui" / "recursos"), "anonimizador/ui/recursos"))
for d in ("datos_cs", "datos_en"):  # listas de nombres y municipios de los paquetes de idioma
    datas.append((str(RAIZ / "src" / "anonimizador" / "detector" / d), f"anonimizador/detector/{d}"))
hiddenimports += ["spacy.lang.es", "spacy.lang.en", "spacy.lang.cs"]
if sys.platform == "win32":
    hiddenimports += ["win32com.client", "pythoncom"]
MAC = sys.platform == "darwin"

tesseract = RAIZ / "vendor" / "tesseract"
if tesseract.exists():
    datas.append((str(tesseract), "tesseract"))

a = Analysis(
    [str(RAIZ / "main.py")],
    pathex=[str(RAIZ / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["pytest", "stdnum", "matplotlib", "IPython", "notebook", "torch", "tensorflow"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Anonimizador",
    console=False,
    icon=str(RAIZ / "packaging" / ("icono.icns" if MAC else "icono.ico")),
    version=str(RAIZ / "packaging" / "version.txt") if (RAIZ / "packaging" / "version.txt").exists() else None,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="Anonimizador")

if MAC:
    from anonimizador import __version__

    app = BUNDLE(
        coll,
        name="Anonimizador.app",
        icon=str(RAIZ / "packaging" / "icono.icns"),
        bundle_identifier="io.legalatlas.anonimizador",
        version=__version__,
        info_plist={
            "CFBundleDisplayName": "Anonimizador",
            "CFBundleName": "Anonimizador",
            "CFBundleShortVersionString": __version__,
            "NSHumanReadableCopyright": "LegalAtlas · AGPL-3.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "12.0",
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Documento",
                "CFBundleTypeRole": "Viewer",
                "LSItemContentTypes": ["com.adobe.pdf", "org.openxmlformats.wordprocessingml.document",
                                       "com.microsoft.word.doc"],
            }],
        },
    )
