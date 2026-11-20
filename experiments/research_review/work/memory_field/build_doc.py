from pathlib import Path
from collections import OrderedDict
import json, math, re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from bibliography import canonical_url

HOME_DIR=Path(__file__).resolve().parent
OUT=HOME_DIR.parents[1]/'outputs'/'agent-memory-research-map.docx'
def load(n): return json.loads((HOME_DIR/(n+'.json')).read_text(encoding='utf-8-sig'))
ov,ex,arch,exp,fr,cd,ps,en,ctrl=[load(n) for n in ['overview','extra_field','architecture','experience','frontiers','candidates','personal','endmatter','controls']]
pages=[]
def add(section,*items):
    for item in items: pages.append((section,item))
add('I   Устройство памяти',ov[0],ov[1],ex[0],ov[2],en[0])
add('II   Семейства архитектур',arch[0],arch[1],arch[2],arch[3],exp[0],exp[1],exp[2],exp[3],ex[1])
add('III   Статьи и методы оценки',ov[3],ov[4],ctrl[0],ov[5])
hypotheses=[fr[0],fr[1],fr[2],fr[3],cd[0],cd[1],ps[0],cd[2]]
for i,p in enumerate(hypotheses,1): add('IV   Исследовательские направления     /     '+str(i)+' из 8',p)
add('V   Выбор и планирование',{'type':'matrix','title':'Как выбрать направление'},en[1],en[2])
meta=load('refs_meta')
def canon(url):
    k=canonical_url(url)
    if k.endswith('/abs/2409.07429'): return 'https://proceedings.mlr.press/v267/wang25bx.html'
    return k
refs=OrderedDict()
for _,page in pages:
    for ref in page.get('sources',[]):
        key=canon(ref['url'])
        if key not in refs: refs[key]=len(refs)+1
lookups={k:v for k,v in meta.items()}
for key in refs: assert key in lookups, key
NREF=len(refs)
extras={'https://icdm2026.neu.edu.cn/Tutorials/list.htm':'ICDM 2026 — программа tutorials','https://icdm2026.neu.edu.cn/Keynotes/list.htm':'ICDM 2026 — пленарные доклады','https://github.com/MemTensor/MemBook/blob/408a73615570ddad328bb945ef851c7c33624a52/README.md':'MemBook — оглавление и состав редакторов','https://github.com/MemTensor/MemOS/releases/tag/v1.0.0':'MemOS — официальный релиз v1.0.0'}
doc=Document()
sec=doc.sections[0]
sec.page_width=Cm(21); sec.page_height=Cm(29.7)
sec.left_margin=Cm(2.1); sec.right_margin=Cm(2.05); sec.top_margin=Cm(1.85); sec.bottom_margin=Cm(1.75)
sec.header_distance=Cm(0.65); sec.footer_distance=Cm(0.72)
sec.different_first_page_header_footer=True
dark='1C2933'; grey='51616A'; teal='14645D'; deep='162C39'; ink='101A22'
def style(name,font,size,color=dark,bold=False,before=0,after=0,space=1.12):
    ss=doc.styles[name] if name in doc.styles else doc.styles.add_style(name,WD_STYLE_TYPE.PARAGRAPH)
    ss.font.name=font; ss.font.size=Pt(size); ss.font.bold=bold; ss.font.color.rgb=RGBColor.from_string(color)
    pf=ss.paragraph_format; pf.space_before=Pt(before); pf.space_after=Pt(after); pf.line_spacing=space
    return ss
style('Normal','Calibri',11.5,dark,after=2,space=1.08)
for name,f,size,col,b,be,af,sp in [
('Title','Cambria',40,'000000',True,0,10,1.0),('Heading 1','Cambria',26,deep,True,0,10,1.02),
('Heading 2','Calibri',13,deep,True,6,2,1.01),('Eyebrow','Calibri',10,teal,True,0,7,1),
('Lead text','Cambria',13.5,deep,False,0,6,1.08),('Reference links','Calibri',9.6,teal,False,2,0,1.1),
('Refs heading','Calibri',10,grey,True,9,2,1),('Bib entry','Calibri',11.3,dark,False,0,8,1.09),
('Running text','Calibri',9,grey,False,0,0,1),('Navigation','Calibri',12,dark,False,0,7,1.13),
('Matrix text','Calibri',10.4,dark,False,0,0,1.08),('Cover intro','Cambria',17,deep,False,0,10,1.15)]:
    style(name,f,size,col,b,be,af,sp)
for sn in ['Title','Subtitle']:
    if sn in doc.styles:
        pr=doc.styles[sn]._element.find(qn('w:pPr'))
        if pr is not None:
            borders=pr.find(qn('w:pBdr'))
            if borders is not None: pr.remove(borders)
