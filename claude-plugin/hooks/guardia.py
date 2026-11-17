#!/usr/bin/env python3
"""Guardia del anonimizador para Claude Code (hook PreToolUse).

Bloquea que el agente abra lo que tiene datos reales (Read, Grep, Glob, Bash, Write/Edit,
NotebookRead/NotebookEdit y WebFetch con file://):
- los originales, la tabla y los resultados revertidos que registró `anonimizador agente`
  (~/.anonimizador/protegidos.json);
- cualquier tabla (*_tabla.json, tabla_NO_ABRIR.json), salida _CON_DATOS_REVISAR o _revertido;
- cualquier Word/PDF/RTF/ODT que no sea un _anonimizado: así ni siquiera el primer vistazo
  al documento, antes de anonimizarlo, llega a la conversación.

Es un cinturón de seguridad, no una caja fuerte: atrapa los descuidos de un agente que sigue
las instrucciones; no está hecho para detener a alguien que quiera saltárselo a propósito.
Solo usa la biblioteca estándar, para que funcione aunque el paquete aún no esté instalado.
Sale con 2 (bloquea, y el mensaje le llega al agente) o con 0 (deja pasar).
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REGISTRO = Path(os.environ.get("ANONIMIZADOR_REGISTRO") or Path.home() / ".anonimizador" / "protegidos.json")
DOCUMENTOS = {".docx", ".docm", ".doc", ".dotx", ".odt", ".rtf", ".pdf", ".xps", ".pages"}
CODIGO = {".py", ".sh", ".bash", ".zsh", ".js", ".mjs", ".ts", ".rb", ".pl", ".ps1", ".bat", ".cmd", ".r", ".jl"}
_NOMBRE_VEDADO = re.compile(r"(_tabla(_\d+)?\.json|tabla_no_abrir[^/\\]*\.json|_con_datos_revisar|_revertido)",
                            re.IGNORECASE)
_PERMITIDO = re.compile(r"_anonimizado(_\d+)?\.[a-z]+$", re.IGNORECASE)
# Las únicas órdenes que tocan los originales y la tabla: el anonimizador mismo, sin encadenar nada.
_ORDEN_PROPIA = re.compile(r"^\s*(?:\S*[/\\])?(?:anonimizador(?:\.exe)?|python3?\s+-m\s+anonimizador)\s+agente\s+"
                           r"(?:preparar|devolver)\b")
# Abrir el resultado en Word/Vista Previa para la persona no pasa nada a la conversación.
_ABRIR = re.compile(r"^\s*(?:open|xdg-open|start(?:\s+\"\")?|explorer(?:\.exe)?|cmd(?:\.exe)?\s+/c\s+start)\s+"
                    r"(\"[^\"]+\"|'[^']+'|\S+)\s*$")


def _registro() -> tuple[set[str], set[str]]:
    try:
        datos = json.loads(REGISTRO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set(), set()
    return set(datos.get("protegidos", [])), set(datos.get("permitidos", []))


def _absoluta(ruta: str, cwd: str) -> str:
    p = Path(os.path.expanduser(ruta))
    if not p.is_absolute():
        p = Path(cwd or ".") / p
    try:
        return str(p.resolve())
    except OSError:
        return str(p)


def _motivo_ruta(ruta: str, cwd: str, protegidos: set[str], permitidos: set[str]) -> str | None:
    if not ruta:
        return None
    absoluta = _absoluta(ruta, cwd)
    if absoluta in permitidos:
        return None
    if absoluta in protegidos:
        return "es un archivo con datos reales (original, tabla o resultado revertido)"
    nombre = Path(absoluta).name
    if _NOMBRE_VEDADO.search(nombre):
        return "es una tabla de equivalencias o un archivo con datos reales"
    if Path(nombre).suffix.lower() in DOCUMENTOS and not _PERMITIDO.search(nombre):
        return "es un documento sin anonimizar"
    return None


def _motivo_texto(texto: str, cwd: str, protegidos: set[str], permitidos: set[str]) -> str | None:
    """Una orden o un script que menciona algo vedado."""
    if _NOMBRE_VEDADO.search(texto):
        return "menciona una tabla de equivalencias o un archivo con datos reales"
    for p in protegidos:
        nombre = Path(p).name
        if p in texto or (len(nombre) > 4 and nombre in texto):
            return "menciona un archivo con datos reales (original, tabla o resultado revertido)"
    for m in re.finditer(r"[^\s\"'`;|&<>()=,\[\]{}]+\.(?:" + "|".join(e[1:] for e in DOCUMENTOS) + r")\b", texto,
                         re.IGNORECASE):
        token = m.group(0)
        if _PERMITIDO.search(token) or _absoluta(token, cwd) in permitidos:
            continue
        return f"menciona un documento sin anonimizar ({Path(token).suffix})"
    return None


def _motivo_carpeta(ruta: str, cwd: str, protegidos: set[str]) -> str | None:
    """Buscar o listar dentro de una carpeta que tiene originales registrados o una tabla."""
    carpeta = Path(_absoluta(ruta, cwd))
    if not carpeta.is_dir():
        return None
    if any(p.startswith(str(carpeta) + os.sep) for p in protegidos):
        return "esa carpeta contiene archivos con datos reales; busca solo en el texto anonimizado"
    for i, f in enumerate(carpeta.rglob("*")):
        if i > 5000:
            break
        if _NOMBRE_VEDADO.search(f.name):
            return "esa carpeta contiene una tabla de equivalencias; busca solo en el texto anonimizado"
    return None


def revisar(evento: dict) -> str | None:
    """Motivo para bloquear, o None si puede pasar."""
    herramienta = evento.get("tool_name", "")
    entrada = evento.get("tool_input") or {}
    cwd = evento.get("cwd") or os.getcwd()
    protegidos, permitidos = _registro()

    if herramienta == "Read":
        return _motivo_ruta(entrada.get("file_path", ""), cwd, protegidos, permitidos)

    if herramienta == "NotebookRead":
        return _motivo_ruta(entrada.get("notebook_path", ""), cwd, protegidos, permitidos)

    if herramienta == "WebFetch":
        url = str(entrada.get("url", ""))
        if not url.lower().startswith("file:"):
            return None
        from urllib.parse import unquote, urlparse
        ruta = unquote(urlparse(url).path)
        if re.match(r"^/[A-Za-z]:/", ruta):  # file:///C:/... en Windows
            ruta = ruta[1:]
        return _motivo_ruta(ruta, cwd, protegidos, permitidos) or _motivo_carpeta(ruta, cwd, protegidos)

    if herramienta in ("Grep", "Glob"):
        # Grep muestra contenido; Glob, nombres de archivo (el del original suele ser el del cliente).
        ruta = entrada.get("path") or cwd
        motivo = _motivo_ruta(ruta, cwd, protegidos, permitidos)
        if motivo:
            return motivo
        if herramienta == "Glob" and _NOMBRE_VEDADO.search(str(entrada.get("pattern", ""))):
            return "busca una tabla de equivalencias o un archivo con datos reales"
        return _motivo_carpeta(ruta, cwd, protegidos)

    if herramienta == "Bash":
        orden = entrada.get("command", "")
        sin_redireccion = re.sub(r"\s*2>&1\s*$", "", orden)
        sin_redireccion = re.sub(r"^\s*cd\s+(?:\"[^\"]*\"|'[^']*'|[^\s;&|`$]+)\s*&&\s*", "", sin_redireccion)
        if _ORDEN_PROPIA.match(sin_redireccion) and not re.search(r"[;&|`$<>\n]", sin_redireccion):
            return None
        if _ABRIR.match(orden):
            return None
        if re.search(r"anonimizador(?:\.exe)?\s+(?:escanear|generar|revertir)\b", orden):
            return "los comandos escanear, generar y revertir imprimen datos reales; usa `anonimizador agente`"
        return _motivo_texto(orden, cwd, protegidos, permitidos)

    if herramienta in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        ruta = entrada.get("file_path") or entrada.get("notebook_path") or ""
        absoluta = _absoluta(ruta, cwd) if ruta else ""
        if absoluta in protegidos or _NOMBRE_VEDADO.search(Path(absoluta).name):
            return "es un archivo con datos reales; no se modifica"
        if Path(ruta).suffix.lower() in CODIGO or herramienta == "NotebookEdit":
            contenido = " ".join(str(entrada.get(k, "")) for k in ("content", "new_string", "new_source"))
            contenido += " ".join(str(e.get("new_string", "")) for e in entrada.get("edits", []) or [])
            return _motivo_texto(contenido, cwd, protegidos, permitidos)
    return None


def main() -> int:
    try:
        evento = json.load(sys.stdin)
    except ValueError:
        return 0
    motivo = revisar(evento)
    if not motivo:
        return 0
    print(f"Bloqueado por la guardia del anonimizador: {motivo}. Trabaja solo con el texto anonimizado "
          "(texto_anonimizado.md o los *_anonimizado.*) y usa `anonimizador agente preparar` / "
          "`anonimizador agente devolver` para todo lo demás. Si la persona necesita que veas un documento "
          "sin anonimizar, que lo anonimice primero.", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
