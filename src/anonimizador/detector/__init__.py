"""Detección de datos sensibles: patrones (regex + validadores) y nombres (reglas + spaCy)."""

from __future__ import annotations

from typing import Iterable

from . import nombres, patrones
from .modelo import DESMARCADOS_POR_DEFECTO, PRIORIDAD, TIPOS, Hallazgo
from .nombres import ner_disponible

__all__ = ["Hallazgo", "TIPOS", "DESMARCADOS_POR_DEFECTO", "detectar", "ner_disponible"]


def _sin_cortes(texto: str, h: Hallazgo) -> Hallazgo | None:
    """Un hallazgo que termina a media palabra ("…v Kol|íně") nunca se encontraría al
    sustituir (se busca con límites de palabra) y se quedaría sin tapar: se recorta hasta
    la última palabra completa."""
    fin = h.fin
    if 0 < fin < len(texto) and texto[fin - 1].isalnum() and texto[fin].isalnum():
        corte = max(texto.rfind(" ", h.inicio, fin), texto.rfind("\n", h.inicio, fin))
        if corte <= h.inicio:
            return None
        fin = len(texto[h.inicio:corte].rstrip(" ,.;")) + h.inicio
    if fin <= h.inicio:
        return None
    return h if fin == h.fin else Hallazgo(h.tipo, texto[h.inicio:fin], h.inicio, fin, h.verificado)


def detectar(
    texto: str, tipos: Iterable[str] | None = None, usar_ner: bool = True, idioma: str = "es"
) -> list[Hallazgo]:
    """Devuelve los hallazgos sin traslapes, ordenados por posición."""
    permitidos = set(tipos) if tipos is not None else set(TIPOS)
    if idioma == "cs":
        from . import cs

        candidatos = cs.candidatos(texto, usar_modelo=usar_ner)
    elif idioma == "en":
        from . import en

        candidatos = en.candidatos(texto, usar_modelo=usar_ner)
    else:
        candidatos = patrones.candidatos(texto)
        if permitidos & {"NOMBRE", "EMPRESA"}:
            candidatos += nombres.detectar_nombres(texto, usar_ner=usar_ner)
    candidatos = [r for h in candidatos if h.tipo in permitidos and (r := _sin_cortes(texto, h)) is not None]
    candidatos.sort(key=lambda h: (-PRIORIDAD[h.tipo], -(h.fin - h.inicio), h.inicio))
    elegidos: list[Hallazgo] = []
    for h in candidatos:
        if all(h.fin <= e.inicio or h.inicio >= e.fin for e in elegidos):
            elegidos.append(h)
    return sorted(elegidos, key=lambda h: h.inicio)
