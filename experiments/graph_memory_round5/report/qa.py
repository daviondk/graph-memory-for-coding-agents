"""Check page boundaries, hyperlinks, content and raster rendering of the final research report."""
import hashlib
import json
import re
import zipfile
from pathlib import Path
from page_order import ordered_pages
from xml.etree import ElementTree as ET
from PIL import Image, ImageDraw
import pdfplumber
from pypdf import PdfReader

HERE=Path(__file__).resolve().parent
FINAL=HERE/'final'
NAME='graph-memory-research-round5'
pages=ordered_pages(HERE/'pages')
titles=[p.read_text(encoding='utf8').splitlines()[0][2:] for p in pages]
flat=lambda v:re.sub(r'[\s\u00ad\u200b\-‑−–—]+','',v).lower()
results=[]
with pdfplumber.open(FINAL/(NAME+'.pdf')) as pdf:
    print('pages',len(pdf.pages),'intended',len(pages))
    for i,page in enumerate(pdf.pages):
        words=page.extract_words()
        body=[w for w in words if 42 < w['top'] < page.height-41]
        text=' '.join(w['text'] for w in body)
        assert all(0<=w['x0']<w['x1']<=page.width+.5 and 0<=w['top']<w['bottom']<=page.height+.5 for w in words)
        result=dict(page=i+1,words=len(body),bottom=round(max((w['bottom'] for w in body),default=0.0),1),
                    heading=[s for s in titles if flat(s) in flat(text)],links=len(page.hyperlinks))
        print(result)
        results.append(result)
    assert [r['heading'][0] if len(r['heading'])==1 else '' for r in results]==titles, 'page splits or missing heading'
    assert all(68<r['words'] and r['bottom'] < 799 for r in results)
with zipfile.ZipFile(FINAL/(NAME+'.docx')) as z:
    doc=ET.fromstring(z.read('word/document.xml'))
    rel=ET.fromstring(z.read('word/_rels/document.xml.rels'))
    refids={el.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id') for el in doc.iter() if el.tag.endswith('}hyperlink')}
    links=[r.attrib['Target'] for r in rel if r.attrib['Id'] in refids]
    assert len(links) >= 8
    expected={t for p in pages for t in re.findall(r'\[[^\]]+\]\((https?://[^)]+)\)',p.read_text('utf8'))}
    assert set(links)==expected
    assert sum(el.tag.endswith('}tbl') for el in doc.iter()) >= 4
assert len(results)==len(list(FINAL.glob('page-*.png')))
for i in range(0,len(results),3):
    group=results[i:i+3]
    sheet=Image.new('RGB',(480*len(group),730),'#dfe6e9')
    draw=ImageDraw.Draw(sheet)
    for j,row in enumerate(group):
        path=FINAL/('page-%d.png'%row['page'])
        row['png_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
        with Image.open(path) as img:
            assert img.width>=900 and img.height>=1200
            img.thumbnail((464,680))
            sheet.paste(img,(j*480+8,8))
        draw.text((j*480+8,699), 'Page %d'%row['page'], fill='#153443')
    sheet.save(FINAL/('overview-%d.png'%(1+i//3)))
(FINAL/'qa.json').write_text(json.dumps(dict(pages=results, links=sorted(links)),ensure_ascii=False,indent=2),encoding='utf8')

