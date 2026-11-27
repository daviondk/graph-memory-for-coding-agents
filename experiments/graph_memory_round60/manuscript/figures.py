"""Recreate the actual console state and project-level plot from the published records."""
from pathlib import Path
import json
import reportlab
from reportlab.lib.colors import HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
data=json.loads((HERE.parent/"coverage/results.json").read_bytes())["new/B"]["charges"]
rows={k.split("/")[-1]:(v["1024/exact"]-v["1024/notify"],v["1024/xor"]-v["1024/notify"]) for k,v in data.items()}
pdfmetrics.registerFont(TTFont("Chart",str(Path(reportlab.__file__).parent/"fonts"/"Vera.ttf")))
c=Canvas(str(HERE/"projects.pdf"),pagesize=(248,125),invariant=True,initialFontName="Chart")
c.setFont("Chart",7);left=75;scale=113/max(v[0] for v in rows.values())
for i,(name,(full,xor)) in enumerate(sorted(rows.items(),key=lambda x:-x[1][0])):
    y=106-14*i;c.setFillColor(HexColor("#1b343a"));c.drawString(1,y,name.replace("pydata-sphinx-theme","pydata theme"))
    for v,color,dy in ((full,"#226459",3),(xor,"#b06830",-2)):
        c.setFillColor(HexColor(color));c.rect(left,y+dy,max(.65,v*scale),3.4,fill=1,stroke=0)
    c.setFillColor(HexColor("#21383e"));c.drawRightString(245,y,f"{full:,} / {xor:,}")
c.setStrokeColor(HexColor("#879698"));c.line(left,31,left,118)
c.setFillColor(HexColor("#226459"));c.drawString(1,13,"Savings vs compressed lists")
c.setFillColor(HexColor("#ab6131"));c.drawString(124,13,"Savings vs XOR (bytes)")
c.showPage();c.save()
with sync_playwright() as p:
    b=p.chromium.launch(channel="msedge",headless=True)
    page=b.new_page(viewport={"width":940,"height":880},device_scale_factor=1.3,offline=True)
    page.goto((HERE.parent/"demo/index.html").as_uri());page.click("#two")
    page.locator("#lab .layout .panel").nth(1).screenshot(path=str(HERE/"lab.png"))
    b.close()
