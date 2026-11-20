from pathlib import Path
import json, csv, collections, math, hashlib, datetime, statistics, zipfile
from collections import defaultdict
from docx import Document
from docx.shared import Cm, Pt, RGBColor
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.opc.part import Part
from docx.opc.packuri import PackURI

HERE=Path(__file__).resolve().parent
T=HERE.parent/'agent_memory_trials'; OUT=HERE.parents[1]/'outputs'
def J(s):return json.loads((T/s).read_text(encoding='utf-8-sig'))
def C(s):return list(csv.DictReader((T/s).open(encoding='utf-8-sig',newline='')))
def n(x):return f'{int(x):,}'.replace(',',' ')
def dec(x,k=2):return f'{x:.{k}f}'.replace('.',',').replace('-', '−')
def perc(x):return dec(x*100,2)+'%'
def pp(x,k=1):return ('+' if x>0 else '')+dec(x*100,k)
def ci(d,k=4):return '['+dec(d['lower95'],k)+'; '+dec(d['upper95'],k)+']'
doc=Document()
sec=doc.sections[0];sec.page_height=Cm(29.7);sec.page_width=Cm(21);sec.left_margin=Cm(1.9);sec.right_margin=Cm(1.9);sec.top_margin=Cm(1.75);sec.bottom_margin=Cm(1.8);sec.header_distance=Cm(.65);sec.footer_distance=Cm(.65)
teal='1E506B';ink='142330';mute='4D5F69'
def sty(name,font,size,col,bold=0,before=0,after=4,spacing=1.10):
    s=doc.styles[name] if name in doc.styles else doc.styles.add_style(name,WD_STYLE_TYPE.PARAGRAPH)
    s.font.name=font;s.font.size=Pt(size);s.font.color.rgb=RGBColor.from_string(col);s.font.bold=bool(bold)
    p=s.paragraph_format;p.space_before=Pt(before);p.space_after=Pt(after);p.line_spacing=spacing
    return s
sty('Normal','Calibri',11.7,ink,after=5);sty('Title','Cambria',29,'000000',1,after=10,spacing=1.03)
sty('Heading 1','Cambria',24,'000000',1,after=6,spacing=1.02);sty('Heading 2','Calibri',13,'000000',1,before=7,after=2)
sty('Section line','Calibri',10,teal,1,after=6);sty('Lead','Cambria',14,ink,after=9,spacing=1.06)
sty('Table text','Calibri',10.2,ink,after=0,spacing=1.03);sty('Table small','Calibri',9.75,ink,after=0,spacing=1.01);sty('Caption','Calibri',10,mute,after=4);sty('Running','Calibri',9,mute,after=0);sty('Ref','Calibri',10,ink,after=4)
for key in ['Title','Subtitle']:
    if key in doc.styles:
        for b in doc.styles[key]._element.xpath('.//w:pBdr'):b.getparent().remove(b)
hdr=sec.header.paragraphs[0];hdr.style='Running';hdr.alignment=WD_ALIGN_PARAGRAPH.RIGHT;hdr.add_run('Рабочая память кодового агента')
ft=sec.footer.paragraphs[0];ft.style='Running';ft.paragraph_format.tab_stops.add_tab_stop(Cm(17.15),WD_TAB_ALIGNMENT.RIGHT);ft.add_run('Память языковых агентов\t')
num=OxmlElement('w:fldSimple');num.set(qn('w:instr'),'PAGE');ft._p.append(num)
doc.core_properties.title='Эксперименты с памятью языковых агентов';doc.core_properties.author='Исследовательский отчёт'
def p(t,style='Normal'):return doc.add_paragraph(t,style)
def h(t):return p(t,'Heading 2')
def page(section,title,lead=''):
    x=p(section,'Section line');x.paragraph_format.page_break_before=True;x.paragraph_format.keep_with_next=True
    p(title,'Heading 1')
    if lead:p(lead,'Lead')
def tbl(head,rows,widths=None,small=False):
    count=len(head); tb=doc.add_table(rows=0,cols=count);tb.autofit=False;tb.alignment=WD_TABLE_ALIGNMENT.CENTER
    borders=OxmlElement('w:tblBorders')
    for edge in ('top','left','bottom','right','insideH','insideV'):
        e=OxmlElement('w:'+edge);e.set(qn('w:val'),'single');e.set(qn('w:sz'),'4');e.set(qn('w:color'),'D9D9D9');borders.append(e)
    tb._tbl.tblPr.append(borders)
    widths=widths or [17.1/count]*count
    for i,w in enumerate(widths):tb.columns[i].width=Cm(w)
    for i,vals in enumerate([head,*rows]):
        cells=tb.add_row().cells
        trpr=tb.rows[-1]._tr.get_or_add_trPr();trpr.append(OxmlElement('w:cantSplit'))
        if i==0:trpr.append(OxmlElement('w:tblHeader'))
        for j,(c,x) in enumerate(zip(cells,vals)):
            c.width=Cm(widths[j]);c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            sh=OxmlElement('w:shd');sh.set(qn('w:fill'),'234C65' if i==0 else ('EFF4F7' if i%2 else 'FFFFFF'));c._tc.get_or_add_tcPr().append(sh)
            par=c.paragraphs[0];par.style='Table small' if small else 'Table text'
            par.paragraph_format.space_before=Pt(3 if small else 4);par.paragraph_format.space_after=Pt(3 if small else 4)
            r=par.add_run(str(x));r.bold=(i==0)
            if i==0:r.font.color.rgb=RGBColor.from_string('FFFFFF')
    return tb
def link(par,url,t):
    h=OxmlElement('w:hyperlink');h.set(qn('r:id'),par.part.relate_to(url,RT.HYPERLINK,is_external=True));rn=OxmlElement('w:r');rp=OxmlElement('w:rPr');col=OxmlElement('w:color');col.set(qn('w:val'),teal);rp.append(col);rn.append(rp);txt=OxmlElement('w:t');txt.text=t;rn.append(txt);h.append(rn);par._p.append(h)
def source(label,url):
    par=doc.add_paragraph(style='Ref');link(par,url,label)
def cv(d):return str(d) if d is not None else 'н/д'
def ar(s):return 'https://arxiv.org/abs/'+s

