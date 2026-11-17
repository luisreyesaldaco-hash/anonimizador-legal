"""Punto de entrada de la app de escritorio (lo usa PyInstaller).

`Anonimizador --autoprueba resultado.json` no abre la ventana: comprueba que el detector
de nombres, el OCR y los procesadores funcionen dentro del paquete y escribe el resultado.
Lo usa el CI como prueba de humo del ejecutable (en Windows no hay consola para imprimir).

`Anonimizador --autoprueba-ui documento resultado.json` abre la ventana, carga el documento
y comprueba que llegue a la revisión: lo que vería quien usa la app.
"""

import json
import sys


def autoprueba(destino: str) -> int:
    resultado: dict = {}
    try:
        from anonimizador import __version__
        from anonimizador.detector import cs, detectar, en, ner_disponible
        from anonimizador.procesadores import ocr

        texto = "Comparece el C. Juan Pérez García con RFC GODE561231GR8 y correo juan@ejemplo.com."
        tipos = sorted({h.tipo for h in detectar(texto)})
        resultado = {
            "version": __version__,
            "ner": ner_disponible(),
            "ner_en": en.modelo_disponible(),
            "ner_cs": cs.modelo_disponible(),
            "ocr": ocr.disponible(),
            "ocr_idiomas": ocr.idiomas() if ocr.disponible() else "",
            "tipos": tipos,
        }
        resultado["ocr_lee"] = _prueba_ocr(ocr) if resultado["ocr"] else ""
        resultado["ok"] = (resultado["ner"] and resultado["ner_en"] and resultado["ner_cs"] and {"NOMBRE", "RFC", "CORREO"} <= set(tipos)
                           and "Pérez" in resultado["ocr_lee"])
    except Exception as e:  # el error tiene que llegar al archivo, no perderse
        resultado = {"ok": False, "error": repr(e)}
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    return 0 if resultado.get("ok") else 1


def _prueba_ocr(ocr) -> str:
    """Escanea una página generada aquí mismo: prueba tesseract y el idioma español del paquete."""
    import pymupdf

    origen = pymupdf.open()
    origen.new_page().insert_text((72, 100), "Juan Pérez García", fontsize=24)
    doc = pymupdf.open()
    pagina = doc.new_page()
    pagina.insert_image(pagina.rect, pixmap=origen[0].get_pixmap(dpi=200))
    return pagina.get_text(textpage=ocr.textpage(pagina)).strip()


def autoprueba_ui(documento: str, destino: str, espera: float = 180.0) -> int:
    """Abre la ventana de verdad, carga `documento` como si se eligiera con el botón y
    comprueba que llegue a la revisión con hallazgos. Cualquier error de la ventana cuenta."""
    import time

    from anonimizador.ui import ventana as v

    resultado: dict = {"ok": False}
    w = v.Ventana()
    inicio = time.monotonic()
    cargado, error_carga, informe = w._cargado, w._error_carga, w.report_callback_exception

    def fin(**datos):
        resultado.update(datos)
        resultado["segundos"] = round(time.monotonic() - inicio, 1)
        w.after(500, w.destroy)  # medio segundo: que se pinte la revisión (ahí fallaría el dibujo)

    def al_cargar(valor):
        cargado(valor)
        w.update_idletasks()
        fin(ok=bool(w.flujo.sesion.entidades and w.revision.winfo_ismapped()),
            hallazgos=len(w.flujo.sesion.entidades), avisos=w.flujo.avisos, idioma=w.flujo.idioma,
            etiquetas=[e.etiqueta for e in w.flujo.sesion.entidades])

    def al_fallar(err):
        error_carga(err)
        fin(ok=False, error=repr(err))

    def al_romper(tipo, valor, rastro):
        import traceback
        resultado["ok"] = False
        resultado.setdefault("errores_ventana", []).append("".join(traceback.format_exception(tipo, valor, rastro)))
        w.after(500, w.destroy)

    w._cargado, w._error_carga = al_cargar, al_fallar
    w.report_callback_exception = al_romper
    w.after(300, lambda: w._cargar([documento]))
    w.after(int(espera * 1000), lambda: (fin(ok=False, error="tiempo agotado"), None))
    w.mainloop()
    if resultado.get("errores_ventana"):
        resultado["ok"] = False
    with open(destino, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)
    return 0 if resultado.get("ok") else 1


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--autoprueba":
        sys.exit(autoprueba(sys.argv[2]))
    if len(sys.argv) == 4 and sys.argv[1] == "--autoprueba-ui":
        sys.exit(autoprueba_ui(sys.argv[2], sys.argv[3]))
    from pathlib import Path

    from anonimizador.ui.ventana import main

    main([a for a in sys.argv[1:] if Path(a).is_file()])  # archivos pasados al abrir la app
