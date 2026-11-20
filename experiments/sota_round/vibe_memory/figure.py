"""Plot the reader-facing length distribution for each of the 111 paired queries."""
import json
import statistics as st
from collections import Counter
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parent
ROWS=[json.loads(line) for line in (ROOT/"stage_rows.jsonl").read_text(encoding="utf8").splitlines()]


def font(size,bold=False):
    for path in (("C:/Windows/Fonts/calibrib.ttf" if bold else "C:/Windows/Fonts/calibri.ttf"),
                 ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")):
        if Path(path).exists():
            return ImageFont.truetype(path,size)
    return ImageFont.load_default(size=size)


def main():
    img=Image.new("RGB",(1440,435),"white")
    d=ImageDraw.Draw(img)
    left,right=296,1400
    axis=lambda x:left+(right-left)*x/250
    for tick in range(0,251,50):
        x=axis(tick)
        d.line((x,36,x,305),fill="#D8DEDC",width=2)
        d.text((x,316),str(tick),font=font(29),fill="#46545B",anchor="mt")
    ordered=[("raw_bm25","BM25, шаги","#74868D"),("echo_capped","Echo","#7696AC"),("action_receipt","BM25, действия","#15736A")]
    for i,(method,label,color) in enumerate(ordered):
        y=67+94*i
        values=sorted(r["words_with_header"] for r in ROWS if r["method"]==method)
        assert len(values)==111
        d.text((8,y),label,font=font(32,True),fill="#1E2B36",anchor="lm")
        q1,mid,q3=st.quantiles(values,n=4,method="inclusive")
        d.line((axis(values[0]),y,axis(values[-1]),y),fill=color,width=4)
        for x in (values[0],values[-1]):
            d.line((axis(x),y-9,axis(x),y+9),fill=color,width=3)
        d.rounded_rectangle((axis(q1),y-15,max(axis(q1)+1,axis(q3)),y+15),radius=4,fill=color)
        d.line((axis(mid),y-20,axis(mid),y+20),fill="#102D32",width=5)
        d.text((min(axis(mid),right-10),y+23),str(int(mid)),font=font(24,True),fill="#24373D",anchor="mt")
    d.text((right,367),"Слов в записи вместе с заголовком",font=font(31),fill="#435159",anchor="rt")
    img.save(ROOT/"reader_words.png",dpi=(192,192),optimize=True)


if __name__=="__main__":
    main()
