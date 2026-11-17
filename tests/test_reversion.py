import json

import docx
import pytest

from anonimizador.cli import main
from anonimizador.reversion import (markdown_a_texto, nombre_sugerido, revertir_docx, texto_a_docx,
                                    texto_de_docx)
from anonimizador.seudonimos import FORMATO_TABLA, etiquetas_desconocidas, revertir

TABLA = {
    "formato": FORMATO_TABLA,
    "entidades": [
        {"etiqueta": "PERSONA_1", "tipo": "NOMBRE", "original": "María Ríos Calderón", "variantes": []},
        {"etiqueta": "PERSONA_10", "tipo": "NOMBRE", "original": "Luis Soto", "variantes": []},
        {"etiqueta": "EMPRESA_1", "tipo": "EMPRESA", "original": "IMV, S.A. de C.V.", "variantes": []},
        {"etiqueta": "DOMICILIO_1", "tipo": "DOMICILIO", "original": "Av. Fundidores 2150, Col. San\nBartolo",
         "variantes": []},
    ],
}


def _parrafos(ruta):
    return [p for p in docx.Document(str(ruta)).paragraphs if p.text]


def test_valor_partido_sale_en_un_renglon():
    assert revertir("en [DOMICILIO_1].", TABLA) == "en Av. Fundidores 2150, Col. San Bartolo."
    assert revertir("[PERSONA_10] y [PERSONA_1]", TABLA) == "Luis Soto y María Ríos Calderón"


@pytest.mark.parametrize("deformada", [
    "[PERSONA_1]", "[Persona 1]", "PERSONA_1", "[ PERSONA_1 ]", r"\[PERSONA\_1\]", "[PERSONA\\_1]",
    "[PERSONA-1]", "[PERSONA1]", "[PERSONA_01]", "[PERSONA_ 1]", "[PERSONA_1\u200b]", "[\ufeffPERSONA_1]",
])
def test_etiqueta_deformada_por_la_ia_se_revierte(deformada):
    assert revertir(f"firma {deformada}.", TABLA) == "firma María Ríos Calderón."
    assert etiquetas_desconocidas(f"firma {deformada}.", TABLA) == []


def test_varias_etiquetas_en_un_corchete():
    assert revertir("[PERSONA_1 y PERSONA_10]", TABLA) == "[María Ríos Calderón y Luis Soto]"


@pytest.mark.parametrize("deformada", [
    "[PERSONAS_1]", "[PERSON_1]", "[NOMBRE_1]", "[PERSONA_100]", "[PERSONA_3]", "[CLIENTE_1]",
    "[Persona 4]", "[OSOBY_1]", "[OSOBĚ_1]", "[Osobě 1]", "OSOBA_1ovi", "EMPRESA 3",
])
def test_lo_que_no_se_puede_revertir_se_avisa(deformada):
    """Ninguna etiqueta deformada se queda sin revertir en silencio."""
    assert etiquetas_desconocidas(f"y {deformada} firmó", TABLA) == [deformada]


def test_un_aviso_nunca_trae_un_dato_real():
    """«RFC [RFC_1]» revertido es «RFC GODE561231GR8»: no es una etiqueta deformada, y si lo
    fuera, el aviso llevaría el RFC real a la conversación con la IA."""
    tabla = {"formato": FORMATO_TABLA, "entidades": [
        {"etiqueta": "RFC_1", "tipo": "RFC", "original": "GODE561231GR8", "variantes": []},
        {"etiqueta": "EXPEDIENTE_1", "tipo": "EXPEDIENTE", "original": "EXP 123/2024", "variantes": []}]}
    for texto in ("con RFC [RFC_1] y", "RFC [RFC_1]", "EXPEDIENTE [EXPEDIENTE_1]", "[RFC_1] [RFC_9]"):
        avisos = etiquetas_desconocidas(texto, tabla)
        assert not any("GODE" in a or "123" in a for a in avisos), avisos
    assert etiquetas_desconocidas("[RFC_1] [RFC_9]", tabla) == ["[RFC_9]"]


@pytest.mark.parametrize("normal", ["la norma ISO 9001", "COVID-19 en 2020", "ver [1] y [Anexo 2]",
                                    "Nota [Art 14]", "firma 2 stran"])
def test_texto_normal_no_da_aviso(normal):
    assert etiquetas_desconocidas(normal, TABLA) == []


