"""Validate text, dimensions, live links, and page raster coverage for the report."""
import hashlib
import json
import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET
import pdfplumber
from PIL import Image, ImageDraw
from pypdf import PdfReader
from source_audit import audit

root = Path(__file__).resolve().parent
folder = root / "final"
stem = folder / "agent-memory-session6-results"
titles = [p.read_text(encoding="utf-8").splitlines()[0][2:] for p in sorted((root / "pages").glob("*.md"))]
flatten = lambda v: re.sub(r"\s+", "", v).casefold()
reader = PdfReader(stem.with_suffix(".pdf"))
with zipfile.ZipFile(stem.with_suffix(".docx")) as archive:
    links = [r.attrib["Target"] for r in ET.fromstring(archive.read("word/_rels/document.xml.rels"))
             if r.attrib.get("TargetMode") == "External"]
rows = []
with pdfplumber.open(stem.with_suffix(".pdf")) as geom:
    assert len(geom.pages) == len(titles), (len(geom.pages), titles)
    assert len(list(folder.glob("page-*.png"))) == len(titles)
    for i, (page, title) in enumerate(zip(geom.pages, titles), 1):
        words = page.extract_words()
        body = [w for w in words if 43 < w["top"] < page.height - 45]
        txt = " ".join(w["text"] for w in words)
        assert flatten(title) in flatten(txt), (i, title)
        assert all(0 <= w["x0"] < w["x1"] <= page.width + .1 and 0 <= w["top"] < w["bottom"] <= page.height + .1 for w in words)
        assert len(body) >= 125
        pic = folder / f"page-{i}.png"
        with Image.open(pic) as image:
            assert image.width >= 900 and image.height >= 1200
        rows.append(dict(page=i, title=title, words=len(body), bottom_pt=round(max(w["bottom"] for w in body),1),
                         raster_sha256=hashlib.sha256(pic.read_bytes()).hexdigest(),
                         pdf_links=len(reader.pages[i-1].get("/Annots", []))))
for start in range(0, len(rows), 3):
    group = rows[start:start+3]
    sheet = Image.new("RGB", (430*len(group),630), "#DFE6E9")
    label = ImageDraw.Draw(sheet)
    for j, row in enumerate(group):
        with Image.open(folder/f"page-{row['page']}.png") as p:
            p.thumbnail((410,585))
            sheet.paste(p,(j*430+10,9))
        label.text((j*430+10,601), f"Page {row['page']}", fill="#153443")
    sheet.save(folder/f"overview-{1+start//3}.png")
out = {"pages":rows,"word_external_links":sorted(set(links)), "bundle":"26.1117.12345",
       "tables_rechecked":audit()}
(folder/"qa.json").write_text(json.dumps(out, ensure_ascii=False, indent=2),encoding="utf-8")
print([(row["page"],row["words"],row["bottom_pt"]) for row in rows])
