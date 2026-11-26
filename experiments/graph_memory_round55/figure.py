"""Effect sizes from paired task-level retrieval and measured physical SQLite work."""
import json
from pathlib import Path
from reportlab.pdfgen.canvas import Canvas
from reportlab.lib.colors import HexColor

HERE=Path(__file__).resolve().parent
def load(p):
    return json.loads((HERE/p).read_bytes())
def write(c,x,y,value,size=9,color="#273e4e",bold=False):
    c.setFillColor(HexColor(color))
    c.setFont("Helvetica-Bold" if bold else "Helvetica",size)
    c.drawString(x,y,value)
def line(c,x,y,u,v,shade,width=1):
    c.setStrokeColor(HexColor(shade));c.setLineWidth(width);c.line(x,y,u,v)

def main():
    c=Canvas(str(HERE/"memory-evidence.pdf"),pagesize=(600,541),invariant=1)
    c.setTitle("When does co-edit history help?")
    write(c,28,506,"When does co-edit history help?",21,bold=True)
    write(c,28,481,"Change in Recall@5 from adding historical evidence (percentage points)",12,bold=True)
    write(c,28,463,"54 edit2ripple tasks, 10 repositories. Lines are paired repository-bootstrap 95% intervals.")
    com=load("benchmark_history/community-results.json")["within_method"]
    orig=load("benchmark_history/original-results.json")["primary"]
    data=[("Lexical, five new files",com["lexical"]),("Lexical, original five slots",orig),
          ("CodeNib dense",com["codenib_dense"]),("CodeNib hybrid",com["codenib_hybrid"]),
          ("Oko 0.9.1, mean of three runs",com["oko_mean"]),("CodeNib Zoekt",com["codenib_zoekt"]),
          ("CodeNib graph expansion",com["codenib_graph_expansion"])]
    coord=lambda v:213+(v+8)*17
    for n in (-8,-4,0,4,8):
        line(c,coord(n),283,coord(n),446,"#839aa3" if n==0 else "#e1e7e9")
        write(c,coord(n)-5,268,str(n),8)
    for i,(label,e) in enumerate(data):
        y=432-i*23;d=e["delta"]*100;l,u=(v*100 for v in e["interval"])
        color="#67507c" if i==1 else "#20676a"
        write(c,28,y-3,label,9)
        line(c,coord(l),y,coord(u),y,color,2)
        c.setFillColor(HexColor(color));c.circle(coord(d),y,3,fill=1,stroke=0)
        write(c,501,y-3,f"{d:+.2f}",9,color,True)
    write(c,28,234,"Physical work to maintain the exact top eight",13,bold=True)
    write(c,28,216,"3,023 Git updates across six projects. Counts exclude the common cold-start queries.")
    t=load("cochange/physical/vm-steps.json")["total"]
    for i,(x,s) in enumerate(((28,"Cached state"),(245,"Index probes"),(347,"Rows returned"),(458,"SQLite VM steps"))):
        write(c,x,189,s,9,bold=True)
    for i,(k,label) in enumerate((("classic8","Classic 8 candidates"),("partial8","8 candidates + one bound"),("classic9","Classic 9 candidates"))):
        y=164-i*22;a=t[k]["warm"]
        write(c,28,y,label,10)
        for x,v in ((245,a["executions"]),(347,a["returned_rows"]),(458,a["vm_steps"])):
            write(c,x,y,f"{v:,}",10,bold=True)
    line(c,28,105,570,105,"#cdd8db")
    write(c,28,83,"At equal candidate counts, the extra bound saves index work.",10)
    write(c,28,66,"At equal payload size (72 bytes), retaining a ninth candidate needs fewer index probes",10)
    write(c,28,50,"and fewer VM steps. Both strategies return the same ranked IDs and scores.",10)
    c.showPage();c.save()
if __name__=="__main__":
    main()