def para(txt,sty='Normal'): return doc.add_paragraph(txt,sty)
def pbreak(secname):
    p=para(secname,'Eyebrow')
    p.paragraph_format.page_break_before=True
    p.paragraph_format.keep_with_next=True
    return p
def link(p,url,text,color=teal, internal=False):
    h=OxmlElement('w:hyperlink')
    if internal:h.set(qn('w:anchor'),url)
    else:h.set(qn('r:id'),p.part.relate_to(url,RT.HYPERLINK,is_external=True))
    r=OxmlElement('w:r');rp=OxmlElement('w:rPr');co=OxmlElement('w:color');co.set(qn('w:val'),color);rp.append(co)
    r.append(rp);t=OxmlElement('w:t');t.text=text;r.append(t);h.append(r);p._p.append(h)
def bookmark(p, name, num):
    b=OxmlElement('w:bookmarkStart'); b.set(qn('w:id'),str(num)); b.set(qn('w:name'),name);p._p.insert(1,b)
    e=OxmlElement('w:bookmarkEnd');e.set(qn('w:id'),str(num));p._p.append(e)
def field(p,instruction):
    f=OxmlElement('w:fldSimple');f.set(qn('w:instr'),instruction);p._p.append(f)
def footer(s):
    p=s.footer.paragraphs[0];p.style='Running text'
    p.paragraph_format.tab_stops.add_tab_stop(Cm(16.85),WD_TAB_ALIGNMENT.RIGHT)
    p.add_run('Память языковых агентов');p.add_run('\t');field(p,'PAGE')
footer(sec)
p=sec.header.paragraphs[0];p.style='Running text';p.alignment=WD_ALIGN_PARAGRAPH.RIGHT;p.add_run('Обзор исследований   /   16 ноября 2026')
cp=doc.core_properties;cp.title='Как устроена память языковых агентов';cp.subject='Карта литературы и восемь направлений для выбора исследовательской темы';cp.author='Исследовательский обзор'
def heading(title): return para(title,'Heading 1')
def add_sources(page):
    para('Источники','Refs heading')
    p=doc.add_paragraph(style='Reference links')
    for i,ref in enumerate(page['sources']):
        if i:p.add_run('     ')
        key=canon(ref['url']); link(p,key,'['+str(refs[key])+']\u00a0'+ref['label'])
def ordinary(page):
    t=heading(page['title'])
    lead=para(page['lead'],'Lead text')
    dense=len(' '.join([page['lead']]+[b['text'] for b in page['blocks']]).split())>290
    for b in page['blocks']:
        para(b['head'],'Heading 2')
        p=para(b['text'])
        if dense:
            p.paragraph_format.line_spacing=1.045
            p.runs[0].font.size=Pt(11.0)
    add_sources(page)
    return t
def shade(cell,color):
    tcpr=cell._tc.get_or_add_tcPr();s=OxmlElement('w:shd');s.set(qn('w:fill'),color);tcpr.append(s)
def matrix():
    t=heading('Как выбрать направление')
    para('Выбор зависит от того, какой материал вы хотите сделать центральным результатом статьи — новый способ записи, исполняемый эксперимент или аудит уже принятой методики.','Lead text')
    data=[
('Тема','Что понадобится','Самое важное сравнение'),
('1. Цена повторного чтения','Симулятор, где одна команда возвращает несколько полей','Сохранить целый блок при тех же расходах'),
('2. Независимая проверка','Документы с известной цепочкой цитирования','Всегда открыть новый источник'),
('3. Перенос процедуры','Пары версий инструмента и скрытые тесты','Придумать пробу уже в новой среде'),
('4. Адресат поручения','Календарь дежурств или реестр веток Git','Сохранить буквальный текст и открыть реестр'),
('5. Границы поиска','Несколько репозиториев, журналы и локализация','Выдать необработанные метаданные той же команды'),
('6. Отзыв источника','Сводки, разрешённые документы, цепочки ссылок','Пересобрать сводку из оставшихся документов'),
('7. Личное исключение','Два профиля и симулятор календаря','Проверить карточку, потом спросить при необходимости'),
('8. Выборка бенчмарка','Хронологическая история задач и воспроизводимые тесты','Оценить методы на последовательной и обогащённой выборках')]
    table=doc.add_table(rows=0,cols=3); table.autofit=False; table.alignment=WD_TABLE_ALIGNMENT.CENTER
    for i,v in enumerate([4.05,6.10,6.7]):table.columns[i].width=Cm(v)
    for i,row in enumerate(data):
        cs=table.add_row().cells
        for j,(c,txt) in enumerate(zip(cs,row)):
            c.width=Cm([4.05,6.10,6.7][j]); c.vertical_alignment=WD_CELL_VERTICAL_ALIGNMENT.CENTER
            shade(c,'1D514F' if i==0 else ('EAF1EF' if i%2 else 'F8FAF9'))
            p=c.paragraphs[0];p.style='Matrix text';p.paragraph_format.space_before=Pt(4);p.paragraph_format.space_after=Pt(4);rr=p.add_run(txt)
            rr.bold=(i==0 or j==0)
            if i==0:rr.font.color.rgb=RGBColor.from_string('FFFFFF')
    para('Если важна работа на настоящем коде','Heading 2')
    para('Вариант 5 оставляет систему маленькой и даёт проверяемую инженерную задачу. Вариант 3 подходит для управляемого эксперимента с версиями API. Вариант 8 требует больше вычислений и даёт прежде всего вывод о достоверности измерений.')
    para('Если нужны быстрые и однозначные проверки','Heading 2')
    para('В вариантах 1 и 4 правильное действие легко вычислить программно. Варианты 2, 6 и 7 лучше подходят для исследования зависимости от источника, права на пересмотр и цены уточнения. Им потребуется отдельно проверить качество размеченных историй.')
    return t