def test_markdown_a_docx_con_formato(tmp_path):
    texto = ("# Demanda\n\n**EXPEDIENTE:** ___\n**ACTORA:** [PERSONA_1]\n\n"
             "Demando a **[EMPRESA_1]**, con domicilio en _[DOMICILIO_1]_.\n\n"
             "- primera\n- segunda\n\n1. uno\n2. dos\n\n| Dato | Valor |\n|---|---|\n| Actora | [PERSONA_1] |\n\n"
             "Inventada: [PERSONA_9].")
    r = texto_a_docx(texto, tmp_path / "s.docx", TABLA)
    assert r.reemplazos == 4 and r.desconocidas == ["[PERSONA_9]"]
    doc = docx.Document(str(tmp_path / "s.docx"))
    textos = [p.text for p in doc.paragraphs if p.text]
    assert textos[0] == "Demanda" and doc.paragraphs[0].style.name == "Heading 1"
    assert textos[1] == "EXPEDIENTE: ___" and textos[2] == "ACTORA: María Ríos Calderón"  # un renglón cada uno
    demando = next(p for p in doc.paragraphs if p.text.startswith("Demando"))
    assert demando.text == "Demando a IMV, S.A. de C.V., con domicilio en Av. Fundidores 2150, Col. San Bartolo."
    assert any(r.bold and r.text == "IMV, S.A. de C.V." for r in demando.runs)
    assert any(r.italic and "Fundidores" in r.text for r in demando.runs)
    assert "*" not in "".join(textos) and "**" not in "".join(textos)
    assert [p.style.name for p in doc.paragraphs if p.text in ("primera", "segunda")] == ["List Bullet"] * 2
    assert any(p.text.startswith("1.\tuno") for p in doc.paragraphs)
    assert doc.tables[0].cell(1, 1).text == "María Ríos Calderón"
    assert doc.core_properties.author == ""


def test_docx_de_la_ia_conserva_formato_y_etiquetas_partidas(tmp_path):
    entrada = tmp_path / "respuesta.docx"
    d = docx.Document()
    p = d.add_paragraph()
    p.add_run("Demanda de [PERS")
    negrita = p.add_run("ONA_1]")
    negrita.bold = True
    p.add_run(" contra [EMPRESA_1].")
    d.sections[0].header.paragraphs[0].text = "Actora: PERSONA 1"
    d.save(str(entrada))
    salida = nombre_sugerido(entrada, tmp_path / "x_tabla.json")
    assert salida.name == "respuesta_revertido.docx"
    r = revertir_docx(entrada, salida, TABLA)
    assert r.reemplazos == 3 and not r.desconocidas
    p = _parrafos(salida)[0]
    assert p.text == "Demanda de María Ríos Calderón contra IMV, S.A. de C.V.."
    assert p.runs[0].text == "Demanda de María Ríos Calderón" and not p.runs[1].text
    assert "Actora: María Ríos Calderón" in texto_de_docx(salida)
    with pytest.raises(ValueError):
        revertir_docx(entrada, entrada, TABLA)


def test_markdown_a_texto():
    texto = "## Partes\n\n**Actora:** María\n- uno\n> cita *suave*\n\n---\n\n| a | b |\n|---|---|\n| 1 | 2 |\nPlazo: ___"
    assert markdown_a_texto(texto) == "Partes\n\nActora: María\n• uno\ncita suave\n\na · b\n1 · 2\nPlazo: ___"


def test_cli_revertir_a_docx(tmp_path, capsys):
    tabla = tmp_path / "caso_tabla.json"
    tabla.write_text(json.dumps(TABLA), encoding="utf-8")
    md = tmp_path / "respuesta.md"
    md.write_text("**[PERSONA_1]** demanda.", encoding="utf-8")
    assert main(["revertir", str(tabla), str(md), "-o", str(tmp_path / "r.docx")]) == 0
    assert _parrafos(tmp_path / "r.docx")[0].text == "María Ríos Calderón demanda."
    entrada = tmp_path / "ia.docx"
    d = docx.Document()
    d.add_paragraph("[EMPRESA_1]")
    d.save(str(entrada))
    capsys.readouterr()
    assert main(["revertir", str(tabla), str(entrada)]) == 0
    assert capsys.readouterr().out.strip().endswith("ia_revertido.docx")
    assert _parrafos(tmp_path / "ia_revertido.docx")[0].text == "IMV, S.A. de C.V."
