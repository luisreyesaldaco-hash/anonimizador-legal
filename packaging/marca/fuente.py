# Regenera ui/recursos/CormorantGaramond-SemiBold.ttf (la letra del imagotipo, licencia OFL).
#
#   curl -L -o vf.ttf "https://github.com/google/fonts/raw/main/ofl/cormorantgaramond/CormorantGaramond%5Bwght%5D.ttf"
#   python packaging/marca/fuente.py vf.ttf completa.ttf            (requiere fonttools)
#   pyftsubset completa.ttf --unicodes="U+0020-007E,U+00A0-017F,U+2010-2027,U+2030-203A,U+20AC" \
#       --layout-features='*' --name-IDs='*' --name-legacy --name-languages='*' \
#       --output-file=src/anonimizador/ui/recursos/CormorantGaramond-SemiBold.ttf
"""Instancia estática wght=600 de Cormorant Garamond como familia de una sola cara.

Una sola cara «Regular» en su propia familia («Cormorant Garamond SemiBold») hace que Tk la
encuentre igual en Windows (GDI), Mac (CoreText) y Linux (fontconfig) sin depender de cómo
cada sistema empareja pesos intermedios.
"""
import sys

from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

src, dst = sys.argv[1], sys.argv[2]
f = TTFont(src)
s = instancer.instantiateVariableFont(f, {"wght": 600}, updateFontNames=False)
FAM = "Cormorant Garamond SemiBold"
name = s["name"]
for nid in (16, 17, 21, 22, 25):
    name.removeNames(nameID=nid)
for nid, val in ((1, FAM), (2, "Regular"), (4, FAM), (6, "CormorantGaramond-SemiBold"),
                 (3, "Cormorant Garamond SemiBold (instancia estatica wght=600)")):
    name.removeNames(nameID=nid)
    name.setName(val, nid, 3, 1, 0x409)
    name.setName(val, nid, 1, 0, 0)
s["OS/2"].usWeightClass = 400
s["OS/2"].fsSelection = (s["OS/2"].fsSelection & ~0b100001) | 0b1000000
s["head"].macStyle = 0
if "STAT" in s:
    del s["STAT"]
s.save(dst)
print("ok", dst)
