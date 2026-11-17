"""Entradas nuevas (texto, imagen) y la salida en Word para lo que no es Word."""

import docx
import pymupdf
import pytest

from anonimizador.cli import main
from anonimizador.flujo import Flujo
from anonimizador.procesadores import abrir, imagen_a_pdf
from anonimizador.procesadores import ocr

CONTRATO = ("CONTRATO DE TRABAJO\n\nEn la Ciudad de México comparece el C. Juan Pérez García,\n"
            "con RFC GODE561231GR8 y correo juan@ejemplo.com.\n\nSegunda cláusula.\n")


def _pdf(ruta, paginas):
    doc = pymupdf.open()
    for texto in paginas:
        p = doc.new_page()
        p.insert_text((72, 72), texto, fontsize=11)
    doc.save(str(ruta))
    return ruta


def _texto_word(ruta):
    return "\n".join(p.text for p in docx.Document(str(ruta)).paragraphs)


def _flujo(rutas):
    f = Flujo(usar_ner=False)
    f.cargar(rutas)
    f.revisado = True
    return f


def test_txt_sale_en_txt_o_en_word(tmp_path):
    entrada = tmp_path / "contrato.txt"
    entrada.write_text(CONTRATO, encoding="utf-8")
    r = _flujo([entrada]).guardar_todos()
    salida = r.documentos[0].salida
    assert salida.name == "contrato_anonimizado.txt" and r.limpio
    assert "GODE561231GR8" not in salida.read_text(encoding="utf-8")
    r = _flujo([entrada]).guardar_todos(formato="docx")
    salida = r.documentos[0].salida
    assert salida.suffix == ".docx" and r.limpio
    texto = _texto_word(salida)
    assert "[RFC_1]" in texto and "GODE561231GR8" not in texto and "juan@ejemplo.com" not in texto
    # Los renglones de un mismo bloque se unen; los bloques quedan como párrafos.
    assert "comparece el C. [PERSONA_1], con RFC [RFC_1]" in texto


def test_pdf_a_word_con_saltos_de_pagina(tmp_path):
    entrada = _pdf(tmp_path / "demanda.pdf", ["Actor: Juan Pérez García, RFC GODE561231GR8.",
                                                "Correo juan@ejemplo.com en la segunda hoja."])
    r = _flujo([entrada]).guardar_todos(formato="docx")
    d = r.documentos[0]
    assert d.salida.name == "demanda_anonimizado.docx" and d.limpio
    doc = docx.Document(str(d.salida))
    parrafos = [p for p in doc.paragraphs if p.text]
    assert "GODE561231GR8" not in _texto_word(d.salida) and "[RFC_1]" in parrafos[0].text
    assert parrafos[1].paragraph_format.page_break_before and "[CORREO_1]" in parrafos[1].text
    assert any("diseño" in a for a in d.avisos)
    # Y el PDF sigue saliendo en PDF si no se pide Word.
    assert _flujo([entrada]).guardar_todos().documentos[0].salida.suffix == ".pdf"


def test_formato_desconocido(tmp_path):
    entrada = tmp_path / "a.txt"
    entrada.write_text(CONTRATO, encoding="utf-8")
    with pytest.raises(ValueError):
        _flujo([entrada]).guardar_todos(formato="pdf")


@pytest.mark.skipif(not ocr.disponible(), reason="sin OCR")
def test_imagen_escaneada_se_lee_con_ocr(tmp_path):
    origen = pymupdf.open()
    origen.new_page().insert_text((72, 100), "RFC GODE561231GR8", fontsize=24)
    foto = tmp_path / "foto.png"
    origen[0].get_pixmap(dpi=200).save(str(foto))
    documento = abrir(foto)
    assert type(documento).__name__ == "DocumentoPDF" and "GODE561231GR8" in documento.texto.replace(" ", "")
    r = _flujo([foto]).guardar_todos()
    assert r.documentos[0].salida.name == "foto_anonimizado.pdf"


def test_imagen_a_pdf_rechaza_basura(tmp_path):
    malo = tmp_path / "x.png"
    malo.write_bytes(b"\x89PNG roto")
    with pytest.raises(Exception):
        imagen_a_pdf(malo)


def test_cli_word(tmp_path, capsys):
    entrada = _pdf(tmp_path / "escrito.pdf", ["Actor: Juan Pérez García, RFC GODE561231GR8."])
    assert main(["generar", str(entrada), "--sin-ner", "--word"]) == 0
    assert (tmp_path / "escrito_anonimizado.docx").exists()
