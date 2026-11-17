# Regenera los íconos del Anonimizador desde el maestro 8b de ~/legal-atlas-brand.
# Uso: python packaging/marca/icono.py   (requiere playwright y Pillow)
"""Ícono del Anonimizador: el inverso del de LegalAtlas.

LegalAtlas (la app que vendrá de la web) usa el 8a: fondo papel, pliegue oscuro. El Anonimizador
usa el 8b (pliegue claro) sobre un carbón más claro que la tinta del 8b, para que se distingan en
el Dock sin dejar de ser de la misma familia. Colores del pliegue sin tocar (decisiones firmadas).
"""
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

FONDO = "#3a3833"  # carbón cálido: más claro que la tinta #22211e del 8b
RAIZ = Path(__file__).resolve().parents[2]
maestro = (Path.home() / "legal-atlas-brand/logos/legal-atlas-8b-rounded.svg").read_text()
assert maestro.count('fill="#22211e"') == 1, "el maestro 8b cambió: revisar antes de regenerar"
svg = maestro.replace('fill="#22211e"', f'fill="{FONDO}"')


def pintar(lado: int) -> Image.Image:
    html = f"<html><body style='margin:0;background:transparent'>{svg}</body></html>"
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": lado, "height": lado})
        pg.set_content(html.replace('width="1024" height="1024"', f'width="{lado}" height="{lado}"'))
        pg.wait_for_timeout(300)
        png = pg.locator("body > svg").screenshot(omit_background=True)
        b.close()
    return Image.open(io.BytesIO(png)).convert("RGBA")


baldosa = pintar(1024)
# macOS: la baldosa ocupa 742 px de 1024, centrada (la rejilla de Apple dice 824, pero en el Dock
# se veía más grande que las demás apps: Luis pidió 10 % menos, 13-nov-2026).
mac = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
mac.alpha_composite(baldosa.resize((742, 742), Image.LANCZOS), (141, 141))
mac.save(RAIZ / "packaging/icono-mac.png")
mac.save(RAIZ / "packaging/icono.icns", sizes=[(16, 16), (32, 32), (128, 128), (256, 256), (512, 512), (1024, 1024)])
# Windows y la ventana: la baldosa a sangre (sin aire).
tamanos = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
for destino in ("packaging/icono.ico", "src/anonimizador/ui/recursos/icono.ico"):
    baldosa.save(RAIZ / destino, sizes=tamanos)
baldosa.resize((256, 256), Image.LANCZOS).save(RAIZ / "src/anonimizador/ui/recursos/icono.png")
print("ok")
