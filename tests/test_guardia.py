"""La guardia del plugin de Claude Code: qué bloquea y qué deja pasar."""

import importlib.util
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("guardia", RAIZ / "claude-plugin" / "hooks" / "guardia.py")
guardia = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guardia)


@pytest.fixture
def caso(tmp_path, monkeypatch):
    (tmp_path / "anonimizado").mkdir()
    (tmp_path / "anonimizado" / "tabla_NO_ABRIR.json").write_text("{}")
    registro = tmp_path / "protegidos.json"
    registro.write_text(json.dumps({
        "protegidos": [str(tmp_path / "Demanda Juan Pérez.docx"), str(tmp_path / "final.docx")],
        "permitidos": [str(tmp_path / "anonimizado" / "texto_anonimizado.md")],
    }))
    monkeypatch.setattr(guardia, "REGISTRO", registro)
    return tmp_path


def _bloquea(caso, herramienta, **entrada) -> bool:
    return guardia.revisar({"tool_name": herramienta, "tool_input": entrada, "cwd": str(caso)}) is not None


@pytest.mark.parametrize("herramienta, entrada", [
    ("Read", {"file_path": "Demanda Juan Pérez.docx"}),
    ("Read", {"file_path": "anonimizado/tabla_NO_ABRIR.json"}),
    ("Read", {"file_path": "final.docx"}),
    ("Read", {"file_path": "/otra/carpeta/contrato.pdf"}),
    ("Read", {"file_path": "x/demanda_tabla.json"}),
    ("Read", {"file_path": "documento_1_CON_DATOS_REVISAR.docx"}),
    ("Grep", {"pattern": "Juan", "path": "anonimizado"}),
    ("Grep", {"pattern": "Juan"}),
    ("Bash", {"command": "cat anonimizado/tabla_NO_ABRIR.json"}),
    ("Bash", {"command": "pdftotext contrato.pdf -"}),
    ("Bash", {"command": "python3 -c \"import docx; docx.Document('Demanda Juan Pérez.docx')\""}),
    ("Bash", {"command": "anonimizador agente preparar a.docx; cat a.docx"}),
    ("Bash", {"command": "cd /x && anonimizador agente preparar a.docx && cat a.docx"}),
    ("Bash", {"command": "anonimizador revertir t.json r.md"}),
    ("Bash", {"command": "anonimizador generar demanda.docx"}),
    ("Write", {"file_path": "leer.py", "content": "import docx\ndocx.Document('demanda.docx')"}),
    ("Write", {"file_path": "anonimizado/tabla_NO_ABRIR.json", "content": "{}"}),
])
def test_bloquea(caso, herramienta, entrada):
    assert _bloquea(caso, herramienta, **entrada)


@pytest.mark.parametrize("herramienta, entrada", [
    ("Read", {"file_path": "anonimizado/texto_anonimizado.md"}),
    ("Read", {"file_path": "anonimizado/documento_1_anonimizado.docx"}),
    ("Read", {"file_path": "notas.md"}),
    ("Grep", {"pattern": "PERSONA", "path": "anonimizado/texto_anonimizado.md"}),
    ("Bash", {"command": "anonimizador agente preparar \"Demanda Juan Pérez.docx\" --idioma es"}),
    ("Bash", {"command": "anonimizador agente devolver anonimizado/tabla_NO_ABRIR.json r.md -o final.docx 2>&1"}),
    ("Bash", {"command": "cd \"/x y\" && anonimizador agente devolver \"anonimizado/tabla_NO_ABRIR.json\" r.md -o f.docx"}),
    ("Bash", {"command": "open \"final.docx\""}),
    ("Bash", {"command": "ls -la && git status"}),
    ("Write", {"file_path": "anonimizado/respuesta.md", "content": "# Opinión sobre demanda.docx"}),
])
def test_deja_pasar(caso, herramienta, entrada):
    assert not _bloquea(caso, herramienta, **entrada)
