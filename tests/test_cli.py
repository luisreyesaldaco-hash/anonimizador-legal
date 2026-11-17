import json
import shutil

import pytest
from docx import Document

import docx_hostil
from anonimizador.cli import main
from anonimizador.procesadores import FormatoNoSoportado, abrir, rutas_salida
from anonimizador.procesadores.doc import convertidor_disponible


def test_generar_y_revertir(tmp_path, capsys):
    entrada = docx_hostil.crear(tmp_path / "demanda.docx")
    assert main(["generar", str(entrada), "--sin-ner", "--texto", str(tmp_path / "limpio.txt")]) == 0
    salida, tabla = tmp_path / "demanda_anonimizado.docx", tmp_path / "demanda_tabla.json"
    assert salida.exists() and tabla.exists()
    datos = json.loads(tabla.read_text(encoding="utf-8"))
    assert {e["etiqueta"] for e in datos["entidades"]} >= {"PERSONA_1", "RFC_1", "CORREO_1"}
    limpio = (tmp_path / "limpio.txt").read_text(encoding="utf-8")
    assert "Pérez" not in limpio and limpio.count("Firma: [PERSONA_1]") == 1

    respuesta = tmp_path / "respuesta.txt"
    respuesta.write_text("[PERSONA_1] tiene razón.", encoding="utf-8")
    capsys.readouterr()
    assert main(["revertir", str(tabla), str(respuesta)]) == 0
    assert capsys.readouterr().out == "Juan Pérez García tiene razón."


def test_rutas_salida_no_pisan(tmp_path):
    original = tmp_path / "a.pdf"
    s1, t1 = rutas_salida(original, ".pdf")
    s1.write_text("x")
    s2, t2 = rutas_salida(original, ".pdf")
    assert s2.name == "a_anonimizado_2.pdf" and t2.name == "a_tabla_2.json"


def test_formato_por_contenido(tmp_path):
    falso = tmp_path / "en_realidad_docx.doc"
    shutil.copy(docx_hostil.crear(tmp_path / "x.docx"), falso)
    assert type(abrir(falso)).__name__ == "DocumentoWord"
    assert type(abrir(_texto(tmp_path / "nota.txt"))).__name__ == "DocumentoTexto"
    raro = tmp_path / "hoja.xlsx.bin"
    raro.write_bytes(b"\x00\x01binario")
    with pytest.raises(FormatoNoSoportado):
        abrir(raro)


def _texto(ruta):
    ruta.write_text("hola", encoding="utf-8")
    return ruta


def test_error_legible(tmp_path, capsys):
    assert main(["escanear", str(tmp_path / "no_existe.pdf")]) == 1
    assert "No encuentro" in capsys.readouterr().err


def _soffice_para_fabricar():
    from anonimizador.procesadores.doc import _soffice

    return _soffice()


# El .doc de prueba se fabrica con LibreOffice; sin él no hay con qué crearlo.
@pytest.mark.skipif(convertidor_disponible() is None or _soffice_para_fabricar() is None,
                    reason="sin LibreOffice para fabricar el .doc de prueba")
def test_doc_antiguo(tmp_path):
    import subprocess

    from anonimizador.procesadores.doc import _soffice

    docx_path = docx_hostil.crear(tmp_path / "viejo.docx")
    subprocess.run([_soffice(), f"-env:UserInstallation={(tmp_path / 'p').as_uri()}", "--headless",
                    "--convert-to", "doc", "--outdir", str(tmp_path), str(docx_path)],
                   check=True, capture_output=True, timeout=180)
    docx_path.unlink()
    d = abrir(tmp_path / "viejo.doc")
    assert "Juan Pérez García" in d.texto
    with pytest.raises(ValueError):
        d.guardar(tmp_path / "viejo.doc", [])


def test_tabla_va_junto_a_la_salida_no_al_original(tmp_path):
    """La carpeta del original puede ser la que se le da a la IA: ahí no debe quedar nada."""
    origen, destino = tmp_path / "caso", tmp_path / "fuera"
    origen.mkdir()
    destino.mkdir()
    doc = Document()
    doc.add_paragraph("Comparece el C. Juan Pérez García.")
    doc.save(origen / "demanda.docx")
    assert main(["generar", str(origen / "demanda.docx"), "--sin-ner",
                 "--salida", str(destino / "demanda_anonimizado.docx")]) == 0
    assert sorted(p.name for p in origen.iterdir()) == ["demanda.docx"]
    assert (destino / "demanda_tabla.json").exists()
