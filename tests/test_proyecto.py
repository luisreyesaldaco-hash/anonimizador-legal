"""Proyectos de varios documentos: una revisión y una tabla para todos."""

import json

import docx
import pymupdf
import pytest

from anonimizador.cli import main
from anonimizador.flujo import ErrorDeDocumento, Flujo, revertir_con_archivo

JUAN = "Juan Pérez García"
MARIA = "María López Hernández"


def _contrato(ruta):
    d = docx.Document()
    d.add_paragraph(f"Contrato individual de trabajo que celebra el C. {JUAN}, con RFC GODE561231GR8.")
    d.add_paragraph(f"Firma el trabajador {JUAN}. Correo juan.perez@ejemplo.com")
    d.add_paragraph("Al final del contrato queda el nombre Juan")
    d.save(str(ruta))
    return ruta


def _renuncia(ruta):
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_text((72, 72), "Pérez renuncia de forma voluntaria.", fontsize=11)
    p.insert_text((72, 90), f"Yo, el C. {JUAN}, presento mi renuncia ante la C. {MARIA}.", fontsize=11)
    p.insert_text((72, 108), "Correo de contacto maria.lopez@ejemplo.com", fontsize=11)
    doc.save(str(ruta))
    return ruta


@pytest.fixture
def archivos(tmp_path):
    return _contrato(tmp_path / "contrato.docx"), _renuncia(tmp_path / "renuncia.pdf")


@pytest.fixture
def proyecto(archivos):
    f = Flujo(usar_ner=False)
    f.cargar(list(archivos))
    return f


def _etiqueta_de(flujo, valor):
    return next(e.etiqueta for e in flujo.sesion.entidades if valor in e.variantes)


def test_misma_persona_misma_etiqueta(proyecto):
    assert [(d.nombre, d.tipo) for d in proyecto.documentos] == [("contrato.docx", "docx"), ("renuncia.pdf", "pdf")]
    juan = _etiqueta_de(proyecto, JUAN)
    assert juan == "PERSONA_1"
    assert len([e for e in proyecto.sesion.entidades if JUAN in e.variantes]) == 1
    por_doc = proyecto.apariciones_por_documento(juan)
    assert por_doc[0] >= 2 and por_doc[1] >= 1 and proyecto.apariciones(juan) == sum(por_doc)
    ctx = proyecto.contextos(juan)
    assert {c.documento for c in ctx} == {"contrato.docx", "renuncia.pdf"}
    assert {c.valor for c in ctx} >= {JUAN, "Juan"}  # "Juan" suelto también es él
    ub = [u for u in proyecto.ubicaciones(juan) if u.documento == "renuncia.pdf"]
    assert ub and ub[0].indice == 1 and ub[0].pagina == 1
    assert proyecto.documentos[1].texto[ub[0].inicio:ub[0].fin] == JUAN


def test_nada_se_empalma_entre_documentos(proyecto):
    # El contrato termina en "Juan" y la renuncia empieza con "Pérez": no es una aparición.
    with pytest.raises(ValueError, match="no aparece"):
        proyecto.sesion.agregar_manual("Juan Pérez renuncia")


def test_guardar_todos_y_revertir(proyecto, archivos):
    proyecto.revisado = True
    r = proyecto.guardar_todos()
    assert r.limpio, r.fugas
    assert [s.name for s in r.salidas] == ["contrato_anonimizado.docx", "renuncia_anonimizado.pdf"]
    assert all(s.exists() for s in r.salidas)
    for original in archivos:  # los originales siguen intactos
        assert original.exists()
    assert r.tabla.name == "contrato_proyecto_tabla.json"

    with pymupdf.open(str(r.salidas[1])) as pdf:
        texto_pdf = pdf[0].get_text()
    assert JUAN not in texto_pdf and "[PERSONA_1]" in texto_pdf
    assert all(JUAN not in d.texto_limpio for d in r.documentos)
    assert "Documento 1 de 2: contrato.docx" in r.texto_limpio and "Documento 2 de 2: renuncia.pdf" in r.texto_limpio

    datos = json.loads(r.tabla.read_text(encoding="utf-8"))
    assert [d["archivo"] for d in datos["documentos"]] == ["contrato.docx", "renuncia.pdf"]
    assert all(len(d["sha256"]) == 64 for d in datos["documentos"])
    maria = _etiqueta_de(proyecto, MARIA)
    texto, desconocidas = revertir_con_archivo(r.tabla, f"[PERSONA_1] renunció ante [{maria}]; [RFC_1].")
    assert texto == f"{JUAN} renunció ante {MARIA}; GODE561231GR8." and desconocidas == []


