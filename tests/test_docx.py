import zipfile

import docx
import pytest

import docx_hostil
from anonimizador.detector import detectar
from anonimizador.procesadores.docx import DocumentoWord
from anonimizador.seudonimos import Entidad, Sesion
from anonimizador.verificacion import verificar_paquete


@pytest.fixture
def procesado(tmp_path):
    entrada = docx_hostil.crear(tmp_path / "hostil.docx")
    d = DocumentoWord(entrada)
    s = Sesion(d.texto, detectar(d.texto, usar_ner=False))
    salida = tmp_path / "hostil_anonimizado.docx"
    informe = d.guardar(salida, s.entidades)
    return d, s, salida, informe


def _todo(salida):
    with zipfile.ZipFile(salida) as z:
        return z.namelist(), " ".join(z.read(n).decode("utf-8", "replace") for n in z.namelist())


def test_texto_extraido_incluye_todas_las_partes(procesado):
    d, *_ = procesado
    for fragmento in ("Comparece el C. Juan Pérez García", "Firma: Juan Pérez García",
                      "Expediente 1234/2024", "Contacto: juan.perez@ejemplo.com", "la parte demandada"):
        assert fragmento in d.texto
    assert docx_hostil.BORRADO not in d.texto  # el texto borrado con control de cambios no cuenta


def test_no_queda_ningun_dato_en_el_paquete(procesado):
    *_, salida, informe = procesado
    nombres, blob = _todo(salida)
    for dato in ("Pérez", "GODE561231GR8", "juan.perez", docx_hostil.BORRADO, "Gabriela", "Ochoa",
                 "Abogado Revisor", "1234/2024"):
        assert dato not in blob, dato
    assert not any("comments" in n or "thumbnail" in n for n in nombres)
    assert informe.limpio, informe.verificacion.fugas


def test_formato_se_conserva(procesado):
    *_, salida, _ = procesado
    p = docx.Document(str(salida)).paragraphs[0]
    assert p.text == "Comparece el C. [PERSONA_1], por su propio derecho, con RFC [RFC_1]."
    marcador = next(r for r in p.runs if r.text == "[PERSONA_1]")
    assert marcador.bold


def test_partes_visibles(procesado):
    *_, salida, _ = procesado
    o = docx.Document(str(salida))
    assert o.sections[0].header.paragraphs[0].text == "Expediente [EXPEDIENTE_1] — [PERSONA_1]"
    assert o.tables[0].cell(0, 1).text == "[PERSONA_1]"
    assert o.core_properties.author == "" and o.core_properties.title == ""


def test_no_sobrescribe_original(tmp_path):
    entrada = docx_hostil.crear(tmp_path / "x.docx")
    d = DocumentoWord(entrada)
    with pytest.raises(ValueError):
        d.guardar(entrada, [])


def test_verificacion_detecta_fuga(tmp_path):
    entrada = docx_hostil.crear(tmp_path / "x.docx")
    fuga = Entidad("PERSONA_1", "NOMBRE", [docx_hostil.NOMBRE])
    r = verificar_paquete(entrada, [fuga])  # el original, sin procesar
    assert not r.limpio
    assert any(f.ubicacion == "word/document.xml" for f in r.fugas)
    assert any("thumbnail" in f.ubicacion for f in r.fugas)


def test_desmarcado_largo_no_cuenta_como_fuga(tmp_path):
    from docx import Document

    from anonimizador.detector import detectar
    from anonimizador.procesadores import abrir
    from anonimizador.seudonimos import Sesion

    ruta = tmp_path / "f.docx"
    d = Document(); d.add_paragraph("Entrevista: 8-sep-2026."); d.add_paragraph("Lo básico (8-sep)."); d.save(ruta)
    doc = abrir(ruta)
    s = Sesion(doc.texto, detectar(doc.texto, usar_ner=False))
    s.marcar(next(e for e in s.entidades if e.canonico == "8-sep-2026").etiqueta, False)
    inf = doc.guardar(tmp_path / "s.docx", s.entidades)
    assert inf.limpio, inf.verificacion.fugas


def test_avisa_que_quito_comentarios_y_cambios(procesado):
    d, *_ = procesado
    assert any("1 comentario" in a for a in d.avisos)
    assert any("cambios controlados" in a for a in d.avisos)


def test_sin_comentarios_ni_cambios_no_hay_aviso(tmp_path):
    ruta = tmp_path / "simple.docx"
    w = docx.Document()
    w.add_paragraph("Comparece el C. Juan Pérez García.")
    w.save(ruta)
    assert DocumentoWord(ruta).avisos == []
