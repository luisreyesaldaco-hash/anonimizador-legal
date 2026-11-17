"""Segunda revisión con una IA local (Ollama): sugiere datos que el detector dejó sin tapar.

Por qué local y solo local: la IA lee el documento. Si saliera de la computadora, el
anonimizador perdería su razón de ser. Por eso solo se habla con Ollama en esta máquina
(o en una dirección de red privada si se configura `ANONIMIZADOR_OLLAMA`); cualquier otra
dirección se rechaza.

Lo que se le manda es el texto YA tapado: lo que el detector encontró va como [PERSONA_1],
y la IA solo ve lo que quedó. Así revisa lo que se escapó (fechas en letra, folios,
escrituras, notarías, colonias, sellos) y además ve menos datos.

La IA sugiere, no decide: cada sugerencia se comprueba contra el texto (si no aparece tal
cual, se descarta: los modelos a veces "corrigen" lo que copian) y entra a la revisión
marcada como sugerida, para que el abogado la acepte o la desmarque.

Probado (nov-2026, constancia de no conciliación de demostración): gemma3:12b y gemma3:27b
encontraron los 6 datos que se habían escapado, sin inventar ninguno.
"""

from __future__ import annotations

import ipaddress
import json
import os
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass

from .detector import modelo as m
from .seudonimos import MANUAL
from .textos import tr

# Solo los probados, en orden de preferencia: el más grande (más preciso, menos ruido).
# Los chicos (gemma3:4b) no se usan: no se probaron y un revisor flojo da falsa confianza.
MODELOS_PREFERIDOS = ("gemma3:27b", "gemma3:12b")
MODELO_SUGERIDO = "gemma3:12b"  # cabe en una laptop de 16 GB; con 32 GB o más, gemma3:27b
TROZO = 6000  # caracteres por consulta (con margen para el contexto de 8k)

TIPOS = {"FECHA": m.FECHA, "FOLIO": m.FOLIO, "NOTARIA": m.FOLIO, "ESCRITURA": m.FOLIO, "SELLO": m.FOLIO,
         "EXPEDIENTE": m.EXPEDIENTE, "DOMICILIO": m.DOMICILIO, "TELEFONO": m.TELEFONO,
         "CORREO": m.CORREO, "CUENTA": m.CUENTA, "PERSONA": m.NOMBRE, "EMPRESA": m.EMPRESA}

INSTRUCCIONES = """Eres un revisor de anonimización de documentos legales. El texto ya pasó por un anonimizador: lo que está entre corchetes, como [PERSONA_1] o [FECHA_2], ya se tapó.

Tu tarea: encontrar los datos que TODAVÍA permitirían identificar a una persona, empresa, caso o trámite y que se quedaron sin tapar. Por ejemplo: fechas escritas en letra o en otro formato, folios, números de expediente o de constancia, números de escritura o de notaría, colonias o pedazos de domicilio, sellos o códigos de verificación, cédulas, teléfonos, correos, cuentas, nombres de personas o empresas.

NO marques: artículos de ley, nombres de leyes, instituciones públicas genéricas, cargos genéricos, horarios sueltos, números de página, ni lo que ya está entre corchetes.

Responde SOLO con JSON: {"hallazgos": [{"texto": "<copia EXACTA del fragmento tal como aparece>", "tipo": "<FECHA|FOLIO|NOTARIA|ESCRITURA|EXPEDIENTE|DOMICILIO|SELLO|TELEFONO|CORREO|CUENTA|PERSONA|EMPRESA|OTRO>", "motivo": "<breve>"}]}

TEXTO:
"""


TRATAMIENTOS = {"lic", "licenciado", "licenciada", "c", "sr", "sra", "srita", "dr", "dra", "ing", "mtro",
                "mtra", "notario", "notaria", "notario público", "persona", "el", "la", "de", "del", "y"}


class SinIALocal(Exception):
    """No hay Ollama corriendo o no tiene un modelo que sirva."""


class Cancelada(Exception):
    """El usuario detuvo la revisión."""


class FaltaInstalar(SinIALocal):
    """Falta Ollama o falta el modelo: la ventana ofrece instalarlo en vez de dar un error."""

    def __init__(self, mensaje: str, hay_ollama: bool):
        super().__init__(mensaje)
        self.hay_ollama = hay_ollama


@dataclass(frozen=True)
class Sugerencia:
    texto: str
    tipo: str  # tipo del detector (FECHA, FOLIO…) o MANUAL
    motivo: str = ""


def direccion() -> str:
    """Dónde está Ollama. Solo esta máquina o la red privada: el documento no sale de ahí."""
    url = os.environ.get("ANONIMIZADOR_OLLAMA", "http://localhost:11434").rstrip("/")
    host = urllib.parse.urlparse(url).hostname or ""
    if host != "localhost":
        try:
            ip = ipaddress.ip_address(host)
        except ValueError:
            raise SinIALocal(tr('La IA solo puede estar en esta computadora o en tu red privada ({host} no lo es).',
                                host=host)) from None
        if not (ip.is_loopback or ip.is_private):
            raise SinIALocal(tr('La IA solo puede estar en esta computadora o en tu red privada ({host} no lo es).',
                                host=host))
    return url


