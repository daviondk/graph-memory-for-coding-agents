"""Render evidence for the paper directly from the frozen holdout and offline UI."""
import json
from pathlib import Path
import reportlab
from reportlab.pdfgen.canvas import Canvas
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase import pdfmetrics
from reportlab.lib.colors import HexColor
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
data=json.loads((HERE.parent/"holdout/results.json").read_bytes())["sketch"]["projects"]
rows={k[2:]:v for k,v in data.items() if k.startswith("B/")}
names=list(sorted(rows,key=lambda k:rows[k]["1024/exact"]-rows[k]["1024/xor"]))
diff=[rows[k]["1024/exact"]-rows[k]["1024/xor"] for k in names]
pdfmetrics.registerFont(TTFont("Chart", str(Path(reportlab.__file__).parent/"fonts"/"Vera.ttf")))
fig=Canvas(str(HERE/"holdout.pdf"),pagesize=(245,123),invariant=True,initialFontName="Chart")
left=95; positive=max(diff); negative=abs(min(diff)); scale=113/max(1,positive,negative)
fig.setFont("Chart",7)
for i,(name,d) in enumerate(zip(names,diff)):
    y=108-15*i
    fig.setFillColor(HexColor("#213538"));fig.drawString(3,y,name.split("/")[-1])
    fig.setFillColor(HexColor("#216e63" if d>=0 else "#9d4e33"))
    if d:fig.rect(left+min(0,d*scale),y-1,abs(d*scale),7,fill=1,stroke=0)
    else:fig.circle(left,y+2,2,fill=1,stroke=0)
    fig.setFillColor(HexColor("#213538"));fig.drawRightString(240,y,f"{d:+,d}")
fig.setStrokeColor(HexColor("#718183"));fig.setLineWidth(.5);fig.line(left,28,left,119)
fig.setFont("Chart",7);fig.drawString(3,13,"Positive: fewer bytes with count + XOR")
fig.showPage();fig.save()
with sync_playwright() as p:
    b=p.chromium.launch(channel="msedge",headless=True)
    page=b.new_page(viewport={"width":890,"height":920},device_scale_factor=1.3,offline=True)
    page.goto((HERE.parent/"demo/index.html").as_uri())
    page.click("#goSketch");page.locator("#sketch .split .box").first.screenshot(path=str(HERE/"certificate.png"))
    b.close()
