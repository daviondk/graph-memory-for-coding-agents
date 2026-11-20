"""Draw an illustrative two-path dependency proof with Cyrillic labels."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import math

out=Path(__file__).resolve().parent
scale=2
im=Image.new('RGB',(2100,550),'white')
g=ImageDraw.Draw(im)
def ff(n,bold=False):
    name='calibrib.ttf' if bold else 'calibri.ttf'
    return ImageFont.truetype(str(Path('C:/Windows/Fonts')/name),n*scale)
def pos(pt):
    return tuple(round(x*scale) for x in pt)
def arrow(p,q,color):
    g.line([pos(p),pos(q)],fill=color,width=5*scale)
    ang=math.atan2(q[1]-p[1],q[0]-p[0])
    ends=[(q[0]-14*math.cos(ang+dv),q[1]-14*math.sin(ang+dv)) for dv in (0.5,-0.5)]
    g.polygon([pos(q)]+[pos(v) for v in ends],fill=color)
def node(x,y,text,fill='#e9f0f3',edge='#426778'):
    p=(x-76,y-22,x+76,y+22)
    g.rounded_rectangle(pos(p),radius=10*scale,fill=fill,outline=edge,width=2*scale)
    g.text(pos((x,y)),text,anchor='mm',font=ff(19,True),fill='#173747')
arrow((202,114),(410,65),'#bd7c53')
arrow((561,65),(767,114),'#bd7c53')
arrow((202,125),(410,176),'#337762')
arrow((561,176),(767,125),'#337762')
node(125,120,'модуль A');node(487,62,'модуль B','#f9e9e2','#b07753');node(487,179,'модуль C','#e1f1ec','#377b64');node(845,120,'модуль D')
g.text(pos((487,22)),'Файл B изменился. Этот путь требует проверки.',anchor='mm',font=ff(17),fill='#805034')
g.text(pos((487,223)),'Файл C и его ребро прежние. Второй путь подтверждает зависимость A → D.',anchor='mm',font=ff(17),fill='#2e624f')
im.save(out/'witness-paths.png',dpi=(300,300))

