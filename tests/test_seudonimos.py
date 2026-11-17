import pytest

from anonimizador.detector import detectar
from anonimizador.seudonimos import Sesion, plegar, revertir

TEXTO = (
    "VISTOS los autos del juicio promovido por JUAN PÉREZ GARCÍA en contra de Inmobiliaria "
    "Los Pinos, S.A. de C.V. y de la señora Ana María Soto Vega, con RFC GODE-561231-GR8. "
    "El actor Pérez García manifestó que el C. Pérez pagó a la señora Soto. Ana María Soto "
    "Vega negó todo. Se notifica a juan.perez@ejemplo.com y al RFC GODE561231GR8."
)


@pytest.fixture
def sesion():
    return Sesion(TEXTO, detectar(TEXTO, usar_ner=False))


def test_plegar_conserva_longitud():
    s = "ÁÉÍÓÚ Ñandú Über"
    assert len(plegar(s)) == len(s) and plegar(s) == "aeiou nandu uber"


def test_etiquetas_por_orden_de_aparicion(sesion):
    etiquetas = {e.etiqueta: e.canonico for e in sesion.entidades}
    assert etiquetas["PERSONA_1"] == "JUAN PÉREZ GARCÍA"
    assert etiquetas["PERSONA_2"] == "Ana María Soto Vega"
    assert etiquetas["RFC_1"] == "GODE-561231-GR8"


def test_variantes_y_duplicados_se_unen(sesion):
    limpio = sesion.texto_limpio()
    assert "Pérez" not in limpio and "PÉREZ" not in limpio and "Soto" not in limpio
    assert "GODE" not in limpio and "juan.perez" not in limpio
    assert limpio.count("[PERSONA_1]") == 3  # nombre completo, apellidos y "el C. Pérez"
    assert limpio.count("[RFC_1]") == 2  # con y sin guiones


def test_empresa_parte_del_asunto_llega_marcada(sesion):
    assert sesion.entidad("EMPRESA_1").marcada  # "en contra de Inmobiliaria Los Pinos"
    assert "Inmobiliaria Los Pinos" not in sesion.texto_limpio()


def test_empresa_de_paso_llega_desmarcada():
    t = ("El C. Juan Pérez García exhibió estados de cuenta.\n\nLos depósitos se hicieron en "
         "BBVA México, S.A. y el pago se acreditó.")
    s = Sesion(t, detectar(t, usar_ner=False))
    empresa = s.entidad("EMPRESA_1")
    assert not empresa.marcada
    assert "BBVA México" in s.texto_limpio()
    s.marcar("EMPRESA_1")
    assert "BBVA México" not in s.texto_limpio()


def test_despacho_con_apellidos_llega_marcado():
    t = ("Comparece la Lic. Mariana Arriaga Solís.\n\nNotificaciones en las oficinas de "
         "Arriaga, Solís & Mendoza Abogados, S.C.")
    s = Sesion(t, detectar(t, usar_ner=False))
    assert s.entidad("EMPRESA_1").marcada
    assert "Arriaga" not in s.texto_limpio() and "Mendoza" not in s.texto_limpio()


def test_apellido_ambiguo_no_se_propaga():
    t = "comparecen los señores Pedro Ramírez Ortiz y Lucía Ramírez Ortiz. El señor Ramírez firmó."
    s = Sesion(t, detectar(t, usar_ner=False))
    assert "El señor Ramírez firmó" in s.texto_limpio()  # no se sabe de quién es: lo decide el abogado


def test_renombrar_fusionar_separar_y_manual(sesion):
    sesion.renombrar("PERSONA_1", "actor")
    assert "[ACTOR]" in sesion.texto_limpio()
    sesion.fusionar("ACTOR", "PERSONA_2")
    assert "[PERSONA_2]" not in sesion.texto_limpio()
    nueva = sesion.separar("ACTOR", "Ana María Soto Vega")
    assert nueva.etiqueta == "PERSONA_3"  # no recicla PERSONA_1 ni PERSONA_2: pudieron llegar a la IA
    manual = sesion.agregar_manual("VISTOS")
    assert manual.etiqueta == "MANUAL_1" and "VISTOS" not in sesion.texto_limpio()
    with pytest.raises(ValueError):
        sesion.renombrar("MANUAL_1", "ACTOR")


def test_revertir_tolera_formatos_de_la_ia(sesion):
    tabla = sesion.tabla(archivo="demanda.docx", contenido=b"x")
    assert tabla["documento"]["archivo"] == "demanda.docx"
    respuesta = "[PERSONA_1] y Persona 2 discuten; ver [ rfc_1 ]. PERSONA_10 no existe."
    assert revertir(respuesta, tabla) == (
        "JUAN PÉREZ GARCÍA y Ana María Soto Vega discuten; ver GODE-561231-GR8. PERSONA_10 no existe."
    )


