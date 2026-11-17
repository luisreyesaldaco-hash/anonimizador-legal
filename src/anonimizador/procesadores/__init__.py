"""Abre cualquier formato soportado con el procesador adecuado."""

from __future__ import annotations

from pathlib import Path

from .docx import DocumentoNoSoportado as _NoSoportadoWord
from .docx import DocumentoWord
from .pdf import DocumentoNoSoportado as _NoSoportadoPDF
from .pdf import DocumentoPDF
from .texto import DocumentoNoSoportado as _NoSoportadoTexto
from .texto import DocumentoTexto
from ..textos import tr

IMAGENES = (".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp")
TEXTO = (".txt", ".md")
CONVERTIBLES = (".doc", ".odt", ".rtf")  # pasan a .docx con Word, textutil o LibreOffice
EXTENSIONES = (".pdf", ".docx") + CONVERTIBLES + TEXTO + IMAGENES
DocumentoNoSoportado = (_NoSoportadoWord, _NoSoportadoPDF, _NoSoportadoTexto)


class FormatoNoSoportado(Exception):
    pass


def _firma(ruta: Path) -> str:
    with open(ruta, "rb") as f:
        inicio = f.read(64)
    if inicio.startswith(b"%PDF"):
        return ".pdf"
    if inicio.startswith(b"PK"):  # .docx y .odt son zip: el .odt lo dice en su primer archivo
        return ".odt" if b"mimetypeapplication/vnd.oasis.opendocument" in inicio else ".docx"
    if inicio.startswith(bytes.fromhex("D0CF11E0A1B11AE1")):
        return ".doc"
    if inicio.startswith(b"{\\rtf"):
        return ".rtf"
    if inicio.startswith((b"\xff\xd8\xff", b"\x89PNG", b"II*\x00", b"MM\x00*", b"BM")):
        return ".imagen"
    return ""


def abrir(ruta: str | Path, usar_ocr: bool = True, avance=None):
    """`avance(pagina, total)`: se llama antes de leer con OCR cada página escaneada."""
    ruta = Path(ruta)
    if not ruta.is_file():
        raise FileNotFoundError(tr('No encuentro el archivo {ruta}.', ruta=ruta))
    # Se decide por el contenido, no por la extensión (hay .doc que en realidad son .docx).
    tipo = _firma(ruta) or ruta.suffix.lower()
    if tipo == ".pdf":
        return DocumentoPDF(ruta, usar_ocr=usar_ocr, avance=avance)
    if tipo == ".docx":
        return DocumentoWord(ruta)
    if tipo in CONVERTIBLES:
        from .doc import abrir_doc

        return abrir_doc(ruta)
    if tipo == ".imagen" or tipo in IMAGENES:
        return DocumentoPDF(ruta, usar_ocr=usar_ocr, datos=imagen_a_pdf(ruta), avance=avance)
    if tipo in TEXTO:
        return DocumentoTexto(ruta)
    raise FormatoNoSoportado(tr('{ruta}: se aceptan PDF, Word (.docx, .doc), .odt, .rtf, .txt, .md e imágenes (.jpg, .png, .tif).', ruta=ruta.name))


def imagen_a_pdf(ruta: str | Path) -> bytes:
    """Una foto o un escaneo como PDF en memoria (una página por imagen; un .tif puede traer
    varias). El OCR lo lee después como cualquier página escaneada."""
    import pymupdf

    try:
        with pymupdf.open(str(ruta)) as imagen:
            return imagen.convert_to_pdf()
    except Exception as e:
        raise _NoSoportadoPDF(tr('No pude abrir {ruta} como imagen: {e}', ruta=Path(ruta).name, e=e)) from e


def extension_salida(documento, formato: str = "original") -> str:
    """`formato`: "original" (PDF sale en PDF, texto en texto) o "docx" (todo sale en Word)."""
    if formato == "docx" or isinstance(documento, DocumentoWord):
        return ".docx"
    if isinstance(documento, DocumentoTexto):
        return documento.ruta.suffix.lower() if documento.ruta.suffix.lower() in TEXTO else ".txt"
    return ".pdf"


def rutas_salida(original: str | Path, extension: str) -> tuple[Path, Path]:
    """documento.pdf → documento_anonimizado.pdf y documento_tabla.json, sin pisar nada."""
    original = Path(original)
    n = 1
    while True:
        sufijo = "" if n == 1 else f"_{n}"
        salida = original.with_name(f"{original.stem}_anonimizado{sufijo}{extension}")
        tabla = original.with_name(f"{original.stem}_tabla{sufijo}.json")
        if not salida.exists() and not tabla.exists():
            return salida, tabla
        n += 1


def ruta_tabla(salida: str | Path) -> Path:
    """La tabla va junto al documento anonimizado (nunca junto al original, que puede estar
    en la carpeta que se le va a dar a la IA): informe_anonimizado.pdf → informe_tabla.json."""
    salida = Path(salida)
    base = salida.stem.removesuffix("_anonimizado")
    n = 1
    while True:
        tabla = salida.with_name(f"{base}_tabla{'' if n == 1 else f'_{n}'}.json")
        if not tabla.exists():
            return tabla
        n += 1


def marcar_si_hay_fugas(salida: Path, limpio: bool) -> Path:
    """Si la verificación encontró datos, el archivo se renombra para que nadie lo mande."""
    if limpio:
        return salida
    final = salida.with_name(salida.stem + "_CON_DATOS_REVISAR" + salida.suffix)
    salida.replace(final)
    return final

