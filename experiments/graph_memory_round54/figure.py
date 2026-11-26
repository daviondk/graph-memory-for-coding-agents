"""Draw the code transfer and source-maintenance measurements from their result files."""
from pathlib import Path
import json
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor
D=Path(__file__).resolve().parent
def load(name):
    return json.loads((D/name).read_bytes())
def text(c,x,y,words,size=10,bold=False,color="#183044"):
    c.setFillColor(HexColor(color))
    c.setFont("Helvetica-Bold" if bold else "Helvetica",size)
    c.drawString(x,y,words)
def panel(c,y,title,note,labels,values,maxv,unit):
    text(c,26,y,title,13,True)
    text(c,26,y-17,note,9,color="#435864")
    left,right=212,489
    step=19
    for i,(name,v) in enumerate(zip(labels,values)):
        yy=y-39-i*step
        text(c,34,yy-3,name,10)
        c.setStrokeColor(HexColor("#d6dfe1"));c.line(left,yy,right,yy)
        c.setFillColor(HexColor("#256a67"));c.rect(left,yy-3.3,(right-left)*v/maxv,6.6,fill=1,stroke=0)
        text(c,right+10,yy-3,(f"{v:.2f}%" if unit=="%" else str(v)),10,True)
def main():
    c=Canvas(str(D/"code-and-updates.pdf"),pagesize=(560,540),invariant=1)
    c.setTitle("Code retrieval, execution and versioned top-k maintenance")
    text(c,26,509,"What transfers to repository work?",19,True)
    m=load("code_links/results.json")["overall"]["metrics"]
    panel(c,477,"Locating changed files","54 held-out edits, 10 repositories. Mean Recall@5, five previously unprovided file addresses.",
        ["Lexical (published)","RepoMap (published)","Scoped symbol links","Matched text votes","BM25 (published)"],
        [100*m[x]["recall5"] for x in ("lexical","repomap","graph_vote","text_vote","bm25")],55,"%")
    r=load("next_read/explicit-results.json")["subsets"]["all"]["rates_pct"]
    l=load("learned_read/results.json")["all"]["summary"]
    panel(c,325,"Choosing one further source","283 archived sessions, 25 repositories. Percentage of new reads that hit a required file.",
        ["Qwen3-Embedding-4B","Seven static ranks (RRF)","Learned ranks + suggestion","Learned static ranks","First valid agent suggestion"],
        [r["embed4"]["new_hit"],l["rrf7"]["new_hit_pct"],l["memory8"]["new_hit_pct"],l["static7"]["new_hit_pct"],r["memory"]["new_hit"]],11,"%")
    p=load("cutoff/correctness.json")["packets"]
    panel(c,173,"Maintaining an exact top-eight history","1,072 signed updates, 40 trajectories. Full index lookups after update; 40 common cold lookups excluded.",
        ["Always query the index","Skip unchanged results","Local rank boundary / Yi prefix","Outside bound + partial refill"],
        [p[k]["counts"]["index"] for k in ("index","unchanged","boundary")]+[load("reserve/partial-results.json")["plans"]["partial-8"]["warm_probes"]],1072,"count")
    cap=load("execution/cap-results.json")["summaries"]
    n=sum(cap["bm25"]["status"].values());a=cap["caller_bm25"]["passed"];b=cap["bm25"]["passed"]
    text(c,26,48,f"Executable control: ClassEval at a 768-token output cap, caller context {a}/{n}, BM25 {b}/{n}.",10,True)
    text(c,26,31,"Intervals for paired effects and full per-case data are in the linked experiment reports.",9,color="#435864")
    c.showPage();c.save()
if __name__=="__main__":main()
