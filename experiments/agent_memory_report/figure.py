"""Render a confidence-interval plot of paired per-world contrasts for the DOCX."""
from pathlib import Path
import json
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import fitz
root=Path(__file__).resolve().parent
data=json.loads((root.parent/'agent_memory_trials/retention/results/summary.json').read_text())
paper=root/'retention-plot.pdf';c=canvas.Canvas(str(paper),pagesize=(450,147))
pdfmetrics.registerFont(TTFont('MetricFace','C:/Windows/Fonts/arial.ttf'))
def x(v):return 94+(v+.028)*342/.108
c.setFont('MetricFace',9)
for i,n in enumerate([0,50,100]):
    d=next(v for v in data['contrasts_positive_favor_joint'] if v['tool']=='block' and v['policy']=='marginal' and v['metric']=='required_reads' and str(v['rho'])==str(n))
    y=113-i*30;c.setFillColorRGB(.13,.18,.22);c.drawString(8,y-3,'ρ = '+str(n/100).replace('.',','))
    c.setStrokeColorRGB(.07,.38,.34);c.setLineWidth(1.7);c.line(x(d['lower95']),y,x(d['upper95']),y)
    for xx in (d['lower95'],d['upper95']):c.line(x(xx),y-4,x(xx),y+4)
    c.setFillColorRGB(.07,.38,.34);c.circle(x(d['mean']),y,3.1,stroke=0,fill=1)
c.setDash([2,2]);c.setStrokeColorRGB(.37,.40,.44);c.setLineWidth(.7);c.line(x(0),32,x(0),130);c.setDash([])
for xx in [-.02,0,.02,.04,.06,.08]:
    c.line(x(xx),21,x(xx),25);c.setFillColorRGB(.18,.23,.27);c.drawCentredString(x(xx),7,f'{xx:.2f}'.replace('.',','))
c.line(x(-.02),24,x(.08),24);c.save()
p=fitz.open(str(paper));p[0].get_pixmap(matrix=fitz.Matrix(2.5,2.5),alpha=False).save(str(root/'retention-plot.png'))

