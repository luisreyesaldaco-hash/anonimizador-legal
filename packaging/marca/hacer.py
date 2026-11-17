# Regenera el lockup desde los maestros de ~/legal-atlas-brand (Chromium respeta la fuente incrustada).
# Uso: python packaging/marca/hacer.py packaging/marca   (requiere playwright)
"""Lockup LEGAL ATLAS | ANONIMIZADOR con los mismos atributos del imagotipo maestro."""
import re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright

maestro = Path.home() / "legal-atlas-brand/logos/imagotipo"
dest = Path(sys.argv[1])
for variante, archivo in (("claro", "imago-horizontal-ink.svg"), ("oscuro", "imago-horizontal-paper.svg")):
    svg = (maestro / archivo).read_text()
    rect = re.search(r'<rect [^>]*/>', svg).group(0)
    texto = re.search(r'<text [^>]*>LEGAL ATLAS</text>', svg).group(0)
    nuevo_rect = rect.replace('x="216.47058823529412"', 'id="sep2" x="0"')
    nuevo_texto = texto.replace(">LEGAL ATLAS<", ">ANONIMIZADOR<").replace("<text ", '<text id="t2" ', 1)
    svg = svg.replace(texto, texto.replace("<text ", '<text id="t1" ', 1) + nuevo_rect + nuevo_texto)
    html = f"<html><body style='margin:0;background:transparent'>{svg}</body></html>"
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(device_scale_factor=3)
        pg.set_content(html); pg.wait_for_timeout(300)
        # separación: la misma que hay entre la primera línea y LEGAL ATLAS
        pg.evaluate("""() => {
            const s = document.querySelector('svg');
            const t1 = document.getElementById('t1'), t2 = document.getElementById('t2'), r = document.getElementById('sep2');
            const r1 = document.querySelector('rect:not(#sep2)');
            const hueco = parseFloat(t1.getAttribute('x')) - parseFloat(r1.getAttribute('x'));
            const finT1 = t1.getBBox().x + t1.getBBox().width;
            const xr = finT1 + (parseFloat(r1.getAttribute('x')) - 176.47);
            r.setAttribute('x', xr);
            t2.setAttribute('x', xr + hueco);
            const fin = t2.getBBox().x + t2.getBBox().width + 19.6;
            const vb = s.getAttribute('viewBox').split(' ').map(Number);
            s.setAttribute('viewBox', [vb[0], vb[1], fin - vb[0], vb[3]].join(' '));
            s.setAttribute('width', fin - vb[0]);
        }""")
        pg.locator("body > svg").screenshot(path=str(dest / f"logo-{variante}.png"), omit_background=True)
        (dest / f"logo-{variante}.svg").write_text(pg.locator("body > svg").evaluate("e => e.outerHTML"))
        b.close()
    print(variante, "ok")
