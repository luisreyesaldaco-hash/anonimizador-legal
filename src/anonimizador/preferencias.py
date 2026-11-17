"""Preferencias de quien usa la app (p. ej. «todo sale en Word»), en la carpeta de su usuario.

Nunca guarda datos de documentos: solo opciones de la interfaz.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _carpeta() -> Path:
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "Anonimizador"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Anonimizador"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "anonimizador"


def _archivo() -> Path:
    return Path(os.environ["ANONIMIZADOR_PREFERENCIAS"]) if os.environ.get("ANONIMIZADOR_PREFERENCIAS") \
        else _carpeta() / "preferencias.json"


def leer(clave: str, defecto=None):
    try:
        return json.loads(_archivo().read_text(encoding="utf-8")).get(clave, defecto)
    except (OSError, ValueError, AttributeError):
        return defecto


def guardar(clave: str, valor) -> None:
    """Si no se puede escribir (carpeta de solo lectura), la opción dura solo esta sesión."""
    archivo = _archivo()
    try:
        datos = json.loads(archivo.read_text(encoding="utf-8")) if archivo.exists() else {}
        if not isinstance(datos, dict):
            datos = {}
    except (OSError, ValueError):
        datos = {}
    datos[clave] = valor
    try:
        archivo.parent.mkdir(parents=True, exist_ok=True)
        archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass
