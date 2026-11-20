import ast,collections,gzip,json
from build_memory import D,tokens,dump
def main(i):
    t=D/"tasks"/i;ctr=json.loads((t/"grades_v2/control.json").read_text(encoding="utf8"))
    labels=ctr["gold"]["gold_lines"];regular=json.loads(gzip.decompress((t/"packets.json.gz").read_bytes()))
    files={k:(t/"base"/k).read_text(encoding="utf8").splitlines() for k in labels if (t/"base"/k).exists()}
    segs=[];defs={}
    for p,ns in sorted(labels.items()):
        if p not in files:continue
        try:tree=ast.parse("\n".join(files[p]))
        except SyntaxError:continue
        defs[p]=sorted([(n.lineno,n.end_lineno,n.name) for n in ast.walk(tree) if isinstance(n,(ast.FunctionDef,ast.ClassDef))],key=lambda x:x[1]-x[0])
        for n in sorted(set(ns)):
            if segs and segs[-1][0]==p and n<=segs[-1][2]+2:segs[-1][2]=n
            else:segs.append([p,n,n])
    spans={}
    def render(spans):
        boxes=[]
        for p in sorted(files):
            arr=sorted((a,b) for pp,a,b in spans.values() if pp==p);merged=[]
            for a,b in arr:
                if merged and a<=merged[-1][1]+1:merged[-1][1]=max(b,merged[-1][1])
                else:merged.append([a,b])
            for a,b in merged:
                name=next((s for st,en,s in defs.get(p,[]) if en>=a and st<=b),"")
                boxes.append(f"{p}  L{a}-{b}  .{name}\n"+"\n".join(files[p][a-1:b]))
        return "\n\n".join(boxes)
    for radius in (0,5,12,24,48):
        for j,(p,a,b) in enumerate(segs):
            tmp={**spans,j:(p,max(1,a-radius),min(len(files[p]),b+radius))}
            if len(tokens(render(tmp)))<=1800:spans=tmp
    packet=render(spans)
    dump(t/"oracle.json.gz",{"issue":regular["issue"],"packets":{"oracle":packet},"paths":sorted(files),"spans":spans,"tokens":len(tokens(packet))})
if __name__=="__main__":
    for i in json.loads((D/"cohort.json").read_text())["ids"]:main(i)

