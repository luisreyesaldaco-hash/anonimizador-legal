import pytest

import docx_hostil
from anonimizador.flujo import Flujo, revertir_con_archivo


@pytest.fixture
def flujo(tmp_path):
    f = Flujo()
    f.cargar(docx_hostil.crear(tmp_path / "demanda.docx"))
    return f


def test_categorias_y_contexto(flujo):
    cats = dict(flujo.entidades_por_categoria())
    assert "Personas" in cats and "Identificaciones" in cats
    ctx = flujo.contextos("PERSONA_1")
    assert len(ctx) == flujo.apariciones("PERSONA_1") >= 3
    assert ctx[0].valor == "Juan Pérez García" and ctx[0].antes.endswith("el C. ")


def test_exige_revision(flujo, tmp_path):
    with pytest.raises(ValueError, match="revisa"):
        flujo.guardar(tmp_path / "salida.docx")


def test_guardar_y_revertir(flujo, tmp_path):
    flujo.revisado = True
    salida, _ = flujo.rutas_sugeridas()
    r = flujo.guardar(salida)
    assert r.limpio and r.salida.exists() and r.tabla.name == "demanda_tabla.json"
    assert "[PERSONA_1]" in r.texto_limpio
    assert revertir_con_archivo(r.tabla, "Hola [PERSONA_1] y [PERSONA_9]") == ("Hola Juan Pérez García y [PERSONA_9]", ["[PERSONA_9]"])


def test_no_sobrescribe_original(flujo):
    flujo.revisado = True
    with pytest.raises(ValueError, match="original"):
        flujo.guardar(flujo.ruta)
