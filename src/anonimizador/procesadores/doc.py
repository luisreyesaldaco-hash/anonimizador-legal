""".doc (Word 97-2003): se convierte a .docx en una carpeta temporal y se procesa como tal.

Orden de preferencia:
1. Microsoft Word, si está instalado (Windows, vía COM): la conversión más fiel.
2. En Mac, `textutil`, que viene con el sistema.
3. LibreOffice, si está instalado.

El .docx intermedio contiene los datos originales: vive en una carpeta temporal que se
borra en cuanto el documento queda cargado en memoria.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from .docx import DocumentoNoSoportado, DocumentoWord
from ..textos import tr

_SOFFICE_WINDOWS = [
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "LibreOffice" / "program" / "soffice.exe",
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "LibreOffice" / "program" / "soffice.exe",
]
_SOFFICE_MAC = [Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")]
WD_FORMAT_DOCX = 16  # wdFormatDocumentDefault


def _con_word(origen: Path, destino: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return False
    pythoncom.CoInitialize()
    word = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        documento = word.Documents.Open(str(origen), ConfirmConversions=False, ReadOnly=True,
                                        AddToRecentFiles=False, Visible=False)
        documento.SaveAs2(str(destino), FileFormat=WD_FORMAT_DOCX, AddToRecentFiles=False)
        documento.Close(SaveChanges=0)
        return destino.exists()
    except Exception:
        return False
    finally:
        if word is not None:
            try:
                word.Quit()
            except Exception:
                pass
        pythoncom.CoUninitialize()


def _soffice() -> str | None:
    encontrado = shutil.which("soffice") or shutil.which("libreoffice")
    if encontrado:
        return encontrado
    return next((str(p) for p in _SOFFICE_WINDOWS + _SOFFICE_MAC if p.exists()), None)


def _textutil() -> str | None:
    return shutil.which("textutil") if sys.platform == "darwin" else None


def _con_textutil(origen: Path, destino: Path) -> bool:
    """macOS trae `textutil`, que convierte .doc a .docx sin instalar nada."""
    herramienta = _textutil()
    if herramienta is None:
        return False
    try:
        subprocess.run([herramienta, "-convert", "docx", "-output", str(destino), str(origen)],
                       check=True, capture_output=True, timeout=180)
    except (subprocess.SubprocessError, OSError):
        return False
    return destino.exists()


def _con_libreoffice(origen: Path, carpeta: Path) -> Path | None:
    soffice = _soffice()
    if soffice is None:
        return None
    perfil = (carpeta / "perfil").as_uri()  # perfil propio: no choca con un LibreOffice abierto
    try:
        subprocess.run(
            [soffice, f"-env:UserInstallation={perfil}", "--headless", "--convert-to", "docx",
             "--outdir", str(carpeta), str(origen)],
            check=True, capture_output=True, timeout=180,
        )
    except (subprocess.SubprocessError, OSError):
        return None
    salida = carpeta / (origen.stem + ".docx")
    return salida if salida.exists() else None


def _word_instalado() -> bool:
    """pywin32 siempre viene en el paquete: lo que importa es que Word esté registrado."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"))
    except OSError:
        return False
    try:
        import win32com.client  # noqa: F401
    except ImportError:
        return False
    return True


def convertidor_disponible() -> str | None:
    if _word_instalado():
        return "Microsoft Word"
    if _textutil():
        return "macOS (textutil)"
    return "LibreOffice" if _soffice() else None


def abrir_doc(ruta: str | Path) -> DocumentoWord:
    ruta = Path(ruta)
    with tempfile.TemporaryDirectory(prefix="anonimizador-") as tmp:
        carpeta = Path(tmp)
        copia = carpeta / ("entrada" + ruta.suffix)  # nombre neutro, por si el original tiene datos
        shutil.copyfile(ruta, copia)
        destino = carpeta / "entrada.docx"
        if (_word_instalado() and _con_word(copia, destino)) or _con_textutil(copia, destino):
            convertido = destino
        else:
            convertido = _con_libreoffice(copia, carpeta)
        if convertido is None:
            raise DocumentoNoSoportado(
                tr('Para abrir archivos {doc} se necesita Microsoft Word o LibreOffice instalado. También puedes abrirlo en Word y guardarlo como .docx.', doc=ruta.suffix or '.doc')
            )
        documento = DocumentoWord(convertido)  # queda cargado en memoria
    documento.ruta = ruta  # para la regla de no sobrescribir el original
    documento.avisos.append(tr('El archivo {doc} se convirtió a .docx; la salida es un .docx.', doc=ruta.suffix or '.doc'))
    return documento
