"""Render the n=2 instance of the same cyclic construction used in the offline visitor console."""
from pathlib import Path
import sys
import reportlab
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "seed_pair"))
from ambiguity import triples

fonts = Path(reportlab.__file__).parent / "fonts"
for name, file in (("Demo", "Vera.ttf"), ("DemoBold", "VeraBd.ttf")):
    pdfmetrics.registerFont(TTFont(name, str(fonts / file)))
c = Canvas(str(HERE / "pair-worlds.pdf"), pagesize=(403, 148), invariant=1, initialFontName="Demo")
c.setTitle("Equal pair counts, different original triples")
colors = ["#1a6157", "#7a4225"]
for shift, color in enumerate(colors):
    x = 3 + 202 * shift
    c.setStrokeColor(HexColor(color))
    c.setFillColor(HexColor("#ffffff"))
    c.roundRect(x, 4, 194, 140, 4, fill=1, stroke=1)
    c.setFillColor(HexColor(color))
    c.setFont("DemoBold", 12)
    c.drawString(x + 9, 125, f"History {shift + 1}")
    c.setFont("Demo", 10)
    c.drawString(x + 9, 109, "Observed event members")
    for j, (a, b, d) in enumerate(triples(2, shift)):
        if a == 0 and b == 2:
            c.setFont("DemoBold", 12)
            c.setFillColor(HexColor(color))
        else:
            c.setFont("Demo", 11)
            c.setFillColor(HexColor("#263641"))
        c.drawString(x + 11, 87 - 18 * j, f"A{a}         B{b - 2}         C{d - 4}")
    c.setFont("Demo", 9)
    c.drawString(x + 9, 12, "Each cross-group pair occurs once.")
c.showPage()
c.save()
