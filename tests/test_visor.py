"""Visor de documento: la parte lógica se prueba sin pantalla; el componente, solo si hay display."""

import os
import sys

import pymupdf
import pytest
from PIL import Image

pytest.importorskip("customtkinter")
from anonimizador.ui import visor as V  # noqa: E402


def _pdf(paginas: list[list[tuple[float, float, str]]], rotar: int = 0) -> pymupdf.Document:
    doc = pymupdf.open()
    for lineas in paginas:
        p = doc.new_page(width=612, height=792)
        for x, y, texto in lineas:
            p.insert_text((x, y), texto, fontsize=12)
        if rotar:
            p.set_rotation(rotar)
    return pymupdf.open("pdf", doc.tobytes())


@pytest.fixture
def doc():
    return _pdf([
        [(72, 100, "Portada del expediente.")],
        [(72, 100, "Comparece la señora MARÍA FERNANDA"), (72, 124, "RÍOS CALDERÓN, por su propio derecho."),
         (72, 150, "Mariana no es María. RFC: RICF-900822-K77.")],
        [(72, 100, "Firma: María Fernanda Ríos Calderón"), (72, 130, "Testigo: Claudia Ornelas")],
    ])


# --- búsqueda en texto ----------------------------------------------------------------


def test_buscar_ignora_mayusculas_acentos_y_cruza_lineas():
    texto = "la señora MARÍA FERNANDA\nRIOS calderón firma"
    tramos = V.buscar(texto, ["María Fernanda Ríos Calderón"])
    assert len(tramos) == 1
    ini, fin = tramos[0]
    assert texto[ini:fin] == "MARÍA FERNANDA\nRIOS calderón"


def test_buscar_respeta_limites_de_palabra_y_gana_la_mas_larga():
    texto = "Mariana y María Ríos; María."
    assert [texto[a:b] for a, b in V.buscar(texto, ["María"])] == ["María", "María"]
    assert [texto[a:b] for a, b in V.buscar(texto, ["María", "María Ríos"])] == ["María Ríos", "María"]


def test_identificadores_con_o_sin_separadores():
    texto = "RFC RICF-900822-K77 y otra vez RICF900822K77; cuenta 0121 8000 1234."
    assert len(V.buscar(texto, ["RICF900822K77"])) == 2
    assert len(V.buscar(texto, ["012180001234"])) == 1


def test_terminos_vacios_no_encuentran_nada():
    assert V.buscar("algo de texto", ["", "   "]) == []
    assert V.patron("  ") is None


# --- texto del PDF ---------------------------------------------------------------------


def test_rectangulos_por_renglon_cuando_el_nombre_cruza_lineas(doc):
    t = V.TextoPDF(doc)
    aps = t.apariciones_en(1, ["María Fernanda Ríos Calderón"])
    assert len(aps) == 1
    rects = aps[0].rects
    assert len(rects) == 2  # «MARÍA FERNANDA» / «RÍOS CALDERÓN»
    assert rects[0].y1 <= rects[1].y0 + 1
    pagina = doc[1]
    assert pagina.get_textbox(rects[0]).strip().endswith("MARÍA FERNANDA")
    assert pagina.get_textbox(rects[1]).strip().startswith("RÍOS CALDERÓN")


def test_mapeo_termino_pagina_y_n_esima_aparicion(doc):
    t = V.TextoPDF(doc)
    termino = ["María Fernanda Ríos Calderón"]
    assert t.conteo_por_pagina(termino) == [(1, 1), (2, 1)]
    primera, total = t.buscar_n(termino, 0)
    assert total == 2 and primera.pagina == 1
    segunda, _ = t.buscar_n(termino, 1)
    assert segunda.pagina == 2
    acotada, _ = t.buscar_n(termino, 99)  # se acota a la última
    assert acotada.pagina == 2
    assert t.buscar_n(["Nadie Inexistente"], 0) == (None, 0)


def test_varias_variantes_cuentan_en_orden_de_lectura(doc):
    t = V.TextoPDF(doc)
    aps = [t.buscar_n(["Claudia Ornelas", "RICF900822K77"], n)[0].pagina for n in range(2)]
    assert aps == [1, 2]


def test_indice_de_texto_plano_es_perezoso(doc):
    t = V.TextoPDF(doc)
    assert not t.completo
    assert t.indexar(2) is False
    assert t._plano[2] is None
    assert t.indexar(5) is True and t.completo


def test_cajas_por_caracter_se_guardan_con_limite(doc, monkeypatch):
    monkeypatch.setattr(V, "PAGINAS_CON_CAJAS", 2)
    t = V.TextoPDF(doc)
    for i in range(3):
        t.pagina(i)
    assert list(t._paginas) == [1, 2]


def test_resaltados_lo_seleccionado_tapa_a_lo_marcado(doc):
    t = V.TextoPDF(doc)
    tenues, sel = t.resaltados_en(2, ["María Fernanda Ríos Calderón", "Claudia Ornelas"], ["María Fernanda Ríos Calderón"])
    assert len(sel) == 1 and len(tenues) == 1
    assert doc[2].get_textbox(tenues[0]).strip() == "Claudia Ornelas"


def test_pagina_girada_da_rectangulos_dentro_de_la_pagina():
    d = _pdf([[(72, 100, "Hola Ernesto Zedillo")]], rotar=90)
    t = V.TextoPDF(d)
    (ap,) = t.apariciones_en(0, ["Ernesto Zedillo"])
    assert d[0].rect.contains(ap.rects[0])
    assert ap.rects[0].height > ap.rects[0].width  # en la página girada el renglón va en vertical


def test_capa_de_texto_del_procesador(tmp_path, doc):
    """Con la capa que ya extrajo DocumentoPDF (incluido el OCR) no se vuelve a extraer nada."""
    from anonimizador.procesadores.pdf import DocumentoPDF

    ruta = tmp_path / "x.pdf"
    doc.save(str(ruta))
    dp = DocumentoPDF(ruta, usar_ocr=False)
    t = V.TextoPDF(pymupdf.open(str(ruta)), dp.texto, dp._chars)
    assert t.completo
    assert t.conteo_por_pagina(["María Fernanda Ríos Calderón"]) == [(1, 1), (2, 1)]
    (ap,) = t.apariciones_en(1, ["María Fernanda Ríos Calderón"])
    assert len(ap.rects) == 2


# --- caché, disposición e imagen -------------------------------------------------------


def test_cache_lru_respeta_el_limite_de_bytes():
    c = V.CacheLRU(limite_bytes=100)
    c.put("a", 1, 40)
    c.put("b", 2, 40)
    assert c.get("a") == 1  # «a» pasa a ser la más reciente
    c.put("c", 3, 40)  # 120 > 100: sale la menos usada, «b»
    assert "b" not in c and c.get("a") == 1 and c.get("c") == 3
    assert c.bytes == 80
    c.put("c", 3, 10)
    assert c.bytes == 50
    c.clear()
    assert len(c) == 0 and c.bytes == 0


def test_disposicion_y_paginas_visibles():
    d = V.Disposicion([(600, 800)] * 10, zoom=0.5, ancho_vista=500)
    assert d.tops[0] == V.MARGEN
    assert d.tops[1] == V.MARGEN + 400 + V.SEPARACION
    assert d.ancho == 500 and d.caja(0)[0] == (500 - 300) // 2
    assert d.pagina_en(0) == 0 and d.pagina_en(d.tops[3] + 5) == 3
    assert d.visibles(d.tops[3] + 5, d.tops[4] + 5, margen=1) == [2, 3, 4, 5]
    assert d.visibles(d.alto, d.alto + 100, margen=1) == [8, 9]


def test_zoom_para_ancho():
    assert V.zoom_para_ancho([(612, 792), (500, 700)], 612 + 2 * V.MARGEN) == pytest.approx(1.0)
    assert V.zoom_para_ancho([], 800) == 1.0


def test_componer_pinta_sin_borrar_la_tinta(doc):
    zoom = 1.0
    base = V.dibujar_pagina(doc[2], zoom)
    t = V.TextoPDF(doc)
    tenues, sel = t.resaltados_en(2, ["Claudia Ornelas"], ["María Fernanda Ríos Calderón"])
    img = V.componer(base, tenues, sel, zoom)
    assert img is not base and img.size == base.size
    r = sel[0]
    # El fondo blanco dentro del dato seleccionado se tiñe de dorado…
    tenido = [img.getpixel((x, int(r.y0) + 1)) for x in range(int(r.x0) + 2, int(r.x1) - 2)]
    assert any(p != (255, 255, 255) for p in tenido)
    # …y la tinta sigue oscura (se multiplica, no se tapa).
    oscuros_antes = sum(1 for p in base.crop(tuple(map(int, r))).get_flattened_data() if sum(p) < 200)
    oscuros_despues = sum(1 for p in img.crop(tuple(map(int, r))).get_flattened_data() if sum(p) < 200)
    assert oscuros_despues >= oscuros_antes > 0
    assert V.componer(base, [], [], zoom) is base


