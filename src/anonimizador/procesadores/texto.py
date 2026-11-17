"""Texto plano (.txt) y Markdown (.md): lo que se copia de un correo, un chat o un sistema."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..seudonimos import Entidad, aplicar, localizar
from ..verificacion import ResultadoVerificacion, buscar_en_cadenas
from ..textos import tr


class DocumentoNoSoportado(Exception):
    pass


@dataclass
class Informe:
    salida: Path
    apariciones: int
    verificacion: ResultadoVerificacion
    avisos: list[str] = field(default_factory=list)

    @property
    def limpio(self) -> bool:
        return self.verificacion.limpio


def _leer(ruta: Path) -> str:
    datos = ruta.read_bytes()
    for codificacion in ("utf-8-sig", "utf-16") if datos[:2] in (b"\xff\xfe", b"\xfe\xff") else ("utf-8-sig",):
        try:
            return datos.decode(codificacion)
        except UnicodeDecodeError:
            pass
    return datos.decode("cp1252", errors="replace")  # Windows en español: el caso más común


class DocumentoTexto:
    def __init__(self, ruta: str | Path):
        self.ruta = Path(ruta)
        try:
            self.texto = _leer(self.ruta).replace("\r\n", "\n").replace("\r", "\n")
        except OSError as e:
            raise DocumentoNoSoportado(tr('No pude leer {ruta}: {e}', ruta=self.ruta.name, e=e)) from e
        self.avisos: list[str] = []

    def texto_limpio(self, entidades: list[Entidad]) -> str:
        marcadas = [e for e in entidades if e.marcada]
        return aplicar(self.texto, localizar(self.texto, entidades), marcadas)

    def guardar(self, salida: str | Path, entidades: list[Entidad]) -> Informe:
        salida = Path(salida)
        if salida.resolve() == self.ruta.resolve():
            raise ValueError(tr('La salida no puede ser el archivo original; elige otro nombre.'))
        if salida.suffix.lower() == ".docx":
            return self.guardar_word(salida, entidades)
        apariciones = localizar(self.texto, entidades)
        limpio = aplicar(self.texto, apariciones, [e for e in entidades if e.marcada])
        salida.write_text(limpio, encoding="utf-8")
        verificacion = ResultadoVerificacion(buscar_en_cadenas(salida.name, [limpio], entidades), [])
        return Informe(salida, len(apariciones), verificacion, list(self.avisos))

    def guardar_word(self, salida: str | Path, entidades: list[Entidad]) -> Informe:
        from .a_word import guardar_como_word

        apariciones, verificacion = guardar_como_word(self.texto, entidades, salida)
        return Informe(Path(salida), len(apariciones), verificacion, self.avisos + verificacion.avisos)
