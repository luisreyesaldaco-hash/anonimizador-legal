"""Idioma del documento, por letras y palabras frecuentes. Sin red ni modelos."""

from __future__ import annotations

import re

IDIOMAS = {"es": "Español", "cs": "Čeština", "en": "English"}

_PALABRAS = {
    "es": {"el", "la", "de", "que", "y", "en", "los", "del", "se", "las", "por", "con", "para", "una"},
    "cs": {"a", "v", "se", "na", "je", "že", "s", "z", "do", "to", "o", "k", "jako", "pro", "ve", "ze", "dne", "není"},
    "en": {"the", "and", "of", "to", "in", "is", "that", "for", "with", "on", "as", "by", "this", "be"},
}
_LETRAS_CS = re.compile(r"[ěščřžůťďň]", re.IGNORECASE)


def detectar_idioma(texto: str) -> str:
    muestra = texto[:20000].lower()
    palabras = re.findall(r"[^\W\d_]+", muestra)
    if not palabras:
        return "es"
    puntos = {k: sum(w in v for w in palabras) / len(palabras) for k, v in _PALABRAS.items()}
    puntos["cs"] += 3 * len(_LETRAS_CS.findall(muestra)) / len(palabras)
    return max(puntos, key=puntos.get)