# --- el componente (necesita pantalla) -------------------------------------------------


def _hay_pantalla() -> bool:
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return False
    try:
        import tkinter

        tkinter.Tk().destroy()
        return True
    except Exception:
        return False


@pytest.mark.skipif(not _hay_pantalla(), reason="sin pantalla")
def test_componente_pdf_y_texto(tmp_path, doc):
    import customtkinter as ctk

    ruta = tmp_path / "x.pdf"
    doc.save(str(ruta))
    raiz = ctk.CTk()
    raiz.geometry("500x700")
    try:
        v = V.VisorDocumento(raiz)
        v.pack(fill="both", expand=True)
        raiz.update()
        assert v.cargar(ruta) and v.modo == "pdf" and v.num_paginas == 3
        for _ in range(20):
            raiz.update()
        assert v._fotos, "no se dibujó ninguna página"
        v.resaltar(["María Fernanda Ríos Calderón"], ["María Fernanda Ríos Calderón"])
        assert v.ir_a("María Fernanda Ríos Calderón", 1) == 2
        raiz.update()
        assert v.pagina_actual == 3
        v.ir_a_pagina(1)
        raiz.update()
        assert v.pagina_actual == 1
        v.zoom(1.5)
        assert not v._ajustar
        v.ajustar()
        assert v._ajustar
        assert not v.cargar(tmp_path / "no-existe.pdf")
        assert v._doc is None and v.modo is None

        v.cargar_texto("Comparece MARÍA FERNANDA\nRÍOS CALDERÓN y luego María Fernanda Ríos Calderón.", "x.docx")
        v.resaltar(["María Fernanda Ríos Calderón"], ["María Fernanda Ríos Calderón"])
        assert v.ir_a("María Fernanda Ríos Calderón", 1) == 2
        assert len(v.cuadro._textbox.tag_ranges("seleccion")) == 4  # dos tramos (inicio, fin)

        # Un documento ya abierto se usa y no se cierra al cambiar de archivo.
        abierto = pymupdf.open(str(ruta))
        assert v.cargar(abierto)
        v.cerrar()
        assert not abierto.is_closed
    finally:
        raiz.destroy()


# --- tramo exacto en una capa de texto (lo que usa ir_a_posicion) -----------------------


class _Car:
    def __init__(self, pagina, rect):
        self.pagina, self.rect = pagina, rect


def test_tramo_en_capa_da_pagina_y_un_rect_por_renglon():
    # "AB\nCD" en la página 1: A y B en un renglón, C y D en el siguiente; el salto sin caja
    capa = [_Car(1, pymupdf.Rect(10, 10, 20, 22)), _Car(1, pymupdf.Rect(20, 10, 30, 22)), _Car(1, None),
            _Car(1, pymupdf.Rect(10, 30, 20, 42)), _Car(1, pymupdf.Rect(20, 30, 30, 42))]
    pagina, rects = V.tramo_en_capa(capa, 0, 5)
    assert pagina == 1
    assert [tuple(r) for r in rects] == [(10, 10, 30, 22), (10, 30, 30, 42)]
    assert V.tramo_en_capa(capa, 2, 3) is None  # solo el salto: nada que señalar


def test_tramo_en_capa_que_cruza_de_pagina_se_queda_con_la_primera():
    capa = [_Car(0, pymupdf.Rect(10, 700, 20, 712)), _Car(1, pymupdf.Rect(10, 40, 20, 52))]
    pagina, rects = V.tramo_en_capa(capa, 0, 2)
    assert pagina == 0 and len(rects) == 1


def test_tramo_en_capa_coincide_con_la_capa_de_documento_pdf(tmp_path, doc):
    from anonimizador.procesadores.pdf import DocumentoPDF

    ruta = tmp_path / "x.pdf"
    doc.save(ruta)
    d = DocumentoPDF(ruta, usar_ocr=False)
    i = d.texto.index("RÍOS CALDERÓN")
    pagina, rects = V.tramo_en_capa(d._chars, i, i + len("RÍOS CALDERÓN"))
    assert pagina == 1
    assert rects and abs(rects[0].y1 - 124) < 6  # el renglón de y=124
