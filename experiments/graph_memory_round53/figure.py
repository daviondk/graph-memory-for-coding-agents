"""Draw the R53 forest plot from archived paired estimates. Requires ReportLab and a Cyrillic font."""
from pathlib import Path
import json
import os
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

ROOT = Path(__file__).resolve().parent
W, H = 576, 344
LEFT, LABEL, PLOT_LEFT, PLOT_RIGHT, RIGHT = 16, 131, 273, 458, 559
NAVY = HexColor("#152e3d")
TEAL = HexColor("#12675f")
BROWN = HexColor("#994b23")
MUTED = HexColor("#465863")
GRID = HexColor("#d9e1e2")
ZERO = HexColor("#72848d")

def register_fonts():
    roots = [
        (Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts", "arial.ttf", "arialbd.ttf"),
        (Path("/usr/share/fonts/truetype/dejavu"), "DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
        (Path("/System/Library/Fonts/Supplemental"), "Arial.ttf", "Arial Bold.ttf"),
    ]
    for folder, regular, bold in roots:
        if (folder / regular).is_file() and (folder / bold).is_file():
            pdfmetrics.registerFont(TTFont("Body", str(folder / regular)))
            pdfmetrics.registerFont(TTFont("Bold", str(folder / bold)))
            return
    raise RuntimeError("Install Arial or DejaVu Sans (regular and bold) for Cyrillic text.")

def read(path):
    return json.loads((ROOT / path / "results.json").read_bytes())

def interval(entry):
    lo, hi = entry.get("ci95_pp", entry.get("ci95"))
    value = entry["delta_pp"]
    assert -1 <= lo <= value <= hi <= 10
    return value, lo, hi

def label(canvas, x, y, text, size=9, style="Body", color=NAVY, align="left"):
    canvas.setFont(style, size)
    canvas.setFillColor(color)
    draw = {"left": canvas.drawString, "right": canvas.drawRightString, "center": canvas.drawCentredString}
    draw[align](x, y, text)

def line(c, x1, y1, x2, y2, color, width):
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.line(x1, y1, x2, y2)

def x(value):
    return PLOT_LEFT + (value + 1) * (PLOT_RIGHT - PLOT_LEFT) / 11

def panel_grid(c, low, high):
    for tick in range(0, 11, 2):
        line(c, x(tick), low, x(tick), high, ZERO if tick == 0 else GRID, .85 if tick == 0 else .45)

def signed(v):
    return f"{v:+.2f}".replace("-", "−")

def observation(c, y, cohort, comparison, entry, interaction=False):
    value, lo, hi = interval(entry)
    color = BROWN if interaction else TEAL
    label(c, LEFT, y - 3.2, cohort)
    label(c, LABEL, y - 3.2, comparison, size=9.2, style="Bold" if interaction else "Body")
    line(c, x(lo), y, x(hi), y, color, 1.7)
    for cap in (lo, hi):
        line(c, x(cap), y - 2.5, x(cap), y + 2.5, color, 1.1)
    c.setFillColor(color)
    if interaction:
        p=c.beginPath()
        p.moveTo(x(value),y+3.7);p.lineTo(x(value)+3.7,y);p.lineTo(x(value),y-3.7);p.lineTo(x(value)-3.7,y);p.close()
        c.drawPath(p, fill=1, stroke=0)
    else:
        c.circle(x(value), y, 2.7, fill=1, stroke=0)
    label(c, RIGHT, y - 3.2, f"{signed(value)}  [{signed(lo)}, {signed(hi)}]", 9, align="right")

def number(n):
    return f"{n:,}".replace(",", " ")

def main():
    register_fonts()
    coverage = read("edge_control")
    reader = read("reader_body")
    c = Canvas(str(ROOT / "evidence-effects.pdf"), pagesize=(W, H), invariant=1, pageCompression=1)
    c.setTitle("Verified hyperlinks versus literal title lookup")
    c.setSubject("Paired corpus coverage, answer F1 and body-substitution interaction")
    label(c, LEFT, 320, "Проверенные ссылки и поиск по названию", 16, "Bold")
    label(c, LEFT, 303, "Effect of following a verified hyperlink instead of a text-only match", 12, color=MUTED)
    line(c, LEFT, 292, RIGHT, 292, GRID, .8)
    label(c, LEFT, 273, "Полное покрытие источников / Full support coverage", 11, "Bold")
    label(c, RIGHT, 273, "Δ, п.п. / pp  [95% CI]", 9, "Bold", align="right")
    panel_grid(c, 176, 256)
    for key, cohort, y in [("2wiki","2Wiki",248),("hotpot","HotpotQA",202)]:
        row=coverage[key]
        n=number(row["n"])
        observation(c, y, f"{cohort} (n = {n})", "Literal titles", row["contrasts"]["real_salience-text_salience"]["full"])
        observation(c, y-18, "", "Learned text proxy", row["contrasts"]["real_salience-text_proxy"]["full"])
    line(c, LEFT, 167, RIGHT, 167, GRID, .7)
    label(c, LEFT, 150, "Качество ответа / Answer F1", 11, "Bold")
    panel_grid(c, 85, 136)
    g=reader["contrasts"]
    observation(c, 129, f"2Wiki (n = {number(reader['n'])})", "Original body", g["real_gap"]["f1"])
    observation(c, 111, "", "Donor body", g["donor_gap"]["f1"])
    observation(c, 93, "", "Difference in differences", g["interaction"]["f1"], True)
    for tick in range(0, 11, 2):
        label(c, x(tick), 74, str(tick), 8.5, color=MUTED, align="center")
    label(c, (PLOT_LEFT+PLOT_RIGHT)/2, 60, "Разность, п.п. / Difference, pp", 8.5, color=MUTED, align="center")
    line(c, LEFT, 50, RIGHT, 50, GRID, .65)
    label(c, LEFT, 37, "Candidate counts are matched for coverage and input lengths for Answer F1 (Qwen3-4B-Instruct-2507).", 8.6, color=MUTED)
    label(c, LEFT, 24, "Interaction = original-body gap minus donor-body gap. Bars show paired 95% bootstrap CIs clustered by first document.", 8.6, color=MUTED)
    label(c, LEFT, 11, "Положительная разность соответствует преимуществу ссылки. Ромб показывает изменение этой разности.", 8.3, color=MUTED)
    c.showPage()
    c.save()

if __name__ == "__main__":
    main()
