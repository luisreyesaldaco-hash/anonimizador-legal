const fs = require("fs");
const d = require("docx");
const { Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, ShadingType,
  AlignmentType, Header, Footer, PageNumber, ExternalHyperlink, FootnoteReferenceRun, LevelFormat, BorderStyle,
  TableOfContents, Bookmark, InternalHyperlink, CommentRangeStart, CommentRangeEnd, CommentReference,
  InsertedTextRun, DeletedTextRun, PageBreak, TabStopType, ImageRun, VerticalMergeType } = d;
const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
const borde = { style: BorderStyle.SINGLE, size: 4, color: "8a7350" };
const celda = (t, extra = {}) => new TableCell({ borders: { top: borde, bottom: borde, left: borde, right: borde },
  width: { size: 4680, type: WidthType.DXA }, margins: { top: 80, bottom: 80, left: 120, right: 120 },
  ...extra, children: [new Paragraph({ children: [new TextRun(t)] })] });
const doc = new Document({
  title: "Contrato con [PERSONA_1]", creator: "Claude",
  styles: { default: { document: { run: { font: "Garamond", size: 24 } } },
    paragraphStyles: [{ id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
      run: { size: 32, bold: true, color: "1F3864", font: "Garamond" }, paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 0 } }] },
  numbering: { config: [
    { reference: "num", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    { reference: "vin", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
      style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] } ] },
  footnotes: { 1: { children: [new Paragraph({ children: [new TextRun("Según escritura otorgada por [PERSONA_2] el [FECHA_1].")] })] } },
  comments: { children: [{ id: 0, author: "Claude", date: new Date(2026, 10, 1),
    children: [new Paragraph({ children: [new TextRun("Confirmar domicilio de [PERSONA_1]")] })] }] },
  sections: [{
    properties: { page: { size: { width: 12240, height: 15840 }, margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT,
      children: [new TextRun({ text: "Expediente [EXPEDIENTE_1] · [EMPRESA_1]", italics: true, size: 18, color: "666666" })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ text: "[PERSONA_1] — página ", size: 18 }), new TextRun({ children: [PageNumber.CURRENT], size: 18 })] })] }) },
    children: [
      new Paragraph({ heading: HeadingLevel.TITLE, alignment: AlignmentType.CENTER, children: [new TextRun("CONTRATO DE PRESTACIÓN DE SERVICIOS")] }),
      new TableOfContents("Índice", { hyperlink: true, headingStyleRange: "1-3" }),
      new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new Bookmark({ id: "partes", children: [new TextRun("Partes: [PERSONA_1]")] })] }),
      new Paragraph({ alignment: AlignmentType.JUSTIFIED, spacing: { line: 360 }, children: [
        new TextRun("Celebran el presente contrato, por una parte, "),
        new TextRun({ text: "[PERSONA_", bold: true }), new TextRun({ text: "1]", bold: true, italics: true }),
        new TextRun(", con domicilio en "), new TextRun({ text: "[DOMICILIO_1]", underline: {} }),
        new TextRun(", y por la otra "), new TextRun({ text: "[EMPRESA_1]", smallCaps: true, color: "8A7350" }),
        new FootnoteReferenceRun(1), new TextRun(", representada por [PERSONA_2]."),
        new TextRun({ text: "\tRFC: [RFC_1]", break: 1 })] }),
      new Paragraph({ children: [new CommentRangeStart(0), new TextRun("Correo de contacto: "),
        new ExternalHyperlink({ link: "mailto:[CORREO_1]", children: [new TextRun({ text: "[CORREO_1]", style: "Hyperlink" })] }),
        new CommentRangeEnd(0), new TextRun({ children: [new CommentReference(0)] })] }),
      new Paragraph({ numbering: { reference: "num", level: 0 }, children: [new TextRun("El pago se hará a la cuenta [CUENTA_1] de [PERSONA_1].")] }),
      new Paragraph({ numbering: { reference: "num", level: 0 }, children: [new TextRun("Vigencia a partir del "), new TextRun({ text: "[FECHA_1]", highlight: "yellow" }), new TextRun(".")] }),
      new Paragraph({ numbering: { reference: "vin", level: 0 }, children: [new TextRun("Teléfono: [TELEFONO_1]")] }),
      new Paragraph({ children: [new TextRun("Cambio propuesto: "), new InsertedTextRun({ text: "[PERSONA_2] firma", id: 1, author: "Claude", date: "2026-11-01T00:00:00Z" }),
        new DeletedTextRun({ text: "[PERSONA_1] firma", id: 2, author: "Claude", date: "2026-11-01T00:00:00Z" })] }),
      new Table({ width: { size: 9360, type: WidthType.DXA }, columnWidths: [4680, 4680], rows: [
        new TableRow({ tableHeader: true, children: [
          celda("Parte", { shading: { fill: "1F3864", type: ShadingType.CLEAR, color: "auto" } }),
          celda("Dato", { shading: { fill: "1F3864", type: ShadingType.CLEAR, color: "auto" } })] }),
        new TableRow({ children: [celda("Cliente", { verticalMerge: VerticalMergeType.RESTART }), celda("[PERSONA_1]")] }),
        new TableRow({ children: [celda("", { verticalMerge: VerticalMergeType.CONTINUE }), celda("[DOMICILIO_1]")] }),
        new TableRow({ children: [celda("Proveedor"), celda("[EMPRESA_1], [RFC_2]")] })] }),
      new Paragraph({ children: [new ImageRun({ type: "png", data: png, transformation: { width: 40, height: 40 } })] }),
      new Paragraph({ children: [new PageBreak()] }),
      new Paragraph({ tabStops: [{ type: TabStopType.RIGHT, position: 9360 }], children: [new TextRun("[PERSONA_1]\t[PERSONA_2]")] }),
      new Paragraph({ children: [new InternalHyperlink({ anchor: "partes", children: [new TextRun({ text: "Ver partes", style: "Hyperlink" })] })] }),
    ] }] });
Packer.toBuffer(doc).then(b => fs.writeFileSync(process.argv[2], b));
