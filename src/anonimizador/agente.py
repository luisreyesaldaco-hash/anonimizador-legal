"""Modo para agentes de IA (Claude Code y similares): el agente trabaja SOLO con lo anonimizado.

    anonimizador agente preparar demanda.docx contrato.pdf [--salida carpeta]
    anonimizador agente devolver carpeta/tabla_NO_ABRIR.json respuesta.md -o final.docx

Reglas de este modo, para que nada real llegue a la conversación del agente:
- Nunca imprime un dato real: ni los valores detectados, ni fragmentos de fugas, ni el texto
  revertido. Lo que imprime es JSON con rutas, etiquetas y conteos.
- Las salidas llevan nombres neutros (documento_1_anonimizado.docx): el nombre del archivo
  original muchas veces es el del cliente.
- Cada original, la tabla y cada resultado revertido se anotan en un registro
  (~/.anonimizador/protegidos.json) que lee la guardia del plugin de Claude Code para
  bloquear al agente si intenta abrirlos.
- Si la verificación encuentra datos reales en la salida, no se entrega texto: una persona
  tiene que revisar en la app.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REGISTRO = Path(os.environ.get("ANONIMIZADOR_REGISTRO") or Path.home() / ".anonimizador" / "protegidos.json")
NOMBRE_TABLA = "tabla_NO_ABRIR.json"
NOMBRE_TEXTO = "texto_anonimizado.md"


# --- registro que lee la guardia -------------------------------------------------------


def _leer_registro() -> dict:
    try:
        datos = json.loads(REGISTRO.read_text(encoding="utf-8"))
        return {"protegidos": list(datos.get("protegidos", [])), "permitidos": list(datos.get("permitidos", []))}
    except (OSError, ValueError):
        return {"protegidos": [], "permitidos": []}


def registrar(protegidos=(), permitidos=()) -> None:
    datos = _leer_registro()
    for clave, rutas in (("protegidos", protegidos), ("permitidos", permitidos)):
        for r in rutas:
            r = str(Path(r).resolve())
            if r not in datos[clave]:
                datos[clave].append(r)
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    temporal = REGISTRO.with_suffix(".tmp")
    temporal.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    temporal.replace(REGISTRO)


# --- salida ------------------------------------------------------------------------------


def _responder(datos: dict, codigo: int = 0) -> int:
    print(json.dumps(datos, ensure_ascii=False, indent=2))
    return codigo


def _sin_datos(texto: str, entidades) -> str:
    """Un aviso de la app puede nombrar algo del documento (un objeto incrustado): se tapa."""
    for e in entidades:
        for v in sorted(e.variantes, key=len, reverse=True):
            if v and e.marcada:
                texto = re.sub(re.escape(v), f"[{e.etiqueta}]", texto, flags=re.IGNORECASE)
    return texto


def _libre(ruta: Path) -> Path:
    n = 1
    while True:
        candidata = ruta if n == 1 else ruta.with_name(f"{ruta.stem}_{n}{ruta.suffix}")
        if not candidata.exists():
            return candidata
        n += 1


# --- preparar ------------------------------------------------------------------------------


def cmd_preparar(args) -> int:
    from .flujo import Flujo
    from .cli import _con_ia

    originales = [Path(a).resolve() for a in args.archivos]
    faltan = [str(i) for i, o in enumerate(originales, 1) if not o.is_file()]
    if faltan:
        return _responder({"estado": "error", "error": f"no existe el archivo número {', '.join(faltan)} de la lista"}, 1)
    registrar(protegidos=originales)  # antes que nada: aunque falle lo demás, el original queda vedado

    carpeta = Path(args.salida).resolve() if args.salida else originales[0].parent / "anonimizado"
    if carpeta in {o.parent for o in originales} and not args.salida:
        carpeta = _libre(carpeta)
    carpeta.mkdir(parents=True, exist_ok=True)

    flujo = Flujo(usar_ner=not args.sin_ner, usar_ocr=not args.sin_ocr,
                  idioma=None if args.idioma == "auto" else args.idioma)
    flujo.cargar([str(o) for o in originales])
    sesion = flujo.sesion
    if args.ia:
        _con_ia(sesion, [d.texto for d in flujo.documentos])
    for etiqueta in args.incluir:
        sesion.marcar(etiqueta, True)
    for etiqueta in args.excluir:
        sesion.marcar(etiqueta, False)
    for valor in args.manual:
        sesion.agregar_manual(valor)
    flujo.revisado = True

    tabla = _libre(carpeta / NOMBRE_TABLA)
    registrar(protegidos=[tabla])
    r = flujo.guardar_todos(carpeta, tabla=tabla, formato="docx" if args.word else "original")

    # Nombres neutros: el nombre del original suele ser el del cliente.
    datos_tabla = json.loads(tabla.read_text(encoding="utf-8"))
    documentos, limpios, sucios, fugas = [], [], [], []
    for i, d in enumerate(r.documentos, 1):
        neutro = _libre(carpeta / f"documento_{i}_anonimizado{d.salida.suffix}")
        if not d.limpio:
            neutro = _libre(carpeta / f"documento_{i}_CON_DATOS_REVISAR{d.salida.suffix}")
        registrar(protegidos=[neutro] if not d.limpio else [], permitidos=[neutro] if d.limpio else [])
        d.salida.replace(neutro)
        datos_tabla["documentos"][i - 1]["salida"] = neutro.name
        (limpios if d.limpio else sucios).append(neutro)
        fugas += [{"documento": f"documento_{i}", "etiqueta": f.etiqueta} for f in d.fugas]
        documentos.append({"documento": f"documento_{i}", "archivo": str(neutro), "sustituciones": d.sustituciones,
                           "verificado_sin_datos": d.limpio})
    tabla.write_text(json.dumps(datos_tabla, ensure_ascii=False, indent=2), encoding="utf-8")

    etiquetas = sorted(e.etiqueta for e in sesion.entidades if e.marcada)
    avisos = sorted({_sin_datos(a, sesion.entidades) for d in r.documentos for a in d.avisos} |
                    {_sin_datos(a, sesion.entidades) for a in flujo.avisos})
    respuesta = {
        "estado": "listo" if not sucios else "revisar",
        "documentos": documentos,
        "tabla": str(tabla),
        "etiquetas": etiquetas,
        "avisos": avisos,
    }
    if sucios:
        respuesta["fugas"] = fugas
        respuesta["instrucciones"] = (
            "La verificación encontró datos reales en la salida. NO abras ningún archivo de esta carpeta. "
            "Pide a la persona que lo revise en la app del anonimizador (anonimizador-app) o que te diga qué "
            "agregar con --manual.")
        return _responder(respuesta, 2)

    texto = _libre(carpeta / NOMBRE_TEXTO)
    partes = [f"## documento_{i}\n\n{d.texto_limpio.strip()}" for i, d in enumerate(r.documentos, 1)]
    texto.write_text("\n\n".join(partes) + "\n" if len(partes) > 1 else r.documentos[0].texto_limpio, encoding="utf-8")
    registrar(permitidos=[texto])
    respuesta["texto"] = str(texto)
    respuesta["instrucciones"] = (
        f"Trabaja SOLO con {texto} (o con los documentos _anonimizado). Escribe tu respuesta con las "
        "etiquetas tal cual, entre corchetes, sin traducirlas, declinarlas ni renumerarlas. Para entregar, "
        f"guarda tu respuesta en un archivo .md o .docx y corre: anonimizador agente devolver {tabla} "
        "<respuesta> -o <final.docx>. Nunca abras la tabla, los originales ni el resultado final.")
    return _responder(respuesta)


# --- devolver ------------------------------------------------------------------------------


def cmd_devolver(args) -> int:
    from .reversion import revertir_docx, texto_a_docx
    from .seudonimos import etiquetas_desconocidas, revertir

    salida = Path(args.salida).resolve()
    respuesta = Path(args.respuesta).resolve()
    tabla_ruta = Path(args.tabla).resolve()
    if salida in {respuesta, tabla_ruta}:
        return _responder({"estado": "error", "error": "la salida debe ser un archivo nuevo"}, 1)
    registrar(protegidos=[salida])  # antes de escribirla: el agente no debe poder leerla
    tabla = json.loads(tabla_ruta.read_text(encoding="utf-8"))
    if respuesta.suffix.lower() == ".docx":
        r = revertir_docx(respuesta, salida, tabla)
        n, desconocidas = r.reemplazos, r.desconocidas
    else:
        texto = respuesta.read_text(encoding="utf-8-sig")
        if salida.suffix.lower() == ".docx":
            r = texto_a_docx(texto, salida, tabla)
            n, desconocidas = r.reemplazos, r.desconocidas
        else:
            from .seudonimos import reemplazos
            n = len(reemplazos(texto, tabla))
            salida.write_text(revertir(texto, tabla), encoding="utf-8")
            desconocidas = etiquetas_desconocidas(texto, tabla)
    # Segunda capa: un aviso nunca lleva un valor de la tabla a la conversación.
    valores = [v for e in tabla["entidades"] for v in [e["original"], *e.get("variantes", [])] if len(v.strip()) >= 3]
    desconocidas = [d for d in desconocidas if not any(v.lower() in d.lower() for v in valores)]
    datos = {"estado": "listo", "salida": str(salida), "reemplazos": n,
             "instrucciones": "Entrega la ruta a la persona. No abras ese archivo: tiene los datos reales."}
    if desconocidas:
        datos["estado"] = "revisar"
        datos["sin_revertir"] = desconocidas
        datos["instrucciones"] = ("Estas etiquetas no se pudieron revertir: corrígelas en TU respuesta (usa la "
                                  "etiqueta exacta de la lista de etiquetas) y vuelve a correr devolver.")
    return _responder(datos, 0 if not desconocidas else 2)


def agregar_comandos(sub) -> None:
    a = sub.add_parser("agente", help="modo para agentes de IA: nunca imprime datos reales")
    asub = a.add_subparsers(dest="accion", required=True)

    p = asub.add_parser("preparar", help="anonimiza y deja el texto para el agente; imprime JSON")
    p.add_argument("archivos", nargs="+", metavar="archivo")
    p.add_argument("--salida", help="carpeta de destino (por omisión: ./anonimizado junto al primero)")
    p.add_argument("--sin-ner", action="store_true")
    p.add_argument("--sin-ocr", action="store_true")
    p.add_argument("--ia", action="store_true", help="segunda revisión con la IA local (Ollama)")
    p.add_argument("--idioma", choices=["auto", "es", "cs", "en"], default="auto")
    p.add_argument("--incluir", action="append", default=[], metavar="ETIQUETA")
    p.add_argument("--excluir", action="append", default=[], metavar="ETIQUETA")
    p.add_argument("--manual", action="append", default=[], metavar="TEXTO")
    p.add_argument("--word", action="store_true", help="todo sale en Word")
    p.set_defaults(f=cmd_preparar)

    d = asub.add_parser("devolver", help="pone los datos reales en la respuesta del agente; imprime JSON")
    d.add_argument("tabla")
    d.add_argument("respuesta", help="archivo .md, .txt o .docx con la respuesta del agente")
    d.add_argument("--salida", "-o", required=True, help="archivo final (.docx recomendado)")
    d.set_defaults(f=cmd_devolver)


if __name__ == "__main__":  # pragma: no cover
    from .cli import main
    sys.exit(main(["agente", *sys.argv[1:]]))
