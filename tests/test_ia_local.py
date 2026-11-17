"""IA local (Ollama) sin Ollama: se reemplaza la llamada HTTP por respuestas fijas."""

import json

import pytest

from anonimizador import ia_local
from anonimizador.flujo import Flujo, texto_tapado
from anonimizador.seudonimos import MANUAL

TEXTO = (
    "En la Ciudad de México, el día seis de octubre de dos mil veintiséis, ante el Lic. Juan Pérez López,\n"
    "Notario Público número 318, comparece María González Ruiz con escritura pública número 84,215.\n\n"
    "Domicilio: Calle Reforma 222, Col. Obrera del Sur, CDMX. Folio de constancia: CNC-2026-031877.\n"
    "Sello digital: 7Hq2+kD9vXw0Lz8RcY1mFt5aBn3sPe6Uo4Gi==\n\nPágina 1 de 2\n"
)


def respuesta(*hallazgos):
    return json.dumps({"hallazgos": [{"texto": t, "tipo": tipo, "motivo": ""} for t, tipo in hallazgos]})


def test_filtrar_descarta_lo_inventado_lo_tapado_y_las_paginas():
    r = respuesta(("seis de octubre de dos mil veintiséis", "FECHA"),
                  ("escrito público número 84,215", "ESCRITURA"),  # «corregido» por el modelo: no está
                  ("[PERSONA_1]", "PERSONA"),
                  ("Página 1 de 2", "OTRO"),
                  ("Lic. [PERSONA_1]", "PERSONA"),  # queda «Lic.»: no se tapa un tratamiento
                  ("[DOMICILIO_1]. Obrera del Sur", "DOMICILIO"),
                  ("SEIS DE OCTUBRE DE DOS MIL VEINTISÉIS", "FECHA"))  # repetida
    textos = [s.texto for s in ia_local.filtrar(r, TEXTO.replace("Calle Reforma 222, Col", "[DOMICILIO_1]"))]
    assert textos == ["seis de octubre de dos mil veintiséis", "Obrera del Sur"]


def test_filtrar_tolera_basura():
    assert ia_local.filtrar("no es json", TEXTO) == []
    assert ia_local.filtrar('{"hallazgos": "x"}', TEXTO) == []
    assert ia_local.filtrar('{"hallazgos": [1, {"texto": null}]}', TEXTO) == []


def test_tipos_se_traducen_al_detector():
    r = respuesta(("CNC-2026-031877", "FOLIO"), ("Obrera del Sur", "DOMICILIO"), ("318", "RARO"))
    tipos = {s.texto: s.tipo for s in ia_local.filtrar(r, TEXTO)}
    assert tipos == {"CNC-2026-031877": "FOLIO", "Obrera del Sur": "DOMICILIO", "318": MANUAL}


@pytest.mark.parametrize("url", ["https://api.ejemplo.com", "http://8.8.8.8:11434", "http://ollama.ejemplo.com"])
def test_solo_maquina_local_o_red_privada(monkeypatch, url):
    monkeypatch.setenv("ANONIMIZADOR_OLLAMA", url)
    with pytest.raises(ia_local.SinIALocal):
        ia_local.direccion()


@pytest.mark.parametrize("url", ["http://localhost:11434", "http://127.0.0.1:1", "http://192.168.1.20:11434"])
def test_direcciones_permitidas(monkeypatch, url):
    monkeypatch.setenv("ANONIMIZADOR_OLLAMA", url)
    assert ia_local.direccion() == url


def test_elegir_modelo():
    assert ia_local.elegir_modelo(["llama3.1:8b", "gemma3:12b", "gemma3:27b"]) == "gemma3:27b"
    assert ia_local.elegir_modelo(["gemma3:12b"]) == "gemma3:12b"
    with pytest.raises(ia_local.SinIALocal, match="ollama pull gemma3:12b"):
        ia_local.elegir_modelo(["llama3.1:8b"])
    with pytest.raises(ia_local.SinIALocal, match="ollama.com"):
        ia_local.elegir_modelo([])
    # Solo gemma3 de 27b o 12b: con otro modelo (aunque sea gemma3:4b) se ofrece instalar.
    with pytest.raises(ia_local.FaltaInstalar) as falta:
        ia_local.elegir_modelo(["gemma3:4b"])
    assert falta.value.hay_ollama
    with pytest.raises(ia_local.FaltaInstalar) as falta:
        ia_local.elegir_modelo([])
    assert not falta.value.hay_ollama


def test_trozos_cortan_por_parrafo():
    texto = ("a" * 50 + "\n\n") * 10
    partes = ia_local.trozos(texto, tam=120)
    assert "".join(partes) == texto
    assert all(len(p) <= 120 for p in partes)


def test_flujo_agrega_sugerencias_marcadas(tmp_path, monkeypatch):
    doc = tmp_path / "constancia.txt"
    doc.write_text(TEXTO, encoding="utf-8")
    flujo = Flujo(usar_ner=False)
    flujo.cargar(doc)
    vistos = []

    def falso(ruta, cuerpo=None, espera=2.0):
        vistos.append(cuerpo["messages"][0]["content"])
        return {"message": {"content": respuesta(
            ("seis de octubre de dos mil veintiséis", "FECHA"), ("Notario Público número 318", "NOTARIA"),
            ("84,215", "ESCRITURA"), ("Obrera del Sur", "DOMICILIO"),
            ("7Hq2+kD9vXw0Lz8RcY1mFt5aBn3sPe6Uo4Gi==", "SELLO"))}}

    monkeypatch.setattr(ia_local, "_pedir", falso)
    antes = len(flujo.sesion.entidades)
    partes = []
    nuevas = flujo.sugerir_con_ia("gemma3:12b", avance=lambda parte, total: partes.append((parte, total)))
    assert partes == [(1, 1)]
    assert len(flujo.sesion.entidades) == antes + len(nuevas)
    assert all(e.sugerida and e.marcada for e in nuevas)
    tapado = texto_tapado(flujo.documentos[0].texto, flujo.sesion)
    for dato in ("seis de octubre", "número 318", "84,215", "Obrera del Sur", "7Hq2"):
        assert dato not in tapado, dato
    # A la IA le llega el texto ya tapado: lo que el detector encontró no viaja.
    assert "Reforma 222" not in vistos[0] and "[DOMICILIO_1]" in vistos[0]
    assert flujo.revisado is False


def test_flujo_sin_ollama(tmp_path, monkeypatch):
    doc = tmp_path / "a.txt"
    doc.write_text(TEXTO, encoding="utf-8")
    flujo = Flujo(usar_ner=False)
    flujo.cargar(doc)
    monkeypatch.setattr(ia_local, "modelos_instalados", lambda: [])
    with pytest.raises(ia_local.SinIALocal):
        flujo.sugerir_con_ia()
