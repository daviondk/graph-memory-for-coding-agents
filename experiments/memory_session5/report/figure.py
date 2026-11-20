"""A paired forest plot of the learned joint writer versus a fixed rebased tail."""
from pathlib import Path
import json,os,subprocess
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
ROOT=Path(__file__).resolve().parent
a=json.loads((ROOT.parent/'packets/results.json').read_bytes())['results']
b=json.loads((ROOT.parent/'packets/transfer/results.json').read_bytes())['results']
pdfmetrics.registerFont(TTFont('ArialPlot','C:/Windows/Fonts/arial.ttf'))
pdf=ROOT/'budget_effect.pdf'
out=Canvas(str(pdf),pagesize=(490,112))
def x(v):return 100+(v+2)*49
for k in range(-2,6):
    out.setStrokeColor(HexColor('#B9CAD2' if k==0 else '#E6EBEE'))
    out.setLineWidth(1 if k==0 else .5);out.line(x(k),20,x(k),90)
    out.setFont('ArialPlot',8);out.setFillColor(HexColor('#384B58'))
    out.drawCentredString(x(k),9,str(k).replace('-','−'))
for i,k in enumerate(('256','512','1024')):
    y=77-i*23
    out.setFont('ArialPlot',8.5);out.drawRightString(78,y-2,'1 024 токена' if k=='1024' else k+' токенов')
    for j,(r,col) in enumerate([(a[k]['paired_joint_minus']['rebased_tail']['repo'],'#244E70'),(b[k]['B_joint_contrasts']['rebased_tail'],'#C4552C')]):
        yy=y+2.6-j*5.2;lo,hi=(x(v*100) for v in r['ci95']);mid=x(r['difference']*100)
        out.setStrokeColor(HexColor(col));out.setFillColor(HexColor(col));out.setLineWidth(1.1)
        out.line(lo,yy,hi,yy);out.line(lo,yy-1.4,lo,yy+1.4);out.line(hi,yy-1.4,hi,yy+1.4);out.circle(mid,yy,2.2,fill=1,stroke=0)
    out.setFillColor(HexColor('#384B58'))
for left,title,col in [(105,'Первая выборка','#244E70'),(230,'Обратный перенос','#C4552C')]:
    out.setFillColor(HexColor(col));out.circle(left,101,2.4,stroke=0,fill=1)
    out.setFillColor(HexColor('#384B58'));out.setFont('ArialPlot',8.5);out.drawString(left+7,98,title)
out.save()
cmd=Path('C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin/pdftoppm.exe')
subprocess.run([str(cmd),'-r','200','-png','-singlefile',str(pdf),str(ROOT/'budget_effect')],check=True)
