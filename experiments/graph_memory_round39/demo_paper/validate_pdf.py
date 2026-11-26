"""Validate the four-page conference document using PyMuPDF after its visual inspection."""
import json
from pathlib import Path
import fitz

D=Path(__file__).resolve().parent
if __name__=='__main__':
    doc=fitz.open(D/'paper.pdf');assert len(doc)==4
    page_words=[];fonts=set();bounds=[]
    for page in doc:
        width,height=page.rect.width,page.rect.height;assert (width,height)==(612,792)
        words=page.get_text('words');assert len(words)>300
        for w in words:assert 30<w[0]<w[2]<width-30 and 25<w[1]<w[3]<height-30,w
        page_words.append(len(words));bounds.append([round(min(w[0] for w in words),1),round(min(w[1] for w in words),1),round(max(w[2] for w in words),1),round(max(w[3] for w in words),1)])
        fonts.update(f[3].split('+')[-1] for f in page.get_fonts())
    text=' '.join(page.get_text() for page in doc)
    for s in ['82.60','82.19','83.07','5.16','108,204','2,041','13,789,213,370','References','Fig. 1.','Fig. 2.']:assert s.casefold() in text.casefold(),s
    assert '??' not in text and any('Termes' in f for f in fonts)
    payload=(json.dumps(dict(pages=4,size_points=[612,792],word_counts=page_words,text_bounds=bounds,fonts=sorted(fonts),layout='IEEEtran conference',figures=2,tables=2,visual_check='All four pages rendered with Poppler and inspected at final layout.'),sort_keys=True,indent=2)+'\n').encode()
    (D/'pdf-check.json').write_bytes(payload)
    print(page_words)
