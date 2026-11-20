"""Draw the paired budget contrast directly from the StaleBench replay."""
import json
import subprocess
from pathlib import Path
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

here = Path(__file__).resolve().parent
results = json.loads((here.parent / "literature/results.json").read_text(encoding="utf-8"))["results"]
pdfmetrics.registerFont(TTFont("ArialPlot", "C:/Windows/Fonts/arial.ttf"))
canvas = Canvas(str(here / "reader-effect.pdf"), pagesize=(455, 101), invariant=1)


def x(v):
    return 110 + (v + 15) * 12.7


for tick in range(-15, 11, 5):
    canvas.setStrokeColor(HexColor("#AAB9C2" if tick == 0 else "#E0E7EA"))
    canvas.setLineWidth(.9 if tick == 0 else .5)
    canvas.line(x(tick), 18, x(tick), 80)
    canvas.setFont("ArialPlot", 8)
    canvas.setFillColor(HexColor("#3F5663"))
    canvas.drawCentredString(x(tick), 5, str(tick).replace("-", "−"))
for title, key, y, color in [("Qwen2.5-14B", "qwen2.5:14b", 64, "#904825"),
                            ("GLM-4.6", "glm-4.6", 35, "#26677D")]:
    row = results[key]
    point = row["overall"]["difference_vs_uniform_pp"]
    low, high = row["secondary_subject_bootstrap"]["percentile_interval_pp"]
    canvas.setFillColor(HexColor("#223743"))
    canvas.setFont("ArialPlot", 10)
    canvas.drawRightString(94, y-3, title)
    canvas.setStrokeColor(HexColor(color))
    canvas.setFillColor(HexColor(color))
    canvas.setLineWidth(1.6)
    canvas.line(x(low), y, x(high), y)
    for bound in [low, high]:
        canvas.line(x(bound), y-3, x(bound), y+3)
    canvas.circle(x(point), y, 3.4, fill=1, stroke=0)
canvas.setFillColor(HexColor("#3F5663"))
canvas.setFont("ArialPlot", 8.2)
canvas.drawString(110, 90, "Разность точности при том же бюджете, п.п.")
canvas.save()
poppler = Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe"
subprocess.run([str(poppler), "-png", "-singlefile", "-r", "215", str(here / "reader-effect.pdf"),
                str(here / "reader-effect")], check=True)
