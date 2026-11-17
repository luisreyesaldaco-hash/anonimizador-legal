"""El modo para agentes nunca imprime un dato real y registra lo que el agente no debe abrir."""

import json

import pytest

import docx_hostil
from anonimizador import agente
from anonimizador.cli import main

REALES = ("Juan", "Pérez", "PEGJ", "juan.perez")


@pytest.fixture
def registro(tmp_path, monkeypatch):
    ruta = tmp_path / "registro" / "protegidos.json"
    monkeypatch.setattr(agente, "REGISTRO", ruta)
    return ruta


def _json(capsys) -> tuple[dict, str]:
    salida = capsys.readouterr()
    todo = salida.out + salida.err
    return json.loads(salida.out), todo


def test_preparar_y_devolver_sin_imprimir_datos(tmp_path, capsys, registro):
    original = docx_hostil.crear(tmp_path / "Demanda Juan Pérez.docx")
    assert main(["agente", "preparar", str(original), "--sin-ner"]) == 0
    r, todo = _json(capsys)
    assert not any(v in todo for v in REALES)  # ni en stdout ni en stderr
    assert r["estado"] == "listo" and "PERSONA_1" in r["etiquetas"]
    texto = r["texto"]
    assert "[PERSONA_1]" in open(texto, encoding="utf-8").read()
    assert r["documentos"][0]["archivo"].endswith("documento_1_anonimizado.docx")  # sin el nombre del cliente
    reg = json.loads(registro.read_text(encoding="utf-8"))
    assert str(original.resolve()) in reg["protegidos"] and r["tabla"] in reg["protegidos"]
    assert texto in reg["permitidos"]

    respuesta = tmp_path / "respuesta.md"
    respuesta.write_text("# Opinión\n\n**[PERSONA_1]** tiene razón; escribir a \\[CORREO\\_1\\].", encoding="utf-8")
    final = tmp_path / "final.docx"
    assert main(["agente", "devolver", r["tabla"], str(respuesta), "-o", str(final)]) == 0
    d, todo = _json(capsys)
    assert not any(v in todo for v in REALES)
    assert d["estado"] == "listo" and d["reemplazos"] == 2
    assert str(final.resolve()) in json.loads(registro.read_text(encoding="utf-8"))["protegidos"]
    from anonimizador.reversion import texto_de_docx
    assert "Juan Pérez García tiene razón" in texto_de_docx(final)


def test_devolver_avisa_etiquetas_deformadas(tmp_path, capsys, registro):
    original = docx_hostil.crear(tmp_path / "a.docx")
    main(["agente", "preparar", str(original), "--sin-ner"])
    r, _ = _json(capsys)
    respuesta = tmp_path / "r.md"
    respuesta.write_text("[OSOBĚ_1] y [PERSONA_1]", encoding="utf-8")
    assert main(["agente", "devolver", r["tabla"], str(respuesta), "-o", str(tmp_path / "f.docx")]) == 2
    d, _ = _json(capsys)
    assert d["estado"] == "revisar" and d["sin_revertir"] == ["[OSOBĚ_1]"]
