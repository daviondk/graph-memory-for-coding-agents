"""Draw the three-file retention example. Run with Python and ReportLab 4."""
from pathlib import Path

import reportlab
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

fonts = Path(reportlab.__file__).parent / "fonts"
pdfmetrics.registerFont(TTFont("Vera", str(fonts / "Vera.ttf")))
pdfmetrics.registerFont(TTFont("VeraBold", str(fonts / "VeraBd.ttf")))
c = Canvas(str(Path(__file__).with_name("retention.pdf")), pagesize=(382,155), invariant=1, initialFontName="Vera")
c.setTitle("Two commits, one owner slot per file")
ink = HexColor("#173243")

def text(x, y, label, size=11, bold=False):
    c.setFont("VeraBold" if bold else "Vera", size)
    c.setFillColor(ink)
    c.drawString(x, y, label)

def box(x, y, w, h, stroke, fill):
    c.setLineWidth(.95)
    c.setStrokeColor(HexColor(stroke))
    c.setFillColor(HexColor(fill))
    c.roundRect(x, y, w, h, 4, fill=1, stroke=1)

text(4, 139, "Two commits, one owner slot per file", 13, True)
for x, title, body in [(5,"Event 1","files A and B"),(110,"Event 2","files A and C")]:
    box(x,83,86,40,"#086259","#f0f7f5")
    text(x+6,106,title,11,True)
    text(x+6,91,body,9.5)
c.setStrokeColor(ink)
c.line(94,103,106,103)
c.line(106,103,101,107)
c.line(106,103,101,99)
text(210,106,"Owners after event 2",11,True)
text(210,90,"A and C hold 2. B holds 1.",10)
box(5,10,177,55,"#657e86","#f0f4f5")
text(12,46,"Read A's own slot",11,True)
text(12,26,"Event 2 gives C one vote.",9)
box(190,10,186,55,"#965d31","#faf3eb")
text(197,46,"Read all live events for A",10.3,True)
text(197,26,"Events 1, 2 give B and C one each.",9)
c.showPage()
c.save()
