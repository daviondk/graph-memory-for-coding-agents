"""Structural and raster completeness audit. Visual review is additionally required."""
import json,sys,zipfile,hashlib
from pathlib import Path
from xml.etree import ElementTree as ET
from pypdf import PdfReader
import pdfplumber
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parent
TITLES=['Память агента','Как отделён эффект памяти','Прогноз и полезное действие','Когда стоит читать причину','Как сохранить точные строки','Когда верная запись мешает','История объяснила выигрыш','Проверка старого объекта в DOM','Передача coding задачи','Что выбрал настоящий читатель','Происхождение наблюдений','Что уже сделано в литературе','Что проверять для статьи','Как проверить каждый результат']
def main(folder):
    path=ROOT/folder;base=path/'agent-memory-session5-results'
    from docx import Document
    expected=[p.text for p in Document(base.with_suffix('.docx')).paragraphs if p.style.name in ('Title','Heading 1')]
    pdf=PdfReader(base.with_suffix('.pdf'));geom=pdfplumber.open(base.with_suffix('.pdf'))
    rows=[]
    for i,(pg,gp) in enumerate(zip(pdf.pages,geom.pages),1):
        words=gp.extract_words();body=[w for w in words if 48<w['top']<gp.height-50]
        full=' '.join(w['text'] for w in words)
        good=all(0<=w['x0']<=w['x1']<=gp.width and 0<=w['top']<=w['bottom']<=gp.height for w in words)
        rows.append({'page':i,'words':len(body),'body_bottom_pt':max((w['bottom'] for w in body),default=0),'bounds_ok':good,'titles':[t for t in expected if t in full],'links':len(pg.get('/Annots',[])),'extract_sha':hashlib.sha256(full.encode()).hexdigest()})
    with zipfile.ZipFile(base.with_suffix('.docx')) as z:
        rel=ET.fromstring(z.read('word/_rels/document.xml.rels'))
        links=sorted({r.attrib['Target'] for r in rel if r.attrib.get('TargetMode')=='External'})
        xml=z.read('word/document.xml').decode()
        assert 'будут внесены' not in xml and 'PLACEHOLDER' not in xml
    imgs=sorted(path.glob('page-*.png'),key=lambda p:int(p.stem.split('-')[-1]))
    assert len(imgs)==len(rows)
    for f in imgs:
        image=Image.open(f);assert image.width>900 and image.height>1200
    for start in range(0,len(imgs),4):
        group=imgs[start:start+4];sheet=Image.new('RGB',(400*len(group),600),'#E8ECEF');draw=ImageDraw.Draw(sheet)
        for j,f in enumerate(group):
            img=Image.open(f).convert('RGB');img.thumbnail((384,568));sheet.paste(img,(j*400+8,4));draw.text((j*400+8,580),f.stem,fill='black')
        sheet.save(path/('overview-'+str(start//4+1)+'.png'))
    out={'pages':rows,'expected_titles':expected,'docx_hyperlinks':links,'raster_count':len(imgs)}
    (path/'qa.json').write_text(json.dumps(out,ensure_ascii=False,indent=1),encoding='utf8')
    print(json.dumps({'pages':len(rows),'words':[r['words'] for r in rows],'body_bottom':[round(r['body_bottom_pt']) for r in rows],'bounds':all(r['bounds_ok'] for r in rows),'titles_matched':[len(r['titles']) for r in rows],'links':len(links)}))
if __name__=='__main__':main(sys.argv[1])


