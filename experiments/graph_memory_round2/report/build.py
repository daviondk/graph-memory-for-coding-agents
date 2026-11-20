"""Typeset the Russian report from ordered UTF-8 page sources."""
import re
from pathlib import Path

from docx import Document
from docx.enum.style import WD_STYLE_TYPE
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_TAB_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from docx.shared import Cm, Pt, RGBColor

HERE = Path(__file__).resolve().parent
NAME = "graph-memory-research-round2"
WIDTH = 16.8
reference = HERE.parents[2] / "outputs" / "agent-memory-session6-results.docx"
doc = Document(reference)
for item in list(doc._element.body):
    if item.tag != qn("w:sectPr"):
        doc._element.body.remove(item)
for key, rel in list(doc.part.rels.items()):
    if rel.reltype in (RT.HYPERLINK, RT.IMAGE):
        doc.part.drop_rel(key)
sec = doc.sections[0]
sec.page_height, sec.page_width = Cm(29.7), Cm(21)
sec.left_margin = sec.right_margin = Cm(2.1)
sec.top_margin, sec.bottom_margin = Cm(1.95), Cm(1.85)
sec.header_distance = sec.footer_distance = Cm(.77)


def style(name, size, color, bold=False, before=0, after=5, leading=1.12, face="Calibri"):
    s = doc.styles[name] if name in doc.styles else doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
    s.font.name, s.font.size, s.font.bold = face, Pt(size), bold
    s.font.color.rgb = RGBColor.from_string(color)
    fmt = s.paragraph_format
    fmt.space_before, fmt.space_after, fmt.line_spacing = Pt(before), Pt(after), leading
    return s


ink = "172934"
style("Title", 31, "000000", True, after=12, leading=1.03, face="Cambria")
style("Heading 1", 25, "000000", True, after=10, leading=1.04, face="Cambria")
style("Heading 2", 14, ink, True, before=8, after=4)
style("Normal", 12.0, ink, after=7, leading=1.13)
style("Lead", 14, ink, after=10, leading=1.12, face="Cambria")
style("Source", 10.1, "45606E", before=2, after=7, leading=1.07)
style("Cell", 10.8, ink, after=0, leading=1.07)
style("Running", 9.4, "516774", after=0)
for node in doc.styles["Title"]._element.xpath(".//w:pBdr"):
    node.getparent().remove(node)
hdr = sec.header.paragraphs[0]
hdr.clear()
hdr.style, hdr.alignment = "Running", WD_ALIGN_PARAGRAPH.RIGHT
hdr.add_run("Графовая память агента   /   Исследовательский отчёт")
footer = sec.footer.paragraphs[0]
footer.clear()
footer.style = "Running"
footer.paragraph_format.tab_stops.add_tab_stop(Cm(WIDTH), WD_TAB_ALIGNMENT.RIGHT)
footer.add_run("\t")
field = OxmlElement("w:fldSimple")
field.set(qn("w:instr"), "PAGE")
footer._p.append(field)


def hyperlink(par, label, url):
    element = OxmlElement("w:hyperlink")
    element.set(qn("r:id"), par.part.relate_to(url, RT.HYPERLINK, is_external=True))
    run = OxmlElement("w:r")
    props = OxmlElement("w:rPr")
    color = OxmlElement("w:color")
    color.set(qn("w:val"), "1A526F")
    props.append(color)
    run.append(props)
    text = OxmlElement("w:t")
    text.text = label
    run.append(text)
    element.append(run)
    par._p.append(element)


def inline(par, msg):
    msg = re.sub(r"(?<=\d) (?=\d{3}\b)", "\u00a0", msg)
    pattern = r"\[([^\]]+)\]\((https?://[^)]+)\)|\*\*([^*]+)\*\*"
    end = 0
    for part in re.finditer(pattern, msg):
        par.add_run(msg[end:part.start()])
        if part[1] is not None:
            hyperlink(par, part[1], part[2])
        else:
            par.add_run(part[3]).bold = True
        end = part.end()
    par.add_run(msg[end:])


