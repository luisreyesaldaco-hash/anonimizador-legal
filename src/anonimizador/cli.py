"""Línea de comandos, para probar con documentos reales antes de la interfaz.

    anonimizador escanear demanda.docx
    anonimizador generar demanda.docx [--incluir EMPRESA_1] [--excluir FECHA_2] [--manual "Rancho El Ocote"]
    anonimizador generar contrato.docx renuncia.pdf [--salida carpeta]   (un proyecto, una sola tabla)
    anonimizador generar demanda.pdf --ia      (segunda revisión con la IA local: Ollama + gemma3)
    anonimizador revertir demanda_tabla.json respuesta.txt
    anonimizador revertir demanda_tabla.json respuesta.md -o respuesta.docx
    anonimizador agente preparar demanda.docx    (para Claude y otros agentes: nunca imprime datos reales)
    anonimizador agente devolver anonimizado/tabla_NO_ABRIR.json respuesta.md -o final.docx
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .detector import detectar
from .flujo import ErrorDeDocumento, Flujo, _guardar_documento, avisos_de_idioma, sugerir_con_ia
from .idioma import detectar_idioma
from .procesadores import (DocumentoNoSoportado, FormatoNoSoportado, abrir, extension_salida, marcar_si_hay_fugas,
                          ruta_tabla, rutas_salida)
from .reversion import nombre_sugerido, revertir_docx, texto_a_docx
from .seudonimos import Sesion, etiquetas_desconocidas, revertir


def _sesion(ruta: str, args) -> tuple[object, Sesion]:
    documento = abrir(ruta, usar_ocr=not args.sin_ocr)
    idioma = detectar_idioma(documento.texto) if args.idioma == "auto" else args.idioma
    print(f"Idioma: {idioma}", file=sys.stderr)
    sesion = Sesion(documento.texto, detectar(documento.texto, usar_ner=not args.sin_ner, idioma=idioma), idioma=idioma)
    for a in documento.avisos + avisos_de_idioma({idioma}, not args.sin_ner):
        print(f"Aviso: {a}", file=sys.stderr)
    if args.ia:
        _con_ia(sesion, [documento.texto])
    return documento, sesion


def _con_ia(sesion: Sesion, textos: list[str]) -> None:
    from .ia_local import SinIALocal, elegir_modelo

    try:
        modelo = elegir_modelo()
        print(f"Revisando con la IA local ({modelo})…", file=sys.stderr)
        nuevas = sugerir_con_ia(sesion, textos, modelo)
    except SinIALocal as err:
        print(f"Aviso: {err}", file=sys.stderr)
        return
    print(f"La IA local sugirió {len(nuevas)} datos más (marcados con *).", file=sys.stderr)


def _imprime_entidades(sesion: Sesion) -> None:
    for e in sorted(sesion.entidades, key=lambda e: e.etiqueta):
        marca = "x" if e.marcada else " "
        variantes = " | ".join(e.variantes)
        print(f"[{marca}] {e.etiqueta:<16} {variantes}{'  *' if e.sugerida else ''}")


def cmd_escanear(args) -> int:
    _, sesion = _sesion(args.archivo, args)
    _imprime_entidades(sesion)
    return 0


def cmd_generar(args) -> int:
    if len(args.archivos) > 1:
        return _generar_proyecto(args)
    args.archivo = args.archivos[0]
    documento, sesion = _sesion(args.archivo, args)
    for etiqueta in args.incluir:
        sesion.marcar(etiqueta, True)
    for etiqueta in args.excluir:
        sesion.marcar(etiqueta, False)
    for valor in args.manual:
        sesion.agregar_manual(valor)
    salida, _ = rutas_salida(args.archivo, extension_salida(documento, "docx" if args.word else "original"))
    if args.salida:
        salida = Path(args.salida)
    tabla = ruta_tabla(salida)
    informe = _guardar_documento(documento, salida, sesion.entidades)
    final = marcar_si_hay_fugas(informe.salida, informe.limpio)
    contenido = Path(args.archivo).read_bytes()
    tabla.write_text(json.dumps(sesion.tabla(args.archivo, contenido), ensure_ascii=False, indent=2), encoding="utf-8")
    if args.texto:
        Path(args.texto).write_text(documento.texto_limpio(sesion.entidades), encoding="utf-8")
    _imprime_entidades(sesion)
    print(f"\n{informe.apariciones} sustituciones → {final}")
    print(f"Tabla de equivalencias (no la compartas) → {tabla}")
    for a in informe.verificacion.avisos:
        print(f"Aviso: {a}", file=sys.stderr)
    if not informe.limpio:
        print("\n¡ATENCIÓN! La verificación encontró datos originales en la salida:", file=sys.stderr)
        for f in informe.verificacion.fugas:
            print(f"  {f.ubicacion}: {f.etiqueta} … {f.fragmento}", file=sys.stderr)
        return 2
    print("Verificación: no quedó ningún dato marcado en el archivo.")
    return 0


def _generar_proyecto(args) -> int:
    """Varios archivos: una sola revisión y una sola tabla; --salida es la carpeta de destino."""
    flujo = Flujo(usar_ner=not args.sin_ner, usar_ocr=not args.sin_ocr,
                  idioma=None if args.idioma == "auto" else args.idioma)
    flujo.cargar(args.archivos)
    for a in flujo.avisos:
        print(f"Aviso: {a}", file=sys.stderr)
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
    r = flujo.guardar_todos(args.salida, formato="docx" if args.word else "original")
    if args.texto:
        Path(args.texto).write_text(r.texto_limpio, encoding="utf-8")
    _imprime_entidades(sesion)
    print()
    for d in r.documentos:
        print(f"{d.nombre}: {d.sustituciones} sustituciones → {d.salida}")
    print(f"Tabla de equivalencias del proyecto (no la compartas) → {r.tabla}")
    for a in r.avisos:
        print(f"Aviso: {a}", file=sys.stderr)
    if not r.limpio:
        print("\n¡ATENCIÓN! La verificación encontró datos originales en la salida:", file=sys.stderr)
        for f in r.fugas:
            print(f"  {f.ubicacion}: {f.etiqueta} … {f.fragmento}", file=sys.stderr)
        return 2
    print("Verificación: no quedó ningún dato marcado en ningún archivo.")
    return 0


def cmd_revertir(args) -> int:
    tabla = json.loads(Path(args.tabla).read_text(encoding="utf-8"))
    if args.respuesta and Path(args.respuesta).suffix.lower() == ".docx":
        salida = args.salida or str(nombre_sugerido(args.respuesta, args.tabla))
        r = revertir_docx(args.respuesta, salida, tabla)
        print(salida)
    else:
        texto = Path(args.respuesta).read_text(encoding="utf-8-sig") if args.respuesta else sys.stdin.read()
        if args.salida and Path(args.salida).suffix.lower() == ".docx":
            r = texto_a_docx(texto, args.salida, tabla)
            print(args.salida)
        else:
            resultado = revertir(texto, tabla)
            if args.salida:
                Path(args.salida).write_text(resultado, encoding="utf-8")
            else:
                sys.stdout.write(resultado)
            r = None
    desconocidas = r.desconocidas if r else etiquetas_desconocidas(texto, tabla)
    if desconocidas:
        print(f"\naviso: esta tabla no conoce {', '.join(desconocidas)}; quedaron sin revertir.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="anonimizador", description="Seudonimiza documentos en tu PC.")
    sub = p.add_subparsers(dest="comando", required=True)

    def comunes(sp, varios=False):
        if varios:
            sp.add_argument("archivos", nargs="+", metavar="archivo")
        else:
            sp.add_argument("archivo")
        sp.add_argument("--sin-ner", action="store_true", help="no usar spaCy para nombres")
        sp.add_argument("--sin-ocr", action="store_true", help="no hacer OCR de páginas escaneadas")
        sp.add_argument("--ia", action="store_true",
                        help="segunda revisión con una IA local (Ollama, gemma3): sugiere lo que se escapó")
        sp.add_argument("--idioma", choices=["auto", "es", "cs", "en"], default="auto",
                        help="idioma del documento (por omisión se detecta)")

    e = sub.add_parser("escanear", help="muestra lo que se detectó")
    comunes(e)
    e.set_defaults(f=cmd_escanear)

    g = sub.add_parser("generar", help="genera el documento seudonimizado y la tabla")
    comunes(g, varios=True)
    g.add_argument("--incluir", action="append", default=[], metavar="ETIQUETA")
    g.add_argument("--excluir", action="append", default=[], metavar="ETIQUETA")
    g.add_argument("--manual", action="append", default=[], metavar="TEXTO")
    g.add_argument("--salida", help="archivo de salida (con varios archivos: carpeta de destino)")
    g.add_argument("--texto", help="guarda también el texto limpio en este archivo")
    g.add_argument("--word", action="store_true", help="todo sale en Word (.docx), también los PDF y las imágenes")
    g.set_defaults(f=cmd_generar)

    r = sub.add_parser("revertir", help="devuelve los nombres reales a la respuesta de la IA")
    r.add_argument("tabla")
    r.add_argument("respuesta", nargs="?", help="archivo con la respuesta: .txt, .md o .docx (si no, entrada estándar)")
    r.add_argument("--salida", "-o", help="archivo de salida; con .docx sale en Word con formato (un .docx de entrada siempre sale en .docx)")
    r.set_defaults(f=cmd_revertir)

    from .agente import agregar_comandos
    agregar_comandos(sub)

    args = p.parse_args(argv)
    try:
        return args.f(args)
    except (FileNotFoundError, FormatoNoSoportado, ValueError, KeyError, ErrorDeDocumento, *DocumentoNoSoportado) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