p=para('Карта литературы   /   ноябрь 2026','Eyebrow');p.paragraph_format.space_before=Pt(16)
p=para('Как устроена память\nязыковых агентов','Title')
para('Архитектуры, способы оценки и восемь направлений для выбора темы исследования','Cover intro')
para('Контекст, который агент получил в прошлой задаче, может изменить его следующее действие. Чтобы понять пользу памяти, нужно выяснить, что было записано, какая часть дошла до исполнителя и улучшился ли результат при тех же затратах. Обзор прослеживает этот путь в диалогах, программировании, работе групп агентов и задачах роботов.')
intro=para('Навигация по документу','Heading 2');intro.paragraph_format.space_before=Pt(21)
def start_for(fragment):
    return 2+next(i for i,(group,_) in enumerate(pages) if group.startswith(fragment))
for lab,part in [('Устройство памяти и разбор фотографий','I '),('Семейства архитектур и примеры применения','II '),('Типы статей, бенчмарки и расхождения результатов','III '),('Восемь проверяемых направлений','IV '),('Сравнение тем и протокол первого опыта','V ')]:
    n=start_for(part);p=doc.add_paragraph(style='Navigation');p.add_run(str(n).zfill(2)+'     ').bold=True;link(p,'p'+str(n),lab,internal=True)
bstart=2+len(pages);p=doc.add_paragraph(style='Navigation');p.add_run(str(bstart).zfill(2)+'     ').bold=True;link(p,'p'+str(bstart),'Библиографический указатель',internal=True)
p=para('Материалы и публикации проверены по состоянию на 16 ноября 2026 года.','Running text');p.paragraph_format.space_before=Pt(14)
for i,(group,page) in enumerate(pages,2):
    p=pbreak(group)
    t=matrix() if page.get('type')=='matrix' else ordinary(page)
    bookmark(t,'p'+str(i),i)

refs_list=list(refs)
ref_sizes=[17,19,19,18,18]
assert sum(ref_sizes)==len(refs_list)
for group_idx,n_entries in enumerate(ref_sizes):
    a=sum(ref_sizes[:group_idx])
    part=refs_list[a:a+n_entries]
    pbreak('Источники     /     '+str(a+1)+'–'+str(a+len(part))+' из '+str(NREF))
    t=heading('Библиографический указатель')
    if a==0:
        bookmark(t,'p'+str(bstart),bstart)
        para('Номера соответствуют ссылкам в тексте. Для научных работ указаны первый автор и год использованной версии. Нажмите на название, чтобы открыть источник.','Lead text')
    for k in part:
        v=lookups[k];p=doc.add_paragraph(style='Bib entry')
        num=refs[k]
        p.paragraph_format.left_indent=Cm(0.91);p.paragraph_format.first_line_indent=Cm(-0.91)
        p.paragraph_format.tab_stops.add_tab_stop(Cm(0.91))
        p.add_run(f'{num:02d}\t').bold=True
        if v['first_author'] or v['year']:p.add_run(' · '.join(i for i in [v['first_author'],v['year']] if i)+'   ')
        title=extras.get(k,v['title']).replace('Agents?Benchmarking','Agents? Benchmarking')
        link(p,k,title)
doc.save(OUT)
print(f'Wrote {OUT}, {NREF} sources, {1+len(pages)+len(ref_sizes)} planned pages')

