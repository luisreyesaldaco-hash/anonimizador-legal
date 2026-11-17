import pymupdf
import pytest

from anonimizador.detector import detectar
from anonimizador.procesadores import ocr
from anonimizador.procesadores.pdf import DocumentoNoSoportado, DocumentoPDF
from anonimizador.seudonimos import Entidad, Sesion

NOMBRE = "Juan Pérez García"
CORREO = "juan.perez@ejemplo.com"


def _pdf_hostil(ruta):
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), f"Comparece el C. {NOMBRE}, por su propio derecho,", fontsize=11)
    p.insert_text((72, 90), f"con RFC GODE561231GR8 y correo {CORREO}.", fontsize=11)
    p.add_text_annot((72, 120), f"Llamar a {NOMBRE}")  # nota adhesiva
    w = pymupdf.Widget()  # campo de formulario lleno
    w.field_name, w.field_type = "actor", pymupdf.PDF_WIDGET_TYPE_TEXT
    w.rect, w.field_value = pymupdf.Rect(72, 140, 300, 160), f"Actor: {NOMBRE}"
    p.add_widget(w)
    doc.embfile_add("notas.txt", f"expediente de {NOMBRE}".encode())
    doc.set_metadata({"author": "Lic. Gabriela Ochoa Ríos", "title": f"Demanda {NOMBRE}"})
    doc.set_toc([[1, f"Hechos de {NOMBRE}", 1]])
    doc.save(str(ruta))
    return ruta


@pytest.fixture
def procesado(tmp_path):
    entrada = _pdf_hostil(tmp_path / "hostil.pdf")
    d = DocumentoPDF(entrada)
    s = Sesion(d.texto, detectar(d.texto, usar_ner=False))
    salida = tmp_path / "hostil_anonimizado.pdf"
    return d, s, salida, d.guardar(salida, s.entidades)


def test_texto_incluye_campos_de_formulario(procesado):
    d, *_ = procesado
    assert NOMBRE in d.texto and f"Actor: {NOMBRE}" in d.texto


def test_salida_limpia(procesado):
    _, _, salida, informe = procesado
    assert informe.limpio, informe.verificacion.fugas
    with pymupdf.open(str(salida)) as o:
        texto = o[0].get_text()
        crudo = b"".join(pg.read_contents() for pg in o)
        assert "[PERSONA_1]" in texto and "[RFC_1]" in texto and "[CORREO_1]" in texto
        assert "Pérez" not in texto and "GODE" not in texto
        assert b"rez Garc" not in crudo and b"GODE" not in crudo  # ni en el flujo de contenido
        assert o.metadata["author"] == "" and o.metadata["title"] == ""
        assert o.embfile_count() == 0
        assert not list(o[0].annots() or []) and not list(o[0].widgets() or [])
        assert all("Pérez" not in t[1] for t in o.get_toc())


def test_resto_del_texto_intacto(procesado):
    _, _, salida, _ = procesado
    with pymupdf.open(str(salida)) as o:
        texto = o[0].get_text()
    assert "Comparece el C." in texto and "por su propio derecho" in texto


def test_no_sobrescribe_original(tmp_path):
    entrada = _pdf_hostil(tmp_path / "x.pdf")
    with pytest.raises(ValueError):
        DocumentoPDF(entrada).guardar(entrada, [])


def test_pdf_con_contrasena(tmp_path):
    doc = pymupdf.open()
    doc.new_page().insert_text((72, 72), "secreto")
    ruta = tmp_path / "cerrado.pdf"
    doc.save(str(ruta), encryption=pymupdf.PDF_ENCRYPT_AES_256, user_pw="x", owner_pw="y")
    with pytest.raises(DocumentoNoSoportado, match="contraseña"):
        DocumentoPDF(ruta)


def _pdf_escaneado(ruta, extra=""):
    origen = pymupdf.open()
    origen.new_page().insert_text((72, 100), f"Comparece el C. {NOMBRE}", fontsize=20)
    if extra:
        origen[0].insert_text((72, 160), extra, fontsize=20)
    pix = origen[0].get_pixmap(dpi=200)
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_image(p.rect, pixmap=pix)
    doc.save(str(ruta))
    return ruta