def test_guardar_en_carpeta_y_dos_veces(proyecto, tmp_path):
    proyecto.revisado = True
    destino = tmp_path / "para_ia"
    r1 = proyecto.guardar_todos(destino)
    r2 = proyecto.guardar_todos(destino)  # el documento en memoria se reabre: no queda a medias
    assert all(s.parent == destino for s in r1.salidas + r2.salidas)
    assert r2.salidas[0].name == "contrato_anonimizado_2.docx" and r2.limpio
    assert r1.tabla != r2.tabla


def test_un_solo_documento_igual_que_antes(archivos):
    f = Flujo(usar_ner=False)
    f.cargar(archivos[0])
    assert f.ruta == archivos[0] and f.documento is f.documentos[0].documento
    f.revisado = True
    r = f.guardar_todos()
    assert r.tabla.name == "contrato_tabla.json" and r.texto_limpio == r.documentos[0].texto_limpio
    with pytest.raises(ValueError, match="guardar_todos"):
        g = Flujo(usar_ner=False)
        g.cargar(list(archivos))
        g.revisado = True
        g.guardar(archivos[0].with_name("x.docx"))


def test_error_dice_que_documento(archivos, tmp_path):
    roto = tmp_path / "roto.pdf"
    roto.write_bytes(b"%PDF-1.4 esto no es un pdf")
    f = Flujo(usar_ner=False)
    with pytest.raises(ErrorDeDocumento, match="roto.pdf") as err:
        f.cargar([archivos[0], roto])
    assert err.value.ruta == roto and f.sesion is None
    with pytest.raises(ValueError, match="ya está"):
        f.cargar([archivos[0], archivos[0]])


def test_agregar_conserva_la_revision(archivos):
    f = Flujo(usar_ner=False)
    f.cargar([archivos[0]])
    juan = _etiqueta_de(f, JUAN)
    f.sesion.renombrar(juan, "TRABAJADOR")
    f.sesion.marcar("RFC_1", False)
    manual = f.sesion.agregar_manual("Contrato individual de trabajo")
    f.revisado = True

    nuevos = f.agregar(archivos[1])
    assert [d.nombre for d in nuevos] == ["renuncia.pdf"] and not f.revisado
    e = f.sesion.entidad("TRABAJADOR")
    assert f.apariciones_por_documento("TRABAJADOR")[1] >= 1 and e.marcada
    assert not f.sesion.entidad("RFC_1").marcada
    assert f.sesion.entidad(manual.etiqueta).marcada
    maria = _etiqueta_de(f, MARIA)
    assert maria not in {juan, "TRABAJADOR"} and f.apariciones_por_documento(maria) == [0, 1]
    assert {c.documento for c in f.contextos("TRABAJADOR")} == {"contrato.docx", "renuncia.pdf"}

    f.revisado = True
    r = f.guardar_todos()
    assert r.limpio, r.fugas
    texto, _ = revertir_con_archivo(r.tabla, f"[TRABAJADOR] y [{maria}]")
    assert texto == f"{JUAN} y {MARIA}"


def test_quitar_documento(proyecto):
    maria = _etiqueta_de(proyecto, MARIA)
    quitado = proyecto.quitar(1)
    assert quitado.nombre == "renuncia.pdf" and len(proyecto.documentos) == 1
    with pytest.raises(KeyError):
        proyecto.sesion.entidad(maria)
    assert proyecto.apariciones_por_documento("PERSONA_1")[0] >= 2
    with pytest.raises(ValueError, match="al menos"):
        proyecto.quitar(0)


def test_cli_generar_varios(archivos, tmp_path, capsys):
    destino = tmp_path / "salidas"
    texto = tmp_path / "limpio.txt"
    args = ["generar", *map(str, archivos), "--sin-ner", "--salida", str(destino), "--texto", str(texto)]
    assert main(args) == 0
    assert (destino / "contrato_anonimizado.docx").exists() and (destino / "renuncia_anonimizado.pdf").exists()
    assert (destino / "contrato_proyecto_tabla.json").exists()
    assert JUAN not in texto.read_text(encoding="utf-8")
