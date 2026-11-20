from pathlib import Path
import fitz
from PIL import Image
q=Path(__file__).parent/'release';p=fitz.open(next(q.glob('*.pdf')))
print('Rendered pages:',len(p))
assert len(p)==16
for i,page in enumerate(p,1):
    s=page.get_text()
    assert len(s.split())>=109 and '\ufffd' not in s,(i,len(s.split()))
    assert all(b[0]>=0 and b[2]<602 for b in page.get_text('blocks'))
    if i in (3,7,8,10,15):
        print(i,'words',len(s.split()))
for ix,nums in enumerate([range(1,9),range(9,17)]):
    out=Image.new('RGB',(4*275,2*387),'#dce1e3')
    for j,n in enumerate(nums):
        try:
            im=Image.open(q/f'page-{n}.png').convert('RGB');im.thumbnail((262,373))
        except FileNotFoundError:
            pix=p[n-1].get_pixmap(matrix=fitz.Matrix(.435,.435),alpha=False);im=Image.frombytes('RGB',(pix.width,pix.height),pix.samples)
        out.paste(im,(j%4*275+5,j//4*387+5))
    out.save(q/f'montage{ix}.jpg',quality=91)