def test_revertir_ida_y_vuelta(sesion):
    tabla = sesion.tabla()
    vuelta = revertir(sesion.texto_limpio(), tabla)
    assert "JUAN PÉREZ GARCÍA" in vuelta and "Ana María Soto Vega" in vuelta


def test_revertir_rechaza_otro_json():
    with pytest.raises(ValueError):
        revertir("hola", {"entidades": []})


def test_empresa_cubre_sigla_y_nombre_sin_sufijo():
    t = "INDUSTRIAS METÁLICAS DEL VALLE\nContrato con Industrias Metálicas del Valle, S.A. de C.V. (IMV). IMVA no."
    s = Sesion(t, detectar(t, usar_ner=False))
    for e in s.entidades:
        s.marcar(e.etiqueta, True)
    assert s.texto_limpio() == "[EMPRESA_1]\nContrato con [EMPRESA_1] ([EMPRESA_1]). IMVA no."


def test_etiquetas_no_se_reciclan(sesion):
    sesion.renombrar("PERSONA_1", "ACTOR")
    nueva = sesion.separar("ACTOR", next(v for v in sesion.entidad("ACTOR").variantes[1:]))
    assert nueva.etiqueta != "PERSONA_1"  # PERSONA_1 ya pudo llegar a la IA con otro valor


def test_manual_que_no_aparece_no_se_agrega(sesion):
    antes = len(sesion.entidades)
    with pytest.raises(ValueError, match="no aparece"):
        sesion.agregar_manual("Rancho El Ocote")
    assert len(sesion.entidades) == antes


def test_dos_apellidos_sueltos_se_ligan_a_la_persona():
    t = ("Asunto: Ríos Calderón vs. IMV.\n\nNotas de la entrevista con la C. María Fernanda Ríos. "
         "La Lic. Paola Durán tomó notas.")
    s = Sesion(t, detectar(t, usar_ner=False))
    limpio = s.texto_limpio()
    assert "Calderón" not in limpio and "Ríos" not in limpio
    assert "Durán tomó" not in limpio  # "Durán" sigue de un verbo en minúscula: no se toca nada más


def test_apellido_en_el_renglon_siguiente():
    t = "otorgada ante la fe del Notario Público número 318, Lic. Everardo Juncos\nValdivia.\n\nOtro párrafo."
    s = Sesion(t, detectar(t, usar_ner=False))
    assert "Valdivia" not in s.texto_limpio()


def test_cargo_bajo_la_firma_no_es_apellido():
    # Word: cada párrafo es un renglón. «Socia» no se pega al nombre ni desaparece al anonimizar.
    t = "Atentamente,\nLic. Fernanda Ortiz Villaseñor\nSocia · Cédula profesional 10458872\n"
    s = Sesion(t, detectar(t, usar_ner=False))
    assert "Socia · Cédula profesional" in s.texto_limpio()


def test_dos_saltos_separan_parrafos():
    t = "Firma: Lic. Everardo Juncos\n\nValdivia y Asociados es otro tema."
    s = Sesion(t, detectar(t, usar_ner=False))
    assert "Valdivia y Asociados" in s.texto_limpio()


def test_nombre_de_pila_suelto():
    t = ("Notas de la C. María Fernanda Ríos.\n\nEntré con Arturo en 2017. Jorge quiere el borrador. "
         "La Escuela Benito Juárez queda cerca. Rosa de los vientos. Luis Ángel Pacheco y Luis firmaron.")
    s = Sesion(t, detectar(t, usar_ner=False))
    limpio = s.texto_limpio()
    assert "Arturo" not in limpio and "Jorge" not in limpio
    assert "Benito Juárez" in limpio and "Rosa de los vientos" in limpio
    assert "y [PERSONA_" in limpio and " Luis firmaron" not in limpio  # Luis es de Luis Ángel Pacheco


def test_nombre_de_pila_de_dos_personas_no_se_adivina():
    t = "Comparecen Juan Pérez López y Juan Gómez Ruiz.\n\nJuan dijo que sí."
    s = Sesion(t, detectar(t, usar_ner=False))
    assert "Juan dijo" in s.texto_limpio()


def test_dato_desmarcado_no_se_tapa_a_pedazos():
    t = "Entrevista: 8-sep-2026, 17:00. Lo básico (8-sep)."
    s = Sesion(t, detectar(t, usar_ner=False))
    larga = next(e for e in s.entidades if e.canonico == "8-sep-2026")
    s.marcar(larga.etiqueta, False)
    assert "8-sep-2026" in s.texto_limpio()  # no "[FECHA_2]-2026"
    assert "([FECHA_" in s.texto_limpio()


def test_despacho_desmarcado_no_protege_a_la_persona():
    t = ("Comparece la Lic. Mariana Arriaga Solís.\n\nOficinas de Arriaga Solís y Asociados, S.C.")
    s = Sesion(t, detectar(t, usar_ner=False))
    for e in s.entidades:
        if e.tipo == "EMPRESA":
            s.marcar(e.etiqueta, False)
    assert "Arriaga" not in s.texto_limpio()