def paragraph(msg, name="Normal"):
    par = doc.add_paragraph(style=name)
    inline(par, msg)
    if par._p.getprevious() is not None and par._p.getprevious().tag == qn("w:tbl"):
        par.paragraph_format.space_before = Pt(7)
    return par


def table(lines, proportions):
    items = [[v.strip() for v in line.strip("|").split("|")] for line in lines]
    cols = len(items[0])
    assert all(len(row) == cols for row in items)
    assert len(proportions) == cols
    tb = doc.add_table(rows=0, cols=cols)
    borders = OxmlElement("w:tblBorders")
    for key in ("top", "left", "bottom", "right", "insideH", "insideV"):
        edge = OxmlElement("w:" + key)
        for attr, value in (("val","single"),("sz","4"),("color","D9D9D9")):
            edge.set(qn("w:" + attr), value)
        borders.append(edge)
    tb._tbl.tblPr.append(borders)
    tb.autofit, tb.alignment = False, WD_TABLE_ALIGNMENT.CENTER
    widths = [p / sum(proportions) * WIDTH for p in proportions]
    for col, width in zip(tb.columns, widths):
        col.width = Cm(width)
    for i, row in enumerate(items):
        tr = tb.add_row()
        trpr = tr._tr.get_or_add_trPr()
        trpr.append(OxmlElement("w:cantSplit"))
        if not i:
            trpr.append(OxmlElement("w:tblHeader"))
        for j, (cell, content, width) in enumerate(zip(tr.cells, row, widths)):
            cell.width = Cm(width)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            shading = OxmlElement("w:shd")
            shading.set(qn("w:fill"), "284B60" if i == 0 else ("EAF1F4" if i % 2 else "F9FBFB"))
            cell._tc.get_or_add_tcPr().append(shading)
            par = cell.paragraphs[0]
            par.style = "Cell"
            par.paragraph_format.space_before = Pt(4)
            par.paragraph_format.space_after = Pt(4)
            if j and width < 4.0:
                par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = par.add_run(re.sub(r"(?<=\d) (?=\d{3}\b)", "\u00a0", content))
            if i == 0:
                run.bold = True
                run.font.color.rgb = RGBColor.from_string("FFFFFF")


def add_page(path, number):
    lines = [s.strip() for s in path.read_text(encoding="utf-8").splitlines() if s.strip()]
    assert lines[0].startswith("# ")
    title = paragraph(lines.pop(0)[2:], "Heading 1" if number else "Title")
    title.paragraph_format.page_break_before = number > 0
    while lines:
        line = lines.pop(0)
        if line.startswith("@ "):
            widths = [float(x) for x in line[2:].split()]
            chunk = []
            while lines and lines[0].startswith("|"):
                chunk.append(lines.pop(0))
            table(chunk, widths)
        elif line.startswith("## "):
            paragraph(line[3:], "Heading 2")
        elif line.startswith("> "):
            paragraph(line[2:], "Lead")
        elif line.startswith("~ "):
            paragraph(line[2:], "Source")
        elif line.startswith("! "):
            par = doc.add_paragraph()
            par.alignment = WD_ALIGN_PARAGRAPH.CENTER
            par.add_run().add_picture(str(HERE / line[2:]), width=Cm(15.9))
        else:
            paragraph(line)


if __name__ == "__main__":
    pages = sorted((HERE / "pages").glob("*.md"))
    for index, path in enumerate(pages):
        add_page(path, index)
    doc.core_properties.title = "Графовая память агента"
    doc.core_properties.subject = "Сравнение способов записи и чтения памяти на открытых тестах"
    doc.core_properties.author = "Исследовательский отчёт"
    final = HERE / "final"
    final.mkdir(exist_ok=True)
    doc.save(final / (NAME + ".docx"))
