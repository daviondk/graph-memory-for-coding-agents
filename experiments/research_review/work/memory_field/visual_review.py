from pathlib import Path
import fitz
from PIL import Image, ImageOps, ImageDraw
q=Path(__file__).parent/'qa_final'
pdf=fitz.open(next(q.glob('*.pdf')))
for tag, inds in [('cover',[1,5,10,14]),('candidates',[20,22,24,26]),('last',[27,28,30,37])]:
    out=Image.new('RGB',(1040,1480),'#e2e5e5')
    for n,i in enumerate(inds):
        pp=pdf[i-1].get_pixmap(matrix=fitz.Matrix(.80,.80),alpha=False)
        im=Image.frombytes('RGB',(pp.width,pp.height),pp.samples)
        out.paste(im,(15+(n%2)*520,15+(n//2)*740))
    out.save(q/('inspect-'+tag+'.jpg'),quality=85)

