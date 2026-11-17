"""Idioma de la interfaz: cada texto envuelto en tr() tiene traducción, con los mismos huecos."""

import ast
import string
from pathlib import Path

import pytest

from anonimizador import textos
from anonimizador.flujo import CATEGORIAS
from anonimizador.textos_cs import TEXTOS as CS
from anonimizador.textos_en import TEXTOS as EN

SRC = Path(textos.__file__).parent


def _claves_en_el_codigo() -> dict[str, str]:
    claves = {}
    for f in sorted(SRC.rglob("*.py")):
        for n in ast.walk(ast.parse(f.read_text(encoding="utf-8"))):
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in ("tr", "traducir"):
                arg = n.args[0] if n.func.id == "tr" else n.args[1]
                if isinstance(arg, ast.Constant):
                    claves.setdefault(arg.value, f"{f.relative_to(SRC)}:{n.lineno}")
    return claves


def _huecos(texto: str) -> set[str]:
    return {campo for _, campo, _, _ in string.Formatter().parse(texto) if campo}


@pytest.mark.parametrize("catalogo", [EN, CS], ids=["en", "cs"])
def test_todo_texto_tiene_traduccion(catalogo):
    faltan = {k: donde for k, donde in _claves_en_el_codigo().items() if k not in catalogo}
    assert not faltan, "Sin traducción (agrégalos a textos_en.py y textos_cs.py):\n" + "\n".join(f"{d}: {k!r}" for k, d in faltan.items())


@pytest.mark.parametrize("catalogo", [EN, CS], ids=["en", "cs"])
def test_mismos_huecos(catalogo):
    malos = [k for k, v in catalogo.items() if _huecos(k) != _huecos(v)]
    assert not malos, malos


def test_categorias_traducidas():
    for cat in (EN, CS):
        assert all(nombre in cat for nombre, _ in CATEGORIAS) and "Otros" in cat


def test_tr_cae_a_espanol_y_formatea(monkeypatch):
    monkeypatch.setattr(textos, "_actual", "en")
    assert textos.tr("Cancelar") == "Cancel"
    assert textos.tr("{n} documentos", n=3) == "3 documents"
    assert textos.tr("Texto que nadie tradujo") == "Texto que nadie tradujo"
    monkeypatch.setattr(textos, "_actual", "es")
    assert textos.tr("{n} documentos", n=3) == "3 documentos"


def test_checo_tiene_catalogo():
    assert textos.traducir("cs", "Cancelar") == "Zrušit"
    assert textos.traducir("cs", "{n} documentos", n=3) == "Dokumentů: 3"


def test_elegir_idioma_se_guarda_sin_cambiar_la_ventana_abierta(monkeypatch, tmp_path):
    monkeypatch.setenv("ANONIMIZADOR_PREFERENCIAS", str(tmp_path / "p.json"))
    monkeypatch.setattr(textos, "_actual", "es")
    textos.poner_idioma_ui("en", ahora=False)
    assert textos.idioma_ui() == "es"
    from anonimizador import preferencias

    assert preferencias.leer("idioma_ui") == "en"


def test_documento_checo_lleva_etiquetas_en_checo():
    from anonimizador.flujo import Flujo

    import docx, tempfile, os
    d = docx.Document()
    d.add_paragraph("Smlouvu se společností Stavby Brno s.r.o., IČO 27074358, podepsala Ing. Jana Dvořáková "
                    "dne 3. března 2026. Kontakt: jana.dvorakova@seznam.cz, tel. 603 123 456.")
    with tempfile.TemporaryDirectory() as t:
        ruta = os.path.join(t, "smlouva.docx")
        d.save(ruta)
        f = Flujo()
        f.cargar([ruta])
        etiquetas = {e.etiqueta.rsplit("_", 1)[0] for e in f.sesion.entidades}
    assert f.idioma == "cs"
    assert {"OSOBA", "FIRMA", "ICO", "DATUM", "EMAIL", "TELEFON"} <= etiquetas, etiquetas
