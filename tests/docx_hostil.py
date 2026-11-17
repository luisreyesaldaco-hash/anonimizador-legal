"""Genera un .docx que reúne los lugares donde suelen fugarse datos."""

from __future__ import annotations

from pathlib import Path

import docx
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.oxml import parse_xml

W = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
NS_TXBX = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:wps="http://schemas.microsoft.com/office/word/2010/wordprocessingShape"'
)

NOMBRE = "Juan Pérez García"
CORREO = "juan.perez@ejemplo.com"
BORRADO = "Roberto Sánchez Medina"


def crear(ruta: Path) -> Path:
    doc = docx.Document()
    doc.core_properties.author = "Lic. Gabriela Ochoa Ríos"
    doc.core_properties.title = f"Demanda de {NOMBRE}"

    # 1. Nombre partido en runs con distinto formato.
    p = doc.add_paragraph("Comparece el C. ")
    p.add_run("Juan ").bold = True
    r = p.add_run("Pé")
    r.bold = True
    r.italic = True
    p.add_run("rez Gar").bold = True
    p.add_run("cía, por su propio derecho, con RFC GODE561231GR8.")

    # 2. Cambio controlado: texto borrado e insertado.
    doc.add_paragraph()._p.append(parse_xml(
        f'<w:r {W}><w:t xml:space="preserve">Se desiste respecto de </w:t></w:r>'
    ))
    par = doc.paragraphs[-1]._p
    par.append(parse_xml(
        f'<w:del {W} w:id="1" w:author="Abogado Revisor" w:date="2026-01-01T00:00:00Z">'
        f'<w:r><w:delText xml:space="preserve">el señor {BORRADO}</w:delText></w:r></w:del>'
    ))
    par.append(parse_xml(
        f'<w:ins {W} w:id="2" w:author="Abogado Revisor" w:date="2026-01-01T00:00:00Z">'
        f'<w:r><w:t xml:space="preserve">la parte demandada.</w:t></w:r></w:ins>'
    ))

    # 3. Comentario.
    pc = doc.add_paragraph("Notificar al actor.")
    doc.add_comment(pc.runs, text=f"Confirmar domicilio de {NOMBRE}", author="Gabriela Ochoa Ríos", initials="GO")

    # 4. Hipervínculo mailto.
    ph = doc.add_paragraph("Correo: ")
    rid = ph.part.relate_to(f"mailto:{CORREO}", RT.HYPERLINK, is_external=True)
    ph._p.append(parse_xml(
        f'<w:hyperlink {W} xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
        f'r:id="{rid}"><w:r><w:t>{CORREO}</w:t></w:r></w:hyperlink>'
    ))

    # 5. Tabla.
    t = doc.add_table(rows=1, cols=2)
    t.cell(0, 0).text = "Actor"
    t.cell(0, 1).text = NOMBRE

    # 6. Cuadro de texto (DrawingML) dentro de un párrafo.
    doc.add_paragraph()._p.append(parse_xml(
        f'<w:r {NS_TXBX}><w:drawing><wp:anchor><wp:docPr id="9" name="Cuadro" descr="Firma de {NOMBRE}"/>'
        f'<a:graphic><a:graphicData><wps:wsp><wps:txbx><w:txbxContent>'
        f'<w:p><w:r><w:t>Firma: {NOMBRE}</w:t></w:r></w:p>'
        f'</w:txbxContent></wps:txbx></wps:wsp></a:graphicData></a:graphic></wp:anchor></w:drawing></w:r>'
    ))

    # 7. Campo con código (instrText).
    doc.add_paragraph()._p.append(parse_xml(
        f'<w:r {W}><w:instrText xml:space="preserve"> HYPERLINK "mailto:{CORREO}" </w:instrText></w:r>'
    ))

    # 8. Encabezado y pie.
    sec = doc.sections[0]
    sec.header.paragraphs[0].text = f"Expediente 1234/2024 — {NOMBRE}"
    sec.footer.paragraphs[0].text = f"Contacto: {CORREO}"

    doc.save(str(ruta))
    return ruta
