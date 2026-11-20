"""Validate DOCX links, PDF pages, titles, text boundaries and raster metadata."""
import argparse
import json
import subprocess
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
from PIL import Image,ImageDraw
from pypdf import PdfReader
import pdfplumber

ROOT=Path(__file__).resolve().parent
PDFBIN=Path("C:/Users/Admin/.cache/codex-runtimes/codex-primary-runtime/dependencies/native/poppler/Library/bin")
NS={"p":"http://www.w3.org/1999/xhtml","r":"http://schemas.openxmlformats.org/package/2006/relationships"}
titles=["Что сохранять","Реквизиты между","Когда можно доверять","Что приносит память","Как памятка влияет",
        "Что нужно помнить","Как модель читает","Опыт похожих комнат","Что изменилось без меню","Нужно ли сохранять","С чем сравнивать","Три направления"]
def main(folder):
    folder=ROOT/folder
    base=folder/"agent-memory-session3-results"
    pdf=PdfReader(base.with_suffix(".pdf"))
    geom=pdfplumber.open(base.with_suffix(".pdf"))
    rows=[]
    for i,(page,xpage) in enumerate(zip(pdf.pages,geom.pages),1):
        words=xpage.extract_words();W,H=xpage.width,xpage.height
        main_words=[word for word in words if 48<word["top"]<H-50]
        full=" ".join(w["text"] for w in words)
        if not main_words:
            rows.append({"n":i,"text":full,"error":"blank"})
            continue
        body_end=max(w["bottom"] for w in main_words)
        bounds=all(0<w["x0"]<w["x1"]<W and 0<w["top"]<w["bottom"]<H for w in words)
        annots=page.get("/Annots",[])
        links=[ann.get_object().get("/A",{}).get("/URI","") for ann in annots]
        rows.append({"n":i,"body_end_pt":round(body_end,1),"words":len(main_words),"page_h":round(H,1),"bounds_ok":bounds,
                     "matches": [t for t in titles if t in full], "links":len(links),"preview":full[:125]})
    with zipfile.ZipFile(base.with_suffix(".docx")) as z:
        rel=ET.fromstring(z.read("word/_rels/document.xml.rels"))
        links={e.attrib["Target"] for e in rel if e.attrib.get("TargetMode")=="External"}
    print(json.dumps(rows,ensure_ascii=False,indent=1))
    (folder/"qa.json").write_text(json.dumps({"pages":rows,"docx_hyperlinks":sorted(links),"paragraph_titles":titles},ensure_ascii=False,indent=1),encoding="utf8")
    paths=sorted(folder.glob("page-*.png"),key=lambda p:int(p.stem.split("-")[-1]))
    sw=374;sh=546
    for group in range(0,len(paths),5):
        ss=Image.new("RGB",(sw*len(paths[group:group+5]),sh),"#dfe5e9")
        draw=ImageDraw.Draw(ss)
        for j,path in enumerate(paths[group:group+5]):
            img=Image.open(path).convert("RGB");img.thumbnail((sw-16,sh-27));ss.paste(img,(j*sw+8,4));draw.text((j*sw+9,sh-18),path.stem,fill="#173a53")
        ss.save(folder/("overview_"+str(group//5+1)+".png"))
    return rows
if __name__=="__main__":
    main(sys.argv[1])