def test_escaneado_sin_ocr_avisa(tmp_path):
    d = DocumentoPDF(_pdf_escaneado(tmp_path / "scan.pdf"), usar_ocr=False)
    assert d.escaneado_sin_ocr
    assert any("NO se anonimizaron" in a for a in d.avisos)


@pytest.mark.skipif(not ocr.disponible(), reason="Tesseract con español no está instalado")
def test_escaneado_con_ocr(tmp_path):
    d = DocumentoPDF(_pdf_escaneado(tmp_path / "scan.pdf"))
    assert d.paginas_ocr == [1]
    assert "Pérez" in d.texto
    s = Sesion(d.texto, detectar(d.texto, usar_ner=False))
    informe = d.guardar(tmp_path / "scan_anon.pdf", s.entidades)
    assert informe.apariciones >= 1
    assert informe.limpio, informe.verificacion.fugas
    # La página de salida ya tiene texto (las etiquetas): para ver lo que quedó en la
    # imagen hay que forzar el OCR sobre ella.
    with pymupdf.open(str(tmp_path / "scan_anon.pdf")) as salida:
        visible = salida[0].get_textpage_ocr(language="spa", dpi=300, full=True,
                                             tessdata=ocr.tessdata()).extractText()
    assert "Pérez" not in visible and "rez" not in visible, visible


@pytest.mark.skipif(not ocr.disponible(), reason="Tesseract con español no está instalado")
def test_escaneado_correo_con_arroba_mal_leida(tmp_path):
    d = DocumentoPDF(_pdf_escaneado(tmp_path / "scan.pdf", "Correo: juan.perez@ejemplo.com"))
    s = Sesion(d.texto, detectar(d.texto, usar_ner=False))
    assert any(e.tipo == "CORREO" for e in s.entidades), d.texto
    informe = d.guardar(tmp_path / "scan_anon.pdf", s.entidades)
    assert informe.limpio, informe.verificacion.fugas


@pytest.mark.skipif(not ocr.disponible(), reason="Tesseract con español no está instalado")
def test_escaneado_verificacion_ve_la_imagen(tmp_path, monkeypatch):
    """Si las cajas no tapan el dato, la verificación debe verlo en los píxeles."""
    from anonimizador.procesadores import pdf as modulo

    d = DocumentoPDF(_pdf_escaneado(tmp_path / "scan.pdf"))
    s = Sesion(d.texto, detectar(d.texto, usar_ner=False))
    monkeypatch.setattr(modulo.DocumentoPDF, "_rects_por_linea",
                        lambda self, i, f: ((n, pymupdf.Rect(r.x0, r.y0, r.x0 + 2, r.y0 + 2), t, o)
                                            for n, r, t, o, _ in self._rects_crudos(i, f)))
    informe = d.guardar(tmp_path / "scan_anon.pdf", s.entidades)
    assert not informe.limpio
    assert any(f.ubicacion.startswith("imagen") for f in informe.verificacion.fugas)


def test_verificacion_detecta_fuga(tmp_path):
    from anonimizador.procesadores.pdf import verificar_pdf

    ruta = _pdf_hostil(tmp_path / "x.pdf")
    r = verificar_pdf(ruta, [Entidad("PERSONA_1", "NOMBRE", [NOMBRE])])
    ubicaciones = {f.ubicacion for f in r.fugas}
    assert {"página 1", "metadatos", "marcadores", "archivos adjuntos"} <= ubicaciones


@pytest.mark.skipif(not ocr.disponible(), reason="Tesseract con español no está instalado")
def test_ocr_avisa_cada_pagina(tmp_path):
    # La ventana muestra «página 1 de 1 escaneada…»: sin esto, el OCR parecía no hacer nada.
    from anonimizador.flujo import Flujo

    vistos = []
    Flujo(usar_ner=False).cargar(_pdf_escaneado(tmp_path / "scan.pdf"), avance=lambda *a: vistos.append(a))
    assert vistos == [("scan.pdf", 1, 1)]
