from pathlib import Path
from PIL import Image, ImageDraw
import fitz,re,sys
q=Path(__file__).parent/'qa_release'
d=fitz.open(next(q.glob('*.pdf')))
assert len(d)==35, len(d)
for lo,hi in [(1,12),(13,24),(25,30),(31,35)]:
    out=Image.new('RGB',(4*265,((hi-lo+4)//4)*385),'#dce2e2')
    for n,i in enumerate(range(lo,hi+1)):
        with Image.open(q/f'page-{i}.png') as im:
            im.thumbnail((253,356)); x=n%4*265+5;y=n//4*385+5;out.paste(im,(x,y));ImageDraw.Draw(out).text((x+2,y+358),str(i),fill='#182b38')
    out.save(q/f'contact-{lo}.jpg',quality=84)
for i,p in enumerate(d,1):
    text=p.get_text()
    assert len(text.split())>100,(i,'sparse')
    if 20<=i<=27:assert str(i-19)+' из 8' in text,i
    if i>=31:assert 'Библиографический указатель' in text,i
    if 2<=i<=30 and i!=28: assert 'Источники' in text,i
    assert '\ufffd' not in text
    boxes=[b[3] for b in p.get_text('blocks') if 43<b[1]<780]
    if i>=31:print('bibliography',i,'to',round(max(boxes)))
print('verified',len(d),'pages')

