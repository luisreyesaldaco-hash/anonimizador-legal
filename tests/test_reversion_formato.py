"""El Word que entrega la IA, revertido, tiene que quedar idéntico salvo el texto de las etiquetas.

`datos/respuesta_ia_docxjs.docx` lo generó docx-js (la librería con la que Claude arma sus
.docx; script al lado, `respuesta_ia_docxjs.js`): título, índice, encabezado y pie con número de
página, nota al pie, comentario, enlace mailto, cambios controlados, listas, tabla con celdas
combinadas y sombreado, imagen. Las etiquetas están en todos esos lugares, y alguna partida en
dos runs con formato distinto.
"""

import re
import urllib.parse
import zipfile
from pathlib import Path

from lxml import etree

from anonimizador.reversion import revertir_docx
from anonimizador.seudonimos import FORMATO_TABLA

ENTRADA = Path(__file__).parent / "datos" / "respuesta_ia_docxjs.docx"
VALORES = {"PERSONA_1": "María José Pérez López", "PERSONA_2": "Juan <Ramírez> Soto",
           "EMPRESA_1": "Pérez & Asociados, S.C.", "DOMICILIO_1": "Av. Insurgentes Sur 1602, Col. Crédito Constructor",
           "EXPEDIENTE_1": "1234/2026", "FECHA_1": "6 de octubre de 2026", "RFC_1": "PELM800101AB1",
           "RFC_2": "PAS990101XY2", "CORREO_1": "maria.perez@ejemplo.mx", "CUENTA_1": "012180001234567891",
           "TELEFONO_1": "55 1234 5678"}
TABLA = {"formato": FORMATO_TABLA, "entidades": [{"etiqueta": k, "original": v} for k, v in VALORES.items()]}
W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
ETIQUETA = re.compile(r"(%s)" % "|".join(VALORES))


def _esqueleto(xml: bytes) -> bytes:
    """El XML sin su texto: lo que define el formato."""
    raiz = etree.fromstring(xml)
    for n in raiz.iter():
        if n.tag in (W + "t", W + "delText", W + "instrText") or (
                len(n) == 0 and n.tag.startswith("{http://purl.org/dc")):
            n.text = None
            n.attrib.pop("{http://www.w3.org/XML/1998/namespace}space", None)
        if "Target" in n.attrib:
            n.set("Target", "")
    return etree.tostring(raiz, method="c14n")


def test_word_de_la_ia_queda_identico_salvo_las_etiquetas(tmp_path):
    salida = tmp_path / "revertido.docx"
    r = revertir_docx(ENTRADA, salida, TABLA)
    assert r.desconocidas == []
    a, b = zipfile.ZipFile(ENTRADA), zipfile.ZipFile(salida)
    # Mismas entradas, en el mismo orden y con la misma compresión.
    assert [(i.filename, i.compress_type) for i in a.infolist()] == [(i.filename, i.compress_type)
                                                                     for i in b.infolist()]
    cambiadas = set()
    for nombre in a.namelist():
        original, nuevo = a.read(nombre), b.read(nombre)
        if nombre.endswith(("xml", ".rels")):
            # Ninguna etiqueta queda en ningún lado (ni en el título, comentarios, lo tachado o el mailto).
            assert not ETIQUETA.search(urllib.parse.unquote(nuevo.decode("utf8"))), nombre
        if original != nuevo:
            cambiadas.add(nombre)
            assert _esqueleto(original) == _esqueleto(nuevo), f"cambió el formato de {nombre}"
    # Lo que no llevaba etiquetas sale byte por byte igual (estilos, numeración, imagen…).
    assert cambiadas == {"word/document.xml", "word/header1.xml", "word/footer1.xml", "word/footnotes.xml",
                         "word/comments.xml", "docProps/core.xml", "word/_rels/document.xml.rels"}
    texto = b.read("word/document.xml").decode()
    assert "Pérez &amp; Asociados, S.C." in texto and "Juan &lt;Ramírez&gt; Soto" in texto
    assert 'Target="mailto:maria.perez@ejemplo.mx"' in b.read("word/_rels/document.xml.rels").decode()