def _pedir(ruta: str, cuerpo: dict | None = None, espera: float = 2.0) -> dict:
    datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
    peticion = urllib.request.Request(direccion() + ruta, data=datos, headers={"Content-Type": "application/json"})
    # Sin proxies: un proxy del sistema mandaría el documento fuera de la máquina.
    abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with abridor.open(peticion, timeout=espera) as r:
        return json.load(r)


def modelos_instalados() -> list[str]:
    try:
        return [x["name"] for x in _pedir("/api/tags").get("models", [])]
    except SinIALocal:
        raise
    except Exception:
        return []


def elegir_modelo(instalados: list[str] | None = None) -> str:
    instalados = modelos_instalados() if instalados is None else instalados
    elegido = os.environ.get("ANONIMIZADOR_MODELO_IA")
    if elegido and elegido in instalados:
        return elegido
    for preferido in MODELOS_PREFERIDOS:
        if preferido in instalados:
            return preferido
    if not instalados:
        raise FaltaInstalar(tr('No encontré Ollama en esta computadora. Instálalo desde ollama.com y luego, en una '
                               'terminal: ollama pull {modelo}', modelo=MODELO_SUGERIDO), hay_ollama=False)
    raise FaltaInstalar(tr('Ollama está instalado, pero falta el modelo. En una terminal: ollama pull {modelo}',
                           modelo=MODELO_SUGERIDO), hay_ollama=True)


def trozos(texto: str, tam: int = TROZO) -> list[str]:
    """Corta por párrafos para no partir un dato a la mitad (salvo un párrafo enorme)."""
    partes, actual = [], ""
    for parrafo in re.split(r"(\n\s*\n)", texto):
        if len(actual) + len(parrafo) > tam and actual.strip():
            partes.append(actual)
            actual = ""
        while len(parrafo) > tam:
            partes.append(parrafo[:tam])
            parrafo = parrafo[tam:]
        actual += parrafo
    if actual.strip():
        partes.append(actual)
    return partes


def _normal(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def filtrar(respuesta: str, texto: str) -> list[Sugerencia]:
    """Lo que el modelo devolvió, solo si aparece tal cual en `texto` y no es algo ya tapado."""
    try:
        hallazgos = json.loads(respuesta).get("hallazgos", [])
    except (ValueError, AttributeError):
        return []
    plano = _normal(texto)
    vistas, sugerencias = set(), []
    for h in hallazgos if isinstance(hallazgos, list) else []:
        if not isinstance(h, dict):
            continue
        tipo = TIPOS.get(str(h.get("tipo", "")).upper(), MANUAL)
        # «[DOMICILIO_2]. Obrera del Sur»: lo ya tapado se quita y se queda lo que falta.
        for pedazo in re.split(r"\[[A-Z0-9_]+\]", str(h.get("texto", ""))):
            fragmento = re.sub(r"\s+", " ", pedazo).strip(" ,.;:·-")
            n = _normal(fragmento)
            if len(n) < 2 or "[" in n or "]" in n or n in vistas or n not in plano or not re.search(r"\w", n):
                continue
            if re.fullmatch(r"(p[aá]gina\s*)?\d{1,2}(\s*(de|/)\s*\d{1,2})?", n):  # números de página
                continue
            if n.rstrip(".") in TRATAMIENTOS or (len(n) < 4 and not re.search(r"\d", n)):
                continue  # «Lic.» que quedó al quitar «[PERSONA_5]»: taparlo taparía todos los «Lic.»
            vistas.add(n)
            sugerencias.append(Sugerencia(fragmento, tipo, str(h.get("motivo", ""))[:200]))
    return sugerencias


def sugerir(texto: str, modelo: str | None = None, espera: float = 600.0, avance=None,
            cancelado=None) -> list[Sugerencia]:
    """Pide a la IA local los datos que quedaron sin tapar en `texto` (ya tapado).

    `avance()` se llama antes de cada trozo: un documento largo son varios minutos y la
    ventana tiene que mostrar que va avanzando. Si `cancelado()` da verdadero (antes de
    cada trozo o al llegar su respuesta), se lanza `Cancelada`."""
    modelo = modelo or elegir_modelo()
    resultado, vistas = [], set()
    for trozo in trozos(texto):
        if cancelado and cancelado():
            raise Cancelada
        if avance:
            avance()
        cuerpo = {"model": modelo, "stream": False, "format": "json",
                  "options": {"temperature": 0, "num_ctx": 8192},
                  "messages": [{"role": "user", "content": INSTRUCCIONES + trozo}]}
        try:
            respuesta = _pedir("/api/chat", cuerpo, espera)["message"]["content"]
        except SinIALocal:
            raise
        except Exception as err:
            raise SinIALocal(tr('La IA local no respondió ({error}).', error=err)) from err
        if cancelado and cancelado():
            raise Cancelada
        for s in filtrar(respuesta, trozo):
            if _normal(s.texto) not in vistas:
                vistas.add(_normal(s.texto))
                resultado.append(s)
    return resultado
